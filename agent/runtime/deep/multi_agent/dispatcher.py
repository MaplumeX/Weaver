"""
Graph-friendly task dispatch helpers for the multi-agent deep runtime.
"""

from __future__ import annotations

from typing import Any

from agent.runtime.deep.multi_agent import support
from agent.runtime.deep.multi_agent.schema import ResearchTask


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
        query = str(item.get("query") or "").strip()
        if not query:
            continue
        aspect = str(item.get("aspect") or "").strip()
        priority = int(item.get("priority") or len(tasks) + 1)
        title = aspect or query
        tasks.append(
            ResearchTask(
                id=support._new_id("task"),
                goal=title,
                query=query,
                priority=priority,
                title=title,
                aspect=aspect,
                branch_id=branch_id,
                parent_context_id=context_id,
            )
        )
    return tasks


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


__all__ = ["build_tasks_from_plan", "claim_ready_task_payloads", "sort_worker_payloads"]
