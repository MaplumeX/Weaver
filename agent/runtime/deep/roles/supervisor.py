"""
Deep Research supervisor agent.

Unifies planning and loop-control decisions for the multi-agent deep runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from .planner import ResearchPlanner


SUPERVISOR_DECISION_PROMPT = """
# 角色
你是一名 Deep Research supervisor，负责决定当前研究循环的下一步动作。

# 当前研究状态
- 主题: {topic}
- 已完成查询数: {num_queries}
- 已收集来源数: {num_sources}
- 已生成摘要数: {num_summaries}
- 当前轮次: {current_epoch}/{max_epochs}
- 质量总分: {quality_score}
- 缺口数量: {quality_gap_count}
- 引用准确/覆盖: {citation_accuracy}
- 已知信息摘要: {knowledge_summary}

# 可选动作
1. plan: 首次生成研究计划
2. dispatch: 继续派发当前 ready branch
3. replan: 基于缺口和验证反馈重规划
4. report: 停止研究并生成最终报告
5. stop: 终止当前研究循环

# 输出格式
严格按照以下格式输出：
action: <动作名称>
reasoning: <决策理由>
priority_topics: <如选择 replan，可列出优先研究的子话题，逗号分隔>
"""


class SupervisorAction(str, Enum):
    PLAN = "plan"
    DISPATCH = "dispatch"
    REPLAN = "replan"
    RETRY_BRANCH = "retry_branch"
    REPORT = "report"
    STOP = "stop"


@dataclass
class SupervisorDecision:
    action: SupervisorAction
    reasoning: str
    priority_topics: list[str] = field(default_factory=list)
    retry_task_ids: list[str] = field(default_factory=list)
    request_ids: list[str] = field(default_factory=list)


class ResearchSupervisor:
    """Single control-plane role for Deep Research planning and loop decisions."""

    def __init__(self, llm: BaseChatModel, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._planner = ResearchPlanner(llm, self.config)
        self._llm = llm

    def create_plan(
        self,
        topic: str,
        *,
        num_queries: int = 5,
        existing_knowledge: str = "",
        existing_queries: list[str] | None = None,
        approved_scope: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._planner.create_plan(
            topic,
            num_queries=num_queries,
            existing_knowledge=existing_knowledge,
            existing_queries=existing_queries,
            approved_scope=approved_scope,
        )

    def refine_plan(
        self,
        topic: str,
        *,
        gaps: list[str],
        existing_queries: list[str],
        num_queries: int = 3,
        approved_scope: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._planner.refine_plan(
            topic,
            gaps=gaps,
            existing_queries=existing_queries,
            num_queries=num_queries,
            approved_scope=approved_scope,
        )

    def decide_next_action(
        self,
        *,
        topic: str,
        num_queries: int,
        num_sources: int,
        num_summaries: int,
        current_epoch: int,
        max_epochs: int,
        ready_task_count: int = 0,
        retry_task_ids: list[str] | None = None,
        request_ids: list[str] | None = None,
        budget_stop_reason: str = "",
        knowledge_summary: str = "",
        quality_score: float | None = None,
        quality_gap_count: int = 0,
        citation_accuracy: float | None = None,
        verification_summary: dict[str, Any] | None = None,
    ) -> SupervisorDecision:
        normalized_retry_task_ids = [
            str(task_id).strip()
            for task_id in (retry_task_ids or [])
            if str(task_id).strip()
        ]
        normalized_request_ids = [
            str(request_id).strip()
            for request_id in (request_ids or [])
            if str(request_id).strip()
        ]
        if budget_stop_reason:
            return SupervisorDecision(
                action=SupervisorAction.STOP,
                reasoning=budget_stop_reason,
                request_ids=normalized_request_ids,
            )
        if current_epoch >= max_epochs:
            return SupervisorDecision(
                action=SupervisorAction.REPORT,
                reasoning="已达到最大研究轮次，停止继续派发研究任务",
                request_ids=normalized_request_ids,
            )
        if normalized_retry_task_ids:
            return SupervisorDecision(
                action=SupervisorAction.RETRY_BRANCH,
                reasoning="branch 验证要求补证据，优先重试现有分支",
                retry_task_ids=normalized_retry_task_ids,
                request_ids=normalized_request_ids,
            )
        if ready_task_count > 0:
            return SupervisorDecision(
                action=SupervisorAction.DISPATCH,
                reasoning="队列中存在 ready branch，继续派发研究任务",
                request_ids=normalized_request_ids,
            )

        action, reasoning, priority_topics = self._decide_action(
            topic=topic,
            num_queries=num_queries,
            num_sources=num_sources,
            num_summaries=num_summaries,
            current_epoch=current_epoch,
            max_epochs=max_epochs,
            knowledge_summary=knowledge_summary,
            quality_score=quality_score,
            quality_gap_count=quality_gap_count,
            citation_accuracy=citation_accuracy,
            verification_summary=verification_summary or {},
        )
        return SupervisorDecision(
            action=action,
            reasoning=reasoning,
            priority_topics=priority_topics,
            request_ids=normalized_request_ids,
        )

    def _decide_action(
        self,
        *,
        topic: str,
        num_queries: int,
        num_sources: int,
        num_summaries: int,
        current_epoch: int,
        max_epochs: int,
        knowledge_summary: str,
        quality_score: float | None,
        quality_gap_count: int,
        citation_accuracy: float | None,
        verification_summary: dict[str, Any],
    ) -> tuple[SupervisorAction, str, list[str]]:
        retry_branches = max(0, int(verification_summary.get("retry_branches", 0) or 0))
        failed_branches = max(0, int(verification_summary.get("failed_branches", 0) or 0))
        verified_branches = max(0, int(verification_summary.get("verified_branches", 0) or 0))

        if num_queries == 0:
            return SupervisorAction.PLAN, "研究尚未开始，需要先生成研究计划", []
        if failed_branches > 0:
            return SupervisorAction.REPLAN, "分支执行存在失败，基于当前证据重规划研究任务", []
        if retry_branches > 0:
            return SupervisorAction.REPLAN, "验证指出仍存在证据缺口，需要补充研究计划", []
        if (
            quality_score is not None
            and max(num_summaries, verified_branches) > 0
            and quality_score >= 0.82
            and quality_gap_count == 0
            and (citation_accuracy is None or citation_accuracy >= 0.7)
        ):
            return SupervisorAction.REPORT, "质量评估良好且无明显缺口，可以进入最终汇总", []
        if (
            quality_score is not None
            and (
                quality_score < 0.6
                or quality_gap_count > 0
                or (citation_accuracy is not None and citation_accuracy < 0.55)
            )
        ):
            return SupervisorAction.REPLAN, "质量信号显示仍存在覆盖或证据缺口，需要重规划", []

        prompt = ChatPromptTemplate.from_messages([("user", SUPERVISOR_DECISION_PROMPT)])
        response = self._llm.invoke(
            prompt.format_messages(
                topic=topic,
                num_queries=num_queries,
                num_sources=num_sources,
                num_summaries=num_summaries,
                current_epoch=current_epoch,
                max_epochs=max_epochs,
                quality_score=f"{quality_score:.2f}" if quality_score is not None else "unknown",
                quality_gap_count=quality_gap_count,
                citation_accuracy=(
                    f"{citation_accuracy:.2f}" if citation_accuracy is not None else "unknown"
                ),
                knowledge_summary=(
                    (knowledge_summary[:1600] + "\n\n验证摘要: " + str(verification_summary)[:400])
                    if verification_summary
                    else (knowledge_summary[:2000] or "暂无")
                ),
            ),
            config=self.config,
        )
        return self._parse_decision(getattr(response, "content", "") or "")

    def _parse_decision(
        self,
        content: str,
    ) -> tuple[SupervisorAction, str, list[str]]:
        action = SupervisorAction.DISPATCH
        reasoning = ""
        priority_topics: list[str] = []

        for raw_line in content.strip().splitlines():
            line = raw_line.strip()
            if line.lower().startswith("action:"):
                candidate = line.split(":", 1)[1].strip().lower()
                try:
                    action = SupervisorAction(candidate)
                except ValueError:
                    action = SupervisorAction.DISPATCH
            elif line.lower().startswith("reasoning:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line.lower().startswith("priority_topics:"):
                topics_str = line.split(":", 1)[1].strip()
                priority_topics = [topic.strip() for topic in topics_str.split(",") if topic.strip()]

        return action, reasoning or "继续执行当前 Deep Research 控制流", priority_topics


__all__ = [
    "ResearchSupervisor",
    "SupervisorAction",
    "SupervisorDecision",
]
