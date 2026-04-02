"""
Deep Research supervisor agent.

Unifies planning and loop-control decisions for the multi-agent deep runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.language_models import BaseChatModel

from .coordinator import CoordinatorAction, ResearchCoordinator
from .planner import ResearchPlanner


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
        self._coordinator = ResearchCoordinator(llm, self.config)

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

        coordinator_decision = self._coordinator.decide_next_action(
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
            verification_summary=verification_summary,
        )
        action = self._map_coordinator_action(
            coordinator_decision.action,
            quality_gap_count=quality_gap_count,
        )
        return SupervisorDecision(
            action=action,
            reasoning=coordinator_decision.reasoning,
            priority_topics=list(coordinator_decision.priority_topics),
            request_ids=normalized_request_ids,
        )

    def _map_coordinator_action(
        self,
        action: CoordinatorAction,
        *,
        quality_gap_count: int,
    ) -> SupervisorAction:
        if action == CoordinatorAction.COMPLETE or action == CoordinatorAction.SYNTHESIZE:
            return SupervisorAction.REPORT
        if action == CoordinatorAction.PLAN:
            return SupervisorAction.PLAN if quality_gap_count <= 0 else SupervisorAction.REPLAN
        if action == CoordinatorAction.REFLECT:
            return SupervisorAction.REPLAN if quality_gap_count > 0 else SupervisorAction.DISPATCH
        if action == CoordinatorAction.RESEARCH:
            return SupervisorAction.REPLAN if quality_gap_count > 0 else SupervisorAction.DISPATCH
        return SupervisorAction.DISPATCH


__all__ = [
    "ResearchSupervisor",
    "SupervisorAction",
    "SupervisorDecision",
]
