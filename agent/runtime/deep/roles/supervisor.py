"""
Deep Research supervisor agent.

Unifies planning and loop-control decisions for the multi-agent deep runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.language_models import BaseChatModel

import agent.runtime.deep.support.runtime_support as support
from agent.runtime.deep.schema import OutlineArtifact, OutlineSection

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

    def create_outline_plan(
        self,
        topic: str,
        *,
        approved_scope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope = approved_scope or {}
        questions = [
            str(item).strip()
            for item in (scope.get("core_questions") or [])
            if str(item).strip()
        ]
        if not questions:
            fallback_goal = str(scope.get("research_goal") or topic).strip() or topic
            questions = [fallback_goal]

        sections: list[dict[str, Any]] = []
        question_map: dict[str, str] = {}
        shared_source_preferences = [
            str(item).strip()
            for item in (scope.get("source_preferences") or [])
            if str(item).strip()
        ]
        deliverable_preferences = [
            str(item).strip()
            for item in (scope.get("deliverable_preferences") or scope.get("deliverable_constraints") or [])
            if str(item).strip()
        ]
        constraints = [
            str(item).strip()
            for item in (scope.get("constraints") or [])
            if str(item).strip()
        ]
        time_boundary = str(scope.get("time_boundary") or "").strip()
        if not time_boundary:
            for item in constraints:
                if item.lower().startswith("time range:"):
                    time_boundary = item.split(":", 1)[1].strip()
                    break
        for index, question in enumerate(questions, 1):
            section = OutlineSection(
                id=support._new_id("section"),
                title=f"问题 {index}: {question}",
                objective=question,
                core_question=question,
                acceptance_checks=[question],
                source_requirements=[
                    "至少 1 个可引用来源",
                    "至少 1 段可定位 passage 支撑主结论",
                ],
                coverage_targets=[question],
                source_preferences=list(shared_source_preferences),
                authority_preferences=list(shared_source_preferences),
                freshness_policy="default_advisory",
                follow_up_policy="bounded",
                branch_stop_policy="coverage_or_budget",
                section_order=index,
                status="planned",
            )
            payload = section.to_dict()
            if deliverable_preferences:
                payload["deliverable_constraints"] = list(deliverable_preferences)
            if constraints:
                payload["constraints"] = list(constraints)
            if time_boundary:
                payload["time_boundary"] = time_boundary
            sections.append(payload)
            question_map[question] = section.id

        return OutlineArtifact(
            id=support._new_id("outline"),
            topic=topic,
            outline_version=1,
            sections=sections,
            required_section_ids=[str(item["id"]) for item in sections],
            question_section_map=question_map,
        ).to_dict()

    def decide_section_action(
        self,
        *,
        outline: dict[str, Any],
        section_status_map: dict[str, Any],
        budget_stop_reason: str = "",
        aggregate_summary: dict[str, Any] | None = None,
        reportable_section_count: int = 0,
    ) -> SupervisorDecision:
        aggregate = aggregate_summary or {}
        if budget_stop_reason and not reportable_section_count and not bool(aggregate.get("report_ready")):
            return SupervisorDecision(
                action=SupervisorAction.STOP,
                reasoning=budget_stop_reason,
            )

        if reportable_section_count or bool(aggregate.get("report_ready")):
            return SupervisorDecision(
                action=SupervisorAction.REPORT,
                reasoning="已有可报告章节，可进入最佳努力报告生成",
            )

        required_ids = [
            str(item).strip()
            for item in (outline.get("required_section_ids") or [])
            if str(item).strip()
        ]
        pending = [
            section_id
            for section_id in required_ids
            if str((section_status_map or {}).get(section_id) or "planned").strip()
            not in {"certified", "blocked", "failed"}
        ]
        blocked = [
            section_id
            for section_id in required_ids
            if str((section_status_map or {}).get(section_id) or "").strip() == "blocked"
        ]
        if blocked and not reportable_section_count:
            return SupervisorDecision(
                action=SupervisorAction.STOP,
                reasoning="存在阻塞的 required section，当前无法继续汇总",
                request_ids=blocked,
            )
        if pending:
            return SupervisorDecision(
                action=SupervisorAction.DISPATCH,
                reasoning="仍有未认证的 section，需要继续研究或修订",
                request_ids=pending,
            )
        return SupervisorDecision(
            action=SupervisorAction.REPORT,
            reasoning="所有 required section 已认证，可以进入最终报告生成",
        )


__all__ = [
    "ResearchSupervisor",
    "SupervisorAction",
    "SupervisorDecision",
]
