"""
Event helpers used by the multi-agent deep runtime.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agent.contracts.events import ToolEventType, get_emitter_sync
from agent.runtime.deep.multi_agent.schema import AgentRole, ResearchTask

logger = logging.getLogger(__name__)


def emit(emitter: Any, event_type: ToolEventType | str, payload: Dict[str, Any]) -> None:
    if not emitter:
        return
    try:
        emitter.emit_sync(event_type, payload)
    except Exception as exc:
        logger.debug("[deepsearch-multi-agent] failed to emit %s: %s", event_type, exc)


def emit_task_update(runtime: Any, *, task: ResearchTask, status: str) -> None:
    payload = {
        "task_id": task.id,
        "status": status,
        "title": task.title or task.goal,
        "query": task.query,
        "parent_context_id": task.parent_context_id,
        "agent_id": task.assigned_agent_id,
        "priority": task.priority,
    }
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
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    summary: Optional[str] = None,
    source_url: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "status": status,
    }
    if task_id:
        payload["task_id"] = task_id
    if agent_id:
        payload["agent_id"] = agent_id
    if summary:
        payload["summary"] = summary
    if source_url:
        payload["source_url"] = source_url
    emit(runtime.emitter, ToolEventType.RESEARCH_ARTIFACT_UPDATE, payload)


def emit_agent_start(
    runtime: Any,
    *,
    agent_id: str,
    role: AgentRole,
    phase: str,
    task_id: Optional[str] = None,
    iteration: Optional[int] = None,
) -> None:
    payload: Dict[str, Any] = {
        "agent_id": agent_id,
        "role": role,
        "phase": phase,
    }
    if task_id:
        payload["task_id"] = task_id
    if iteration is not None:
        payload["iteration"] = iteration
    emit(runtime.emitter, ToolEventType.RESEARCH_AGENT_START, payload)


def emit_agent_complete(
    runtime: Any,
    *,
    agent_id: str,
    role: AgentRole,
    phase: str,
    status: str,
    task_id: Optional[str] = None,
    iteration: Optional[int] = None,
    summary: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {
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
    emit(runtime.emitter, ToolEventType.RESEARCH_AGENT_COMPLETE, payload)


def emit_decision(
    runtime: Any,
    *,
    decision_type: str,
    reason: str,
    iteration: Optional[int] = None,
    coverage: Optional[float] = None,
    gap_count: Optional[int] = None,
) -> None:
    payload: Dict[str, Any] = {
        "decision_type": decision_type,
        "reason": reason,
    }
    if iteration is not None:
        payload["iteration"] = iteration
    if coverage is not None:
        payload["coverage"] = coverage
    if gap_count is not None:
        payload["gap_count"] = gap_count
    emit(runtime.emitter, ToolEventType.RESEARCH_DECISION, payload)


def emit_research_tree_update(runtime: Any) -> None:
    emit(
        runtime.emitter,
        ToolEventType.RESEARCH_TREE_UPDATE,
        {
            "tree": runtime._research_tree_snapshot(),
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
    "emit_research_tree_update",
    "emit_task_update",
    "get_emitter_sync",
]
