from __future__ import annotations

from typing import Any, Mapping, TypedDict

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
    started_at: str
    ended_at: str
    routing_reasoning: str
    routing_confidence: float
    tool_approved: bool
    pending_tool_calls: list[dict[str, Any]]
    tool_call_count: int
    tool_call_limit: int
    enabled_tools: dict[str, bool]
    cancel_token_id: str | None
    is_cancelled: bool
    errors: list[str]
    last_error: str


class ResearchState(TypedDict, total=False):
    scraped_content: list[dict[str, Any]]
    code_results: list[dict[str, Any]]
    summary_notes: list[str]
    sources: list[dict[str, str]]
    research_topology: dict[str, Any]
    current_branch_id: str | None
    domain: str
    domain_config: dict[str, Any]
    sub_agent_contexts: dict[str, dict[str, Any]]


class RuntimeSnapshot(TypedDict, total=False):
    deep_runtime: DeepRuntimeSnapshot
    total_input_tokens: int
    total_output_tokens: int


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
        "started_at": str(data.get("started_at") or "").strip(),
        "ended_at": str(data.get("ended_at") or "").strip(),
        "routing_reasoning": str(data.get("routing_reasoning") or "").strip(),
        "routing_confidence": float(data.get("routing_confidence") or 0.0),
        "tool_approved": bool(data.get("tool_approved")),
        "pending_tool_calls": list(data.get("pending_tool_calls") or []),
        "tool_call_count": int(data.get("tool_call_count") or 0),
        "tool_call_limit": int(data.get("tool_call_limit") or 0),
        "enabled_tools": dict(data.get("enabled_tools") or {}),
        "cancel_token_id": data.get("cancel_token_id"),
        "is_cancelled": bool(data.get("is_cancelled")),
        "errors": list(data.get("errors") or []),
        "last_error": str(data.get("last_error") or ""),
    }


def build_research_state(state: Mapping[str, Any] | None) -> ResearchState:
    data = state or {}
    return {
        "scraped_content": list(data.get("scraped_content") or []),
        "code_results": list(data.get("code_results") or []),
        "summary_notes": list(data.get("summary_notes") or []),
        "sources": list(data.get("sources") or []),
        "research_topology": dict(data.get("research_topology") or {}),
        "current_branch_id": data.get("current_branch_id"),
        "domain": str(data.get("domain") or "").strip(),
        "domain_config": dict(data.get("domain_config") or {}),
        "sub_agent_contexts": dict(data.get("sub_agent_contexts") or {}),
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
        "total_input_tokens": int(data.get("total_input_tokens") or 0),
        "total_output_tokens": int(data.get("total_output_tokens") or 0),
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
    merged = dict(state or {})
    merged.update(dict(updates or {}))
    projected = dict(updates or {})
    projected.update(build_state_slices(merged))
    return projected
