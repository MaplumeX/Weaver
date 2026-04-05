"""
Lightweight facade for the agent package.

Only the stable, public-facing symbols are exported here. For anything else,
import from the relevant submodule (agent.runtime.*, agent.contracts.*,
agent.prompts.*, etc.).
"""

from __future__ import annotations

from typing import Any

_PUBLIC_SYMBOLS = {
    # Core graph/state
    "create_research_graph",
    "create_checkpointer",
    "AgentState",
    "build_execution_request",
    "build_initial_agent_state",
    # Events / streaming
    "event_stream_generator",
    "get_emitter",
    "remove_emitter",
    "ToolEvent",
    # Prompts
    "get_default_agent_prompt",
    "initialize_enhanced_tools",
}

__all__ = sorted(
    [
        "AgentState",
        "ToolEvent",
        "build_execution_request",
        "build_initial_agent_state",
        "create_checkpointer",
        "create_research_graph",
        "event_stream_generator",
        "get_default_agent_prompt",
        "get_emitter",
        "initialize_enhanced_tools",
        "remove_emitter",
    ]
)


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name in _PUBLIC_SYMBOLS:
        from agent import api as _api

        return getattr(_api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_PUBLIC_SYMBOLS)))
