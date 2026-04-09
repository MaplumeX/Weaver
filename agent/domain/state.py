from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict


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
    short_term_context: dict[str, Any]
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


def project_state_updates(
    state: Mapping[str, Any] | None,
    updates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    _ = state
    return dict(updates or {})
