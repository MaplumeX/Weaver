"""
Lightweight facade for the agent package.

Only the stable, public-facing symbols are exported here. For anything else,
import from the relevant submodule (agent.core.*, agent.workflows.*, etc.).
"""

from __future__ import annotations

from typing import Any

_PUBLIC_SYMBOLS = {
    # Core graph/state
    "create_research_graph",
    "create_checkpointer",
    "AgentState",
    "ContextWindowManager",
    "QueryState",
    "QueryDeduplicator",
    "ResearchPlan",
    "smart_route",
    # Events / streaming
    "event_stream_generator",
    "get_emitter",
    "get_emitter_sync",
    "remove_emitter",
    "ToolEvent",
    "ToolEventType",
    # Prompts
    "get_default_agent_prompt",
    "get_agent_prompt",
    "get_writer_prompt",
    "get_deep_research_prompt",
    "PromptManager",
    "get_prompt_manager",
    "set_prompt_manager",
    # Workflows & tools
    "get_deep_agent_prompt",
    "run_deepsearch",
    "run_deepsearch_auto",
    "run_deepsearch_runtime",
    "build_writer_agent",
    "build_tool_agent",
    "build_agent_tools",
    "initialize_enhanced_tools",
    "summarize_messages",
    "get_search_cache",
    "clear_search_cache",
    "extract_message_sources",
    "ClaimStatus",
    "ClaimVerifier",
    "ResultAggregator",
}

__all__ = [
    # Keep the stable surface small and explicit.
    "create_research_graph",
    "create_checkpointer",
    "AgentState",
    "ContextWindowManager",
    "QueryState",
    "QueryDeduplicator",
    "ResearchPlan",
    "smart_route",
    "event_stream_generator",
    "get_emitter",
    "get_emitter_sync",
    "remove_emitter",
    "ToolEvent",
    "ToolEventType",
    "get_default_agent_prompt",
    "get_agent_prompt",
    "get_writer_prompt",
    "get_deep_research_prompt",
    "PromptManager",
    "get_prompt_manager",
    "set_prompt_manager",
    "get_deep_agent_prompt",
    "run_deepsearch",
    "run_deepsearch_auto",
    "run_deepsearch_runtime",
    "build_writer_agent",
    "build_tool_agent",
    "build_agent_tools",
    "initialize_enhanced_tools",
    "summarize_messages",
    "get_search_cache",
    "clear_search_cache",
    "extract_message_sources",
    "ClaimStatus",
    "ClaimVerifier",
    "ResultAggregator",
]


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name in _PUBLIC_SYMBOLS:
        from agent import api as _api

        return getattr(_api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_PUBLIC_SYMBOLS)))
