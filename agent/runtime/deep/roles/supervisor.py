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
from agent.prompts.runtime_templates import (
    DEEP_SUPERVISOR_DECISION_PROMPT as SUPERVISOR_DECISION_PROMPT,
)

from .planner import ResearchPlanner


class SupervisorAction(str, Enum):
    PLAN = "plan"
    DISPATCH = "dispatch"
    REPLAN = "replan"
    RETRY_BRANCH = "retry_branch"
    PATCH_BRANCH = "patch_branch"
    SPAWN_FOLLOW_UP_BRANCH = "spawn_follow_up_branch"
    SPAWN_COUNTEREVIDENCE_BRANCH = "spawn_counterevidence_branch"
    BOUNDED_STOP = "bounded_stop"
    REPORT = "report"
    STOP = "stop"


@dataclass
class SupervisorDecision:
    action: SupervisorAction
    reasoning: str
    priority_topics: list[str] = field(default_factory=list)
    retry_task_ids: list[str] = field(default_factory=list)
    request_ids: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    target_branch_ids: list[str] = field(default_factory=list)


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
        research_brief: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._planner.create_plan(
            topic,
            num_queries=num_queries,
            existing_knowledge=existing_knowledge,
            existing_queries=existing_queries,
            approved_scope=research_brief or approved_scope,
        )

    def refine_plan(
        self,
        topic: str,
        *,
        gaps: list[str],
        existing_queries: list[str],
        num_queries: int = 3,
        approved_scope: dict[str, Any] | None = None,
        research_brief: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._planner.refine_plan(
            topic,
            gaps=gaps,
            existing_queries=existing_queries,
            num_queries=num_queries,
            approved_scope=research_brief or approved_scope,
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
        revision_issues: list[dict[str, Any]] | None = None,
        research_brief: dict[str, Any] | None = None,
        task_ledger: dict[str, Any] | None = None,
        progress_ledger: dict[str, Any] | None = None,
        coverage_matrix: dict[str, Any] | None = None,
        contradiction_registry: dict[str, Any] | None = None,
        missing_evidence_list: dict[str, Any] | None = None,
        outline_artifact: dict[str, Any] | None = None,
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
        normalized_revision_issues = [
            issue
            for issue in (revision_issues or [])
            if isinstance(issue, dict)
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
        revision_decision = self._decide_revision_routing(normalized_revision_issues)
        if revision_decision is not None:
            revision_decision.request_ids = normalized_request_ids
            return revision_decision
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

        structured_action, structured_reason, structured_topics = self._decide_from_structured_state(
            research_brief=research_brief or {},
            task_ledger=task_ledger or {},
            progress_ledger=progress_ledger or {},
            coverage_matrix=coverage_matrix or {},
            contradiction_registry=contradiction_registry or {},
            missing_evidence_list=missing_evidence_list or {},
            outline_artifact=outline_artifact or {},
            verification_summary=verification_summary or {},
        )
        if structured_action is not None:
            return SupervisorDecision(
                action=structured_action,
                reasoning=structured_reason,
                priority_topics=structured_topics,
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

    def _decide_revision_routing(
        self,
        revision_issues: list[dict[str, Any]],
    ) -> SupervisorDecision | None:
        blocking_issues = [
            issue
            for issue in revision_issues
            if issue.get("blocking") and str(issue.get("status") or "").strip() in {"open", "accepted"}
        ]
        if not blocking_issues:
            return None
        issue_ids = [
            str(issue.get("id") or "").strip()
            for issue in blocking_issues
            if str(issue.get("id") or "").strip()
        ]
        target_branch_ids = list(
            dict.fromkeys(
                str(issue.get("branch_id") or "").strip()
                for issue in blocking_issues
                if str(issue.get("branch_id") or "").strip()
            )
        )
        actions = {
            str(issue.get("recommended_action") or "").strip()
            for issue in blocking_issues
            if str(issue.get("recommended_action") or "").strip()
        }
        if "spawn_counterevidence_branch" in actions:
            return SupervisorDecision(
                action=SupervisorAction.SPAWN_COUNTEREVIDENCE_BRANCH,
                reasoning="blocking issues 显示当前结论存在冲突，需要派生 counterevidence branch",
                issue_ids=issue_ids,
                target_branch_ids=target_branch_ids,
            )
        if "spawn_follow_up_branch" in actions:
            return SupervisorDecision(
                action=SupervisorAction.SPAWN_FOLLOW_UP_BRANCH,
                reasoning="blocking issues 需要额外 follow-up branch 来补齐 coverage 或证据范围",
                issue_ids=issue_ids,
                target_branch_ids=target_branch_ids,
            )
        return SupervisorDecision(
            action=SupervisorAction.PATCH_BRANCH,
            reasoning="blocking issues 可在现有 branch 上定向修订，优先 patch existing branch",
            issue_ids=issue_ids,
            target_branch_ids=target_branch_ids,
        )

    def _decide_from_structured_state(
        self,
        *,
        research_brief: dict[str, Any],
        task_ledger: dict[str, Any],
        progress_ledger: dict[str, Any],
        coverage_matrix: dict[str, Any],
        contradiction_registry: dict[str, Any],
        missing_evidence_list: dict[str, Any],
        outline_artifact: dict[str, Any],
        verification_summary: dict[str, Any],
    ) -> tuple[SupervisorAction | None, str, list[str]]:
        entries = task_ledger.get("entries", []) if isinstance(task_ledger, dict) else []
        if research_brief and not entries:
            return SupervisorAction.PLAN, "权威 research brief 已就绪，但 ledger 仍无任务，需要先生成正式计划", []

        open_requests = progress_ledger.get("active_request_ids", []) if isinstance(progress_ledger, dict) else []
        blocker_labels = []

        contradiction_entries = (
            contradiction_registry.get("entries", []) if isinstance(contradiction_registry, dict) else []
        )
        if contradiction_entries:
            blocker_labels.append("处理矛盾证据")

        missing_items = missing_evidence_list.get("items", []) if isinstance(missing_evidence_list, dict) else []
        blocking_missing_items = [
            item
            for item in missing_items
            if isinstance(item, dict) and bool(item.get("blocking", True))
        ]
        if blocking_missing_items:
            blocker_labels.append("补齐缺失证据")

        coverage_rows = coverage_matrix.get("rows", []) if isinstance(coverage_matrix, dict) else []
        uncovered_dimensions = [
            str(item.get("dimension") or item.get("label") or "").strip()
            for item in coverage_rows
            if (
                isinstance(item, dict)
                and str(item.get("status") or "").strip().lower() not in {"covered", "passed"}
                and (
                    bool(item.get("blocking"))
                    or (
                        "blocking" not in item
                        and str(item.get("status") or "").strip().lower() in {"gap", "unresolved"}
                    )
                )
            )
        ]
        blocker_labels.extend(item for item in uncovered_dimensions if item)

        blocking_gaps = outline_artifact.get("blocking_gaps", []) if isinstance(outline_artifact, dict) else []
        outline_ready = bool(outline_artifact.get("is_ready")) if isinstance(outline_artifact, dict) else False
        if blocking_gaps:
            blocker_labels.append("补齐报告结构缺口")

        retry_branches = max(0, int(verification_summary.get("retry_branches", 0) or 0))
        if retry_branches > 0:
            blocker_labels.append("重试分支补证据")

        if blocker_labels or open_requests:
            return (
                SupervisorAction.REPLAN,
                "控制面 artifacts 指出仍有未解决问题，需要继续重规划: " + "、".join(dict.fromkeys(blocker_labels)),
                list(dict.fromkeys(uncovered_dimensions[:3])),
            )

        if outline_artifact:
            if outline_ready:
                return SupervisorAction.REPORT, "outline 已就绪且不存在阻塞缺口，可以进入最终报告生成", []
            return SupervisorAction.REPLAN, "outline 尚未就绪，仍需先完成结构整理", []

        completed_entries = [
            item for item in entries if isinstance(item, dict) and str(item.get("status") or "") == "completed"
        ]
        if completed_entries and not blocker_labels:
            return SupervisorAction.REPORT, "brief、ledger 和验证 artifacts 已收敛，可以进入 outline/report 阶段", []
        return None, "", []

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
