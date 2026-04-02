"""
Event helpers used by the multi-agent deep runtime.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.contracts.events import ToolEventType, get_emitter_sync
from agent.runtime.deep.schema import AgentRole, ResearchTask

logger = logging.getLogger(__name__)


def emit(emitter: Any, event_type: ToolEventType | str, payload: dict[str, Any]) -> None:
    if not emitter:
        return
    try:
        emitter.emit_sync(event_type, payload)
    except Exception as exc:
        logger.debug("[deep-research-multi-agent] failed to emit %s: %s", event_type, exc)


def _graph_context(
    runtime: Any,
    *,
    node_id: str | None = None,
    branch_id: str | None = None,
    task_id: str | None = None,
    attempt: int | None = None,
    parent_task_id: str | None = None,
    parent_branch_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"engine": "multi_agent"}
    graph_run_id = getattr(runtime, "graph_run_id", None)
    if graph_run_id:
        payload["graph_run_id"] = graph_run_id
    graph_attempt = getattr(runtime, "graph_attempt", None)
    if isinstance(graph_attempt, int):
        payload["graph_attempt"] = graph_attempt
    payload["resumed_from_checkpoint"] = bool(
        getattr(runtime, "resumed_from_checkpoint", False)
        or getattr(runtime, "cfg", {}).get("resumed_from_checkpoint")
    )
    resolved_node_id = node_id or getattr(runtime, "current_node_id", None)
    if resolved_node_id:
        payload["node_id"] = resolved_node_id
    resolved_branch_id = branch_id or getattr(runtime, "root_branch_id", None)
    if resolved_branch_id:
        payload["branch_id"] = resolved_branch_id
    if task_id:
        payload["task_id"] = task_id
    if attempt is not None:
        payload["attempt"] = attempt
    if parent_task_id:
        payload["parent_task_id"] = parent_task_id
    if parent_branch_id:
        payload["parent_branch_id"] = parent_branch_id
    return payload


def emit_task_update(
    runtime: Any,
    *,
    task: ResearchTask,
    status: str,
    attempt: int | None = None,
    reason: str | None = None,
) -> None:
    payload = {
        **_graph_context(
            runtime,
            task_id=task.id,
            branch_id=task.branch_id,
            attempt=attempt if attempt is not None else task.attempts,
            parent_task_id=task.parent_task_id,
        ),
        "task_id": task.id,
        "status": status,
        "title": task.title or task.goal,
        "objective_summary": task.objective or task.goal,
        "task_kind": task.task_kind,
        "stage": task.stage,
        "query": task.query,
        "query_hints": list(task.query_hints),
        "branch_id": task.branch_id,
        "input_artifact_ids": list(task.input_artifact_ids),
        "parent_context_id": task.parent_context_id,
        "agent_id": task.assigned_agent_id,
        "priority": task.priority,
    }
    if reason:
        payload["reason"] = reason
    emit(runtime.emitter, ToolEventType.RESEARCH_TASK_UPDATE, payload)
    emit(
        runtime.emitter,
        ToolEventType.TASK_UPDATE,
        {
            "id": task.id,
            "status": status,
            "title": task.title or task.goal,
        },
    )


def emit_artifact_update(
    runtime: Any,
    *,
    artifact_id: str,
    artifact_type: str,
    status: str,
    task_id: str | None = None,
    branch_id: str | None = None,
    agent_id: str | None = None,
    summary: str | None = None,
    source_url: str | None = None,
    task_kind: str | None = None,
    stage: str | None = None,
    validation_stage: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        **_graph_context(runtime, task_id=task_id, branch_id=branch_id or getattr(runtime, "root_branch_id", None)),
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "status": status,
    }
    if task_id:
        payload["task_id"] = task_id
    if branch_id:
        payload["branch_id"] = branch_id
    if agent_id:
        payload["agent_id"] = agent_id
    if summary:
        payload["summary"] = summary
    if source_url:
        payload["source_url"] = source_url
    if task_kind:
        payload["task_kind"] = task_kind
    if stage:
        payload["stage"] = stage
    if validation_stage:
        payload["validation_stage"] = validation_stage
    if isinstance(extra, dict):
        payload.update(extra)
    emit(runtime.emitter, ToolEventType.RESEARCH_ARTIFACT_UPDATE, payload)


def emit_agent_start(
    runtime: Any,
    *,
    agent_id: str,
    role: AgentRole,
    phase: str,
    task_id: str | None = None,
    iteration: int | None = None,
    branch_id: str | None = None,
    attempt: int | None = None,
    task_kind: str | None = None,
    stage: str | None = None,
    validation_stage: str | None = None,
    objective_summary: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        **_graph_context(
            runtime,
            task_id=task_id,
            branch_id=branch_id,
            attempt=attempt,
        ),
        "agent_id": agent_id,
        "role": role,
        "phase": phase,
    }
    if task_id:
        payload["task_id"] = task_id
    if iteration is not None:
        payload["iteration"] = iteration
    if task_kind:
        payload["task_kind"] = task_kind
    if stage:
        payload["stage"] = stage
    if validation_stage:
        payload["validation_stage"] = validation_stage
    if objective_summary:
        payload["objective_summary"] = objective_summary
    emit(runtime.emitter, ToolEventType.RESEARCH_AGENT_START, payload)


def emit_agent_complete(
    runtime: Any,
    *,
    agent_id: str,
    role: AgentRole,
    phase: str,
    status: str,
    task_id: str | None = None,
    iteration: int | None = None,
    summary: str | None = None,
    branch_id: str | None = None,
    attempt: int | None = None,
    task_kind: str | None = None,
    stage: str | None = None,
    validation_stage: str | None = None,
    objective_summary: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        **_graph_context(
            runtime,
            task_id=task_id,
            branch_id=branch_id,
            attempt=attempt,
        ),
        "agent_id": agent_id,
        "role": role,
        "phase": phase,
        "status": status,
    }
    if task_id:
        payload["task_id"] = task_id
    if iteration is not None:
        payload["iteration"] = iteration
    if summary:
        payload["summary"] = summary
    if task_kind:
        payload["task_kind"] = task_kind
    if stage:
        payload["stage"] = stage
    if validation_stage:
        payload["validation_stage"] = validation_stage
    if objective_summary:
        payload["objective_summary"] = objective_summary
    emit(runtime.emitter, ToolEventType.RESEARCH_AGENT_COMPLETE, payload)


def emit_decision(
    runtime: Any,
    *,
    decision_type: str,
    reason: str,
    iteration: int | None = None,
    coverage: float | None = None,
    gap_count: int | None = None,
    attempt: int | None = None,
    branch_id: str | None = None,
    task_id: str | None = None,
    task_kind: str | None = None,
    stage: str | None = None,
    validation_stage: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        **_graph_context(runtime, attempt=attempt, branch_id=branch_id, task_id=task_id),
        "decision_type": decision_type,
        "reason": reason,
    }
    if iteration is not None:
        payload["iteration"] = iteration
    if coverage is not None:
        payload["coverage"] = coverage
    if gap_count is not None:
        payload["gap_count"] = gap_count
    if task_kind:
        payload["task_kind"] = task_kind
    if stage:
        payload["stage"] = stage
    if validation_stage:
        payload["validation_stage"] = validation_stage
    if isinstance(extra, dict):
        payload.update(extra)
    emit(runtime.emitter, ToolEventType.RESEARCH_DECISION, payload)


def emit_deep_research_topology_update(runtime: Any) -> None:
    emit(
        runtime.emitter,
        ToolEventType.DEEP_RESEARCH_TOPOLOGY_UPDATE,
        {
            "topology": runtime._research_topology_snapshot(),
            "engine": "multi_agent",
            "quality": runtime._quality_summary(None),
        },
    )


__all__ = [
    "ToolEventType",
    "emit",
    "emit_agent_complete",
    "emit_agent_start",
    "emit_artifact_update",
    "emit_decision",
    "emit_deep_research_topology_update",
    "emit_task_update",
    "get_emitter_sync",
]
