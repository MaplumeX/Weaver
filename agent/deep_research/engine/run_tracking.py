"""Agent-run tracking and event emission helpers for Deep Research."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from agent.contracts.events import ToolEventType
from agent.deep_research.engine import runtime_context
from agent.deep_research.engine.section_logic import _branch_title
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import AgentRunRecord, ResearchTask, _now_iso

EmitFn = Callable[[ToolEventType | str, dict[str, Any]], None]


def next_agent_id(role: str, runtime_state: dict[str, Any]) -> str:
    counters = copy.deepcopy(runtime_state.get("role_counters") or {})
    counters[role] = int(counters.get(role, 0) or 0) + 1
    runtime_state["role_counters"] = counters
    return f"{role}-{counters[role]}"


def start_agent_run(
    *,
    runtime_state: dict[str, Any],
    current_iteration: int,
    graph_run_id: str,
    emit: EmitFn,
    role: str,
    phase: str,
    task_id: str | None = None,
    section_id: str | None = None,
    branch_id: str | None = None,
    stage: str = "",
    objective_summary: str = "",
    attempt: int = 1,
    requested_tools: list[str] | None = None,
) -> dict[str, Any]:
    agent_id = next_agent_id(role, runtime_state)
    policy_snapshot = runtime_context._deep_research_role_tool_policy_snapshot(
        role,
        allowed_tools=requested_tools,
    )
    requested_tool_snapshot = (
        [str(item).strip() for item in (requested_tools or []) if str(item).strip()]
        if requested_tools is not None
        else list(policy_snapshot.get("requested_tools") or [])
    )
    role_tool_policies = dict(runtime_state.get("role_tool_policies") or {})
    role_tool_policies[role] = copy.deepcopy(policy_snapshot)
    role_tool_policies[role]["requested_tools"] = requested_tool_snapshot
    runtime_state["role_tool_policies"] = role_tool_policies
    record = AgentRunRecord(
        id=_new_id("agent_run"),
        role=role,  # type: ignore[arg-type]
        phase=phase,
        status="running",
        agent_id=agent_id,
        graph_run_id=graph_run_id,
        node_id=phase,
        task_id=task_id,
        section_id=section_id,
        branch_id=branch_id,
        stage=stage,
        objective_summary=objective_summary,
        attempt=attempt,
        requested_tools=requested_tool_snapshot,
        resolved_tools=list(policy_snapshot.get("allowed_tool_names") or []),
    ).to_dict()
    emit(
        ToolEventType.RESEARCH_AGENT_START,
        {
            "agent_id": agent_id,
            "role": role,
            "phase": phase,
            "task_id": task_id,
            "section_id": section_id,
            "branch_id": branch_id,
            "iteration": max(1, current_iteration or 1),
            "attempt": attempt,
            "stage": stage,
            "objective_summary": objective_summary,
            "requested_tools": requested_tool_snapshot,
            "resolved_tools": list(policy_snapshot.get("allowed_tool_names") or []),
        },
    )
    return record


def finish_agent_run(
    *,
    agent_runs: list[dict[str, Any]],
    current_iteration: int,
    record: dict[str, Any],
    status: str,
    summary: str,
    emit: EmitFn,
    stage: str = "",
) -> None:
    record["status"] = status
    record["ended_at"] = _now_iso()
    record["summary"] = summary[:240]
    if stage:
        record["stage"] = stage
    agent_runs.append(copy.deepcopy(record))
    emit(
        ToolEventType.RESEARCH_AGENT_COMPLETE,
        {
            "agent_id": record.get("agent_id"),
            "role": record.get("role"),
            "phase": record.get("phase"),
            "task_id": record.get("task_id"),
            "section_id": record.get("section_id"),
            "branch_id": record.get("branch_id"),
            "iteration": max(1, current_iteration or 1),
            "attempt": record.get("attempt", 1),
            "status": status,
            "summary": summary[:240],
            "stage": stage or record.get("stage") or "",
            "requested_tools": list(record.get("requested_tools") or []),
            "resolved_tools": list(record.get("resolved_tools") or []),
        },
    )


def emit_task_update(
    *,
    task: ResearchTask,
    status: str,
    iteration: int,
    emit: EmitFn,
    reason: str = "",
) -> None:
    payload = {
        "task_id": task.id,
        "status": status,
        "title": _branch_title(task),
        "objective_summary": task.objective or task.goal,
        "task_kind": task.task_kind,
        "stage": task.stage,
        "query": task.query,
        "query_hints": list(task.query_hints or []),
        "section_id": task.section_id,
        "branch_id": task.branch_id,
        "priority": task.priority,
        "iteration": max(1, iteration),
        "attempt": task.attempts,
    }
    if reason:
        payload["reason"] = reason
    emit(ToolEventType.RESEARCH_TASK_UPDATE, payload)
    emit(
        ToolEventType.TASK_UPDATE,
        {"id": task.id, "status": status, "title": _branch_title(task)},
    )


def emit_artifact_update(
    *,
    artifact_id: str,
    artifact_type: str,
    summary: str,
    emit: EmitFn,
    status: str = "completed",
    task_id: str | None = None,
    section_id: str | None = None,
    branch_id: str | None = None,
    iteration: int = 1,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "status": status,
        "task_id": task_id,
        "section_id": section_id,
        "branch_id": branch_id,
        "summary": summary[:180],
        "iteration": max(1, iteration),
    }
    if isinstance(extra, dict):
        payload.update(extra)
    emit(ToolEventType.RESEARCH_ARTIFACT_UPDATE, payload)


def emit_decision(
    *,
    decision_type: str,
    reason: str,
    iteration: int,
    emit: EmitFn,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "decision_type": decision_type,
        "reason": reason,
        "iteration": max(1, iteration),
    }
    if isinstance(extra, dict):
        payload.update(extra)
    emit(ToolEventType.RESEARCH_DECISION, payload)
