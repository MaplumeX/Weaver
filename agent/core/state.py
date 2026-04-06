import operator
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph.message import add_messages

from agent.domain.state import (
    ConversationState,
    DeepRuntimeSnapshot,
    ExecutionState,
    ResearchState,
    RuntimeSnapshot,
    build_deep_runtime_snapshot as _build_deep_runtime_snapshot,
    build_state_slices as _build_state_slices,
    project_state_updates as _project_state_updates,
)
from agent.core.message_utils import summarize_messages
from common.config import settings

from .middleware import maybe_strip_tool_messages


def capped_add_messages(
    existing: List[BaseMessage] | None, new: List[BaseMessage] | None
) -> List[BaseMessage]:
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
    if not settings.trim_messages:
        return merged

    keep_first = max(int(getattr(settings, "trim_messages_keep_first", 1)), 0)
    keep_last = max(int(getattr(settings, "trim_messages_keep_last", 8)), 0)
    if keep_first + keep_last == 0 or len(merged) <= keep_first + keep_last:
        return merged

    head = merged[:keep_first] if keep_first else []
    tail = merged[-keep_last:] if keep_last else []
    trimmed = head + tail

    # Optional summarization of middle history
    if settings.summary_messages and len(merged) > settings.summary_messages_trigger:
        middle = merged[keep_first : len(merged) - keep_last]
        summary_msg = summarize_messages(middle)
        trimmed = head + [summary_msg] + tail

    return trimmed


# Execution status type
ExecutionStatus = Literal["pending", "running", "paused", "completed", "failed", "cancelled"]


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
    images: List[Dict[str, Any]]
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
    messages: Annotated[List[BaseMessage], capped_add_messages]
    # Execution status
    status: ExecutionStatus
    # Completion flag
    is_complete: bool
    # Start timestamp (ISO format)
    started_at: str
    # End timestamp (ISO format)
    ended_at: str

    # ============ Routing ============
    # Routing decision: agent or deep
    route: str
    # Routing reasoning (from smart router)
    routing_reasoning: str
    # Routing confidence (0-1)
    routing_confidence: float
    # Whether this turn must escalate into the tool agent path
    needs_tools: bool
    # Human-readable reason for escalation
    tool_reason: str

    # ============ Research Data ============
    # All scraped content from searches
    scraped_content: Annotated[List[Dict[str, Any]], operator.add]
    # Code execution results
    code_results: Annotated[List[Dict[str, Any]], operator.add]
    # Summary notes from deep search
    summary_notes: List[str]
    # Sources collected
    sources: List[Dict[str, str]]
    # Structured memory snippets used to build runtime prompt context
    memory_context: Dict[str, List[str]]
    # Compact summary of tool results for finalize/logging
    tool_observations: Annotated[List[Dict[str, Any]], operator.add]

    # ============ Tool Control ============
    # Tool approval gating
    tool_approved: bool
    # Pending tool calls awaiting approval
    pending_tool_calls: List[Dict[str, Any]]
    # Tool call accounting
    tool_call_count: int
    # Maximum tool calls allowed
    tool_call_limit: int
    # Concrete tools allowed for this session
    available_tools: List[str]
    # Concrete tools explicitly blocked for this session
    blocked_tools: List[str]
    # Concrete tools selected for the current turn
    selected_tools: List[str]

    # ============ Cancellation & Error ============
    # Cancellation support
    cancel_token_id: Optional[str]  # 取消令牌 ID
    is_cancelled: bool  # 是否已取消
    # Error tracking
    errors: Annotated[List[str], operator.add]
    # Last error message
    last_error: str

    # ============ Research Topology ============
    # Deep Research topology snapshot (serialized dict)
    research_topology: Dict[str, Any]
    # Current branch being explored
    current_branch_id: Optional[str]

    # ============ Domain Routing ============
    # Detected research domain (scientific, legal, financial, etc.)
    domain: str
    # Domain-specific configuration (search hints, sources, etc.)
    domain_config: Dict[str, Any]

    # ============ Sub-Agent Context Isolation ============
    # Tracking of sub-agent contexts for parallel branches
    sub_agent_contexts: Dict[str, Dict[str, Any]]

    # ============ Deep Research Runtime ============
    # Nested runtime snapshot (preferred public shape)
    deep_runtime: DeepRuntimeSnapshot

    # ============ Metrics ============
    # Token usage tracking
    total_input_tokens: int
    total_output_tokens: int

    # ============ Structured State Slices ============
    conversation_state: ConversationState
    execution_state: ExecutionState
    research_state: ResearchState
    runtime_snapshot: RuntimeSnapshot

def build_deep_runtime_snapshot(
    *,
    engine: str,
    task_queue: Optional[Dict[str, Any]] = None,
    artifact_store: Optional[Dict[str, Any]] = None,
    runtime_state: Optional[Dict[str, Any]] = None,
    agent_runs: Optional[List[Dict[str, Any]]] = None,
) -> DeepRuntimeSnapshot:
    """Build the preferred nested runtime snapshot while keeping old fields usable."""

    return _build_deep_runtime_snapshot(
        engine=engine,
        task_queue=task_queue,
        artifact_store=artifact_store,
        runtime_state=runtime_state,
        agent_runs=agent_runs,
    )


def build_state_slices(state: Dict[str, Any] | None) -> Dict[str, Any]:
    return _build_state_slices(state)


def project_state_updates(
    state: Dict[str, Any] | None,
    updates: Dict[str, Any] | None,
) -> Dict[str, Any]:
    return _project_state_updates(state, updates)
