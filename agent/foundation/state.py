import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from agent.foundation.message_utils import summarize_messages
from agent.foundation.state_contracts import (
    ConversationState,
    DeepRuntimeSnapshot,
    ExecutionState,
    ResearchState,
    RuntimeSnapshot,
)
from agent.foundation.state_contracts import (
    build_deep_runtime_snapshot as _build_deep_runtime_snapshot,
)
from agent.foundation.state_contracts import (
    project_state_updates as _project_state_updates,
)
from common.config import settings

from .middleware import maybe_strip_tool_messages


def capped_add_messages(
    existing: list[BaseMessage] | None, new: list[BaseMessage] | None
) -> list[BaseMessage]:
    """
    Aggregate messages and trim to keep context bounded.

    Keeps the first N (usually system/setup) and last M recent messages.
    Controlled via settings:
    - trim_messages (bool): enable/disable
    - trim_messages_keep_first (int)
    - trim_messages_keep_last (int)
    """
    merged = add_messages(existing, new)
    merged = maybe_strip_tool_messages(merged)
    if not settings.trim_messages and not settings.summary_messages:
        return merged

    keep_first = max(int(getattr(settings, "trim_messages_keep_first", 1)), 0)
    keep_last = max(int(getattr(settings, "trim_messages_keep_last", 8)), 0)

    # Optional summarization of middle history
    if settings.summary_messages and len(merged) > settings.summary_messages_trigger:
        summary_keep_last = max(
            int(getattr(settings, "summary_messages_keep_last", keep_last)),
            0,
        )
        if keep_first + summary_keep_last >= len(merged):
            return merged

        head = merged[:keep_first] if keep_first else []
        tail = merged[-summary_keep_last:] if summary_keep_last else []
        middle_end = len(merged) - summary_keep_last if summary_keep_last else len(merged)
        middle = merged[keep_first:middle_end]
        if not middle:
            return [*head, *tail]
        summary_msg = summarize_messages(middle)
        return [*head, summary_msg, *tail]

    if not settings.trim_messages:
        return merged

    if keep_first + keep_last == 0 or len(merged) <= keep_first + keep_last:
        return merged

    head = merged[:keep_first] if keep_first else []
    tail = merged[-keep_last:] if keep_last else []
    trimmed = head + tail

    return trimmed


def prepare_seed_messages(messages: list[BaseMessage] | None) -> list[BaseMessage]:
    """
    Apply the same short-term memory policy to seeded history before first node execution.
    """
    return capped_add_messages([], messages or [])


# Execution status type
ExecutionStatus = Literal["pending", "running", "paused", "completed", "failed", "cancelled"]

__all__ = [
    "AgentState",
    "ConversationState",
    "DeepRuntimeSnapshot",
    "ExecutionState",
    "ExecutionStatus",
    "ResearchState",
    "RuntimeSnapshot",
    "build_deep_runtime_snapshot",
    "capped_add_messages",
    "prepare_seed_messages",
    "project_state_updates",
]

class AgentState(TypedDict):
    """
    The state schema for the research agent.
    This represents the agent's "short-term memory" during a research session.

    Enhanced with fields from Manus for better tracking and control.
    """

    # ============ Input/Output ============
    # User's original input/query
    input: str
    # Optional base64-encoded images from the user
    images: list[dict[str, Any]]
    # Final report/answer
    final_report: str
    # Draft report for evaluator/optimizer loop
    draft_report: str
    # Chat-first assistant draft before finalize/human review
    assistant_draft: str

    # ============ User Context ============
    # User identifier for memory/namespace
    user_id: str
    # Thread/conversation identifier
    thread_id: str
    # Agent profile ID (for GPTs-like behavior)
    agent_id: str

    # ============ Execution Control ============
    # Message history for LLM context (auto-trimmed via capped_add_messages)
    messages: Annotated[list[BaseMessage], capped_add_messages]
    # Execution status
    status: ExecutionStatus
    # Completion flag
    is_complete: bool

    # ============ Routing ============
    # Routing decision: agent or deep
    route: str
    # Whether this turn must escalate into the tool agent path
    needs_tools: bool

    # ============ Research Data ============
    # All scraped content from searches
    scraped_content: Annotated[list[dict[str, Any]], operator.add]
    # Summary notes from deep search
    summary_notes: list[str]
    # Sources collected
    sources: list[dict[str, str]]
    # Structured memory snippets used to build runtime prompt context
    memory_context: dict[str, list[str]]
    # Structured short-term session context derived from transcript snapshots
    short_term_context: dict[str, Any]

    # ============ Tool Control ============
    # Resolved execution roles for the current session/profile
    roles: list[str]
    # Granted capability domains for this session/profile
    available_capabilities: list[str]
    # Capability domains explicitly blocked for this session/profile
    blocked_capabilities: list[str]
    # Concrete tools allowed for this session
    available_tools: list[str]
    # Concrete tools explicitly blocked for this session
    blocked_tools: list[str]
    # Concrete tools selected for the current turn
    selected_tools: list[str]

    # ============ Cancellation & Error ============
    # Cancellation support
    cancel_token_id: str | None  # 取消令牌 ID
    is_cancelled: bool  # 是否已取消
    # Error tracking
    errors: Annotated[list[str], operator.add]

    # ============ Research Topology ============
    # Deep Research topology snapshot (serialized dict)
    research_topology: dict[str, Any]

    # ============ Domain Routing ============
    # Detected research domain (scientific, legal, financial, etc.)
    domain: str
    # Domain-specific configuration (search hints, sources, etc.)
    domain_config: dict[str, Any]

    # ============ Sub-Agent Context Isolation ============
    # Tracking of sub-agent contexts for parallel branches
    sub_agent_contexts: dict[str, dict[str, Any]]

    # ============ Deep Research Runtime ============
    # Nested runtime snapshot (preferred public shape)
    deep_runtime: DeepRuntimeSnapshot

def build_deep_runtime_snapshot(
    *,
    engine: str,
    task_queue: dict[str, Any] | None = None,
    artifact_store: dict[str, Any] | None = None,
    runtime_state: dict[str, Any] | None = None,
    agent_runs: list[dict[str, Any]] | None = None,
) -> DeepRuntimeSnapshot:
    """Build the preferred nested runtime snapshot while keeping old fields usable."""

    return _build_deep_runtime_snapshot(
        engine=engine,
        task_queue=task_queue,
        artifact_store=artifact_store,
        runtime_state=runtime_state,
        agent_runs=agent_runs,
    )


def project_state_updates(
    state: dict[str, Any] | None,
    updates: dict[str, Any] | None,
) -> dict[str, Any]:
    return _project_state_updates(state, updates)
