"""
Graph-friendly task dispatch helpers for the multi-agent deep runtime.
"""

from __future__ import annotations

from typing import Any

from agent.runtime.deep.multi_agent import support
from agent.runtime.deep.multi_agent.schema import BranchBrief, ResearchTask


def _coerce_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def build_tasks_from_plan(
    runtime: Any,
    plan_items: list[dict[str, Any]],
    *,
    context_id: str,
    branch_id: str | None = None,
) -> list[ResearchTask]:
    tasks: list[ResearchTask] = []
    for item in plan_items or []:
        if not isinstance(item, dict):
            continue
        objective = str(item.get("objective") or item.get("title") or item.get("query") or "").strip()
        query_hints = _coerce_list(item.get("query_hints"))
        query = str(item.get("query") or (query_hints[0] if query_hints else objective)).strip()
        if not objective:
            continue
        aspect = str(item.get("aspect") or "").strip()
        priority = int(item.get("priority") or len(tasks) + 1)
        task_kind = str(item.get("task_kind") or "branch_research").strip() or "branch_research"
        allowed_tools = _coerce_list(item.get("allowed_tools")) or ["search", "read", "extract", "synthesize"]
        acceptance_criteria = _coerce_list(item.get("acceptance_criteria"))
        input_artifact_ids = _coerce_list(item.get("input_artifact_ids"))
        output_artifact_types = _coerce_list(item.get("output_artifact_types")) or [
            "source_candidate",
            "fetched_document",
            "evidence_passage",
            "branch_synthesis",
        ]
        title = str(item.get("title") or aspect or objective).strip() or objective
        task_branch_id = str(item.get("branch_id") or support._new_id("branch")).strip()
        tasks.append(
            ResearchTask(
                id=support._new_id("task"),
                goal=title,
                query=query,
                priority=priority,
                objective=objective,
                task_kind=task_kind,
                acceptance_criteria=acceptance_criteria,
                allowed_tools=allowed_tools,
                input_artifact_ids=input_artifact_ids,
                output_artifact_types=output_artifact_types,
                query_hints=query_hints or ([query] if query else []),
                stage="planned",
                title=title,
                aspect=aspect,
                branch_id=task_branch_id,
                parent_task_id=str(item.get("parent_task_id") or "").strip() or None,
                parent_context_id=context_id,
            )
        )
    return tasks


def build_briefs_from_tasks(
    topic: str,
    tasks: list[ResearchTask],
    *,
    parent_branch_id: str | None = None,
    context_id: str | None = None,
) -> list[BranchBrief]:
    briefs: list[BranchBrief] = []
    for task in tasks:
        if not task.branch_id:
            continue
        briefs.append(
            BranchBrief(
                id=task.branch_id,
                topic=topic,
                summary=task.title or task.objective or task.goal,
                objective=task.objective or task.goal,
                task_kind=task.task_kind,
                acceptance_criteria=list(task.acceptance_criteria),
                allowed_tools=list(task.allowed_tools),
                input_artifact_ids=list(task.input_artifact_ids),
                context_id=context_id,
                parent_branch_id=parent_branch_id,
                parent_task_id=task.parent_task_id,
                latest_task_id=task.id,
                current_stage=task.stage,
            )
        )
    return briefs


def claim_ready_task_payloads(runtime: Any, current_iteration: int) -> list[dict[str, Any]]:
    runtime.budget_stop_reason = support._budget_stop_reason(
        start_ts=runtime.start_ts,
        searches_used=runtime.searches_used,
        tokens_used=runtime.tokens_used,
        max_seconds=runtime.max_seconds,
        max_tokens=runtime.max_tokens,
        max_searches=runtime.max_searches,
    )
    if runtime.budget_stop_reason:
        return []

    remaining_search_slots = runtime.parallel_workers
    if runtime.max_searches > 0:
        remaining_search_slots = min(
            remaining_search_slots,
            max(0, runtime.max_searches - runtime.searches_used),
        )
    if remaining_search_slots <= 0:
        runtime.budget_stop_reason = "search_budget_exceeded"
        return []

    agent_ids = [runtime.next_agent_id("researcher") for _ in range(remaining_search_slots)]
    claimed = runtime.task_queue.claim_ready_tasks(limit=remaining_search_slots, agent_ids=agent_ids)
    if not claimed:
        return []

    for task in claimed:
        runtime._emit_task_update(task=task, status=task.status, attempt=task.attempts)

    return [
        {
            "task": task.to_dict(),
            "agent_id": task.assigned_agent_id,
            "iteration": current_iteration,
            "branch_id": task.branch_id,
            "attempt": task.attempts,
        }
        for task in claimed
    ]


def sort_worker_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(item: dict[str, Any]) -> tuple[Any, ...]:
        task = item.get("task") or {}
        return (
            int(task.get("priority", 9999) or 9999),
            str(task.get("created_at") or ""),
            str(task.get("id") or ""),
        )

    return sorted((item for item in payloads if isinstance(item, dict)), key=_key)


__all__ = [
    "build_briefs_from_tasks",
    "build_tasks_from_plan",
    "claim_ready_task_payloads",
    "sort_worker_payloads",
]
