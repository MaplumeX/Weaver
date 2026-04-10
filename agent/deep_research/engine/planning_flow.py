"""Planning and dispatch helpers for the Deep Research engine."""

from __future__ import annotations

import copy
from typing import Any


def run_outline_plan_step(
    *,
    parts: Any,
    record: dict[str, Any],
    topic: str,
    graph_attempt: int,
    supervisor: Any,
    fallback_outline_plan_fn: Any,
    outline_sections_fn: Any,
    build_outline_tasks_fn: Any,
    build_plan_artifact_fn: Any,
    emit_artifact_update_fn: Any,
    emit_task_update_fn: Any,
    emit_decision_fn: Any,
    finish_agent_run_fn: Any,
    patch_fn: Any,
    new_id_fn: Any,
) -> dict[str, Any]:
    approved_scope = copy.deepcopy(parts.runtime_state.get("approved_scope_draft") or {})
    if not approved_scope:
        return patch_fn(parts, next_step="scope_review")
    scope = parts.artifact_store.scope()
    if not scope:
        return patch_fn(parts, next_step="research_brief")
    if parts.artifact_store.outline():
        if parts.task_queue.ready_count() > 0:
            return patch_fn(parts, next_step="dispatch")
        return patch_fn(parts, next_step="reviewer")

    if hasattr(supervisor, "create_outline_plan"):
        outline = supervisor.create_outline_plan(topic, approved_scope=scope)
    else:
        outline = fallback_outline_plan_fn(scope)
    sections = outline_sections_fn(outline)
    tasks = build_outline_tasks_fn(outline=outline, scope=scope)
    if not tasks:
        parts.runtime_state["terminal_status"] = "blocked"
        parts.runtime_state["terminal_reason"] = "outline plan produced no executable tasks"
        finish_agent_run_fn(parts, record, status="completed", summary=parts.runtime_state["terminal_reason"])
        return patch_fn(parts, next_step="finalize")

    parts.artifact_store.set_outline(outline)
    parts.runtime_state["outline_id"] = str(outline.get("id") or "")
    parts.runtime_state["section_status_map"] = {
        str(section.get("id") or ""): "planned"
        for section in sections
        if str(section.get("id") or "")
    }
    parts.task_queue.enqueue(tasks)
    plan_artifact = build_plan_artifact_fn(scope, tasks)
    plan_artifact["outline_id"] = str(outline.get("id") or "")
    plan_artifact["required_section_ids"] = list(outline.get("required_section_ids") or [])
    parts.artifact_store.set_plan(plan_artifact)
    parts.runtime_state["plan_id"] = str(plan_artifact.get("id") or "")
    parts.runtime_state["supervisor_phase"] = "outline_plan"
    emit_artifact_update_fn(
        artifact_id=str(outline.get("id") or new_id_fn("outline")),
        artifact_type="outline",
        summary=f"generated {len(sections)} required sections",
        iteration=max(1, parts.current_iteration or 1),
        extra={
            "required_section_ids": list(outline.get("required_section_ids") or []),
            "section_count": len(sections),
        },
    )
    emit_artifact_update_fn(
        artifact_id=str(plan_artifact.get("id") or new_id_fn("plan")),
        artifact_type="plan",
        summary=f"generated {len(tasks)} section tasks",
        iteration=max(1, parts.current_iteration or 1),
    )
    for task in tasks:
        emit_task_update_fn(task, task.status, iteration=max(1, parts.current_iteration or 1))
    emit_decision_fn(
        "outline_plan",
        f"generated {len(sections)} required sections",
        iteration=max(1, parts.current_iteration or 1),
    )
    finish_agent_run_fn(parts, record, status="completed", summary=f"generated {len(sections)} sections")
    return patch_fn(parts, next_step="dispatch")


def run_dispatch_step(
    *,
    parts: Any,
    parallel_workers: int,
    budget_stop_reason_fn: Any,
    next_agent_id_fn: Any,
    emit_decision_fn: Any,
    emit_task_update_fn: Any,
    patch_fn: Any,
) -> dict[str, Any]:
    budget_stop_reason = budget_stop_reason_fn(parts.runtime_state)
    if budget_stop_reason:
        parts.runtime_state["budget_stop_reason"] = budget_stop_reason
        emit_decision_fn("budget_stop", budget_stop_reason, iteration=max(1, parts.current_iteration or 1))
        return patch_fn(parts, next_step="reviewer")

    if parts.task_queue.ready_count() == 0:
        return patch_fn(parts, next_step="reviewer")

    parts.current_iteration += 1
    parts.runtime_state["current_iteration"] = parts.current_iteration
    claimed = parts.task_queue.claim_ready_tasks(
        limit=parallel_workers,
        agent_ids=[next_agent_id_fn("researcher", parts.runtime_state) for _ in range(parallel_workers)],
    )
    for task in claimed:
        emit_task_update_fn(task, "in_progress", iteration=parts.current_iteration)
    emit_decision_fn("research", "dispatch ready section tasks", iteration=parts.current_iteration)
    return patch_fn(
        parts,
        next_step="reviewer",
        pending_worker_tasks=[task.to_dict() for task in claimed],
        worker_results=[{"__reset__": True}],
    )
