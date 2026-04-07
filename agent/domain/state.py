from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from agent.domain.execution import execution_mode_from_public_mode


class DeepRuntimeSnapshot(TypedDict, total=False):
    engine: str
    task_queue: dict[str, Any]
    artifact_store: dict[str, Any]
    runtime_state: dict[str, Any]
    agent_runs: list[dict[str, Any]]


class ConversationState(TypedDict, total=False):
    input: str
    images: list[dict[str, Any]]
    user_id: str
    thread_id: str
    agent_id: str
    messages: list[Any]
    final_report: str
    draft_report: str


class ExecutionState(TypedDict, total=False):
    mode: str
    route: str
    status: str
    is_complete: bool
    available_tools: list[str]
    blocked_tools: list[str]
    selected_tools: list[str]
    cancel_token_id: str | None
    is_cancelled: bool
    errors: list[str]


class ResearchState(TypedDict, total=False):
    scraped_content: list[dict[str, Any]]
    summary_notes: list[str]
    sources: list[dict[str, str]]
    research_topology: dict[str, Any]
    domain: str
    domain_config: dict[str, Any]
    sub_agent_contexts: dict[str, dict[str, Any]]
    memory_context: dict[str, list[str]]
    assistant_draft: str
    needs_tools: bool


class RuntimeSnapshot(TypedDict, total=False):
    deep_runtime: DeepRuntimeSnapshot


def build_deep_runtime_snapshot(
    *,
    engine: str,
    task_queue: Mapping[str, Any] | None = None,
    artifact_store: Mapping[str, Any] | None = None,
    runtime_state: Mapping[str, Any] | None = None,
    agent_runs: list[dict[str, Any]] | None = None,
) -> DeepRuntimeSnapshot:
    return {
        "engine": str(engine or "").strip(),
        "task_queue": dict(task_queue or {}),
        "artifact_store": dict(artifact_store or {}),
        "runtime_state": dict(runtime_state or {}),
        "agent_runs": list(agent_runs or []),
    }


def build_conversation_state(state: Mapping[str, Any] | None) -> ConversationState:
    data = state or {}
    return {
        "input": str(data.get("input") or "").strip(),
        "images": list(data.get("images") or []),
        "user_id": str(data.get("user_id") or "").strip(),
        "thread_id": str(data.get("thread_id") or "").strip(),
        "agent_id": str(data.get("agent_id") or "").strip(),
        "messages": list(data.get("messages") or []),
        "final_report": str(data.get("final_report") or ""),
        "draft_report": str(data.get("draft_report") or ""),
    }


def build_execution_state(state: Mapping[str, Any] | None) -> ExecutionState:
    data = state or {}
    route = str(data.get("route") or "").strip()
    mode = execution_mode_from_public_mode(route or data.get("mode")).value
    return {
        "mode": mode,
        "route": route or "agent",
        "status": str(data.get("status") or "").strip(),
        "is_complete": bool(data.get("is_complete")),
        "available_tools": list(data.get("available_tools") or []),
        "blocked_tools": list(data.get("blocked_tools") or []),
        "selected_tools": list(data.get("selected_tools") or []),
        "cancel_token_id": data.get("cancel_token_id"),
        "is_cancelled": bool(data.get("is_cancelled")),
        "errors": list(data.get("errors") or []),
    }


def build_research_state(state: Mapping[str, Any] | None) -> ResearchState:
    data = state or {}
    return {
        "scraped_content": list(data.get("scraped_content") or []),
        "summary_notes": list(data.get("summary_notes") or []),
        "sources": list(data.get("sources") or []),
        "research_topology": dict(data.get("research_topology") or {}),
        "domain": str(data.get("domain") or "").strip(),
        "domain_config": dict(data.get("domain_config") or {}),
        "sub_agent_contexts": dict(data.get("sub_agent_contexts") or {}),
        "memory_context": dict(data.get("memory_context") or {"stored": [], "relevant": []}),
        "assistant_draft": str(data.get("assistant_draft") or ""),
        "needs_tools": bool(data.get("needs_tools")),
    }


def build_runtime_snapshot(state: Mapping[str, Any] | None) -> RuntimeSnapshot:
    data = state or {}
    nested = data.get("deep_runtime")
    nested_dict = nested if isinstance(nested, Mapping) else {}
    return {
        "deep_runtime": build_deep_runtime_snapshot(
            engine=str(nested_dict.get("engine") or "").strip(),
            task_queue=nested_dict.get("task_queue") if isinstance(nested_dict.get("task_queue"), Mapping) else {},
            artifact_store=(
                nested_dict.get("artifact_store")
                if isinstance(nested_dict.get("artifact_store"), Mapping)
                else {}
            ),
            runtime_state=(
                nested_dict.get("runtime_state")
                if isinstance(nested_dict.get("runtime_state"), Mapping)
                else {}
            ),
            agent_runs=(
                list(nested_dict.get("agent_runs") or [])
                if isinstance(nested_dict.get("agent_runs"), list)
                else []
            ),
        ),
    }


def build_state_slices(state: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "conversation_state": build_conversation_state(state),
        "execution_state": build_execution_state(state),
        "research_state": build_research_state(state),
        "runtime_snapshot": build_runtime_snapshot(state),
    }


def project_state_updates(
    state: Mapping[str, Any] | None,
    updates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    _ = state
    return dict(updates or {})
