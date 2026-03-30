"""
Public API surface for `agent.core`.

This module is intentionally **lazy** to avoid circular import chains. Importing
submodules like `agent.core.search_cache` should not pull in the whole graph /
workflow stack.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

__all__ = [
    "create_research_graph",
    "create_checkpointer",
    "AgentState",
    "QueryState",
    "ResearchPlan",
    "Event",
    "EventEmitter",
    "ToolEvent",
    "ToolEventType",
    "event_stream_generator",
    "get_emitter",
    "get_emitter_sync",
    "remove_emitter",
    "ContextManager",
    "ContextWindowManager",
    "get_context_manager",
    "get_context_window_manager",
    "smart_route",
    "enforce_tool_call_limit",
    "retry_call",
    "maybe_strip_tool_messages",
    "AgentProcessorConfig",
    "SearchCache",
    "QueryDeduplicator",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    # Graph/state
    "create_research_graph": "agent.core.graph",
    "create_checkpointer": "agent.core.graph",
    "AgentState": "agent.core.state",
    "QueryState": "agent.core.state",
    "ResearchPlan": "agent.core.state",
    # Events / streaming
    "Event": "agent.core.events",
    "EventEmitter": "agent.core.events",
    "ToolEvent": "agent.core.events",
    "ToolEventType": "agent.core.events",
    "event_stream_generator": "agent.core.events",
    "get_emitter": "agent.core.events",
    "get_emitter_sync": "agent.core.events",
    "remove_emitter": "agent.core.events",
    # Context
    "ContextManager": "agent.core.context_manager",
    "ContextWindowManager": "agent.core.context_manager",
    "get_context_manager": "agent.core.context_manager",
    "get_context_window_manager": "agent.core.context_manager",
    # Routing
    "smart_route": "agent.core.smart_router",
    # Middleware
    "enforce_tool_call_limit": "agent.core.middleware",
    "retry_call": "agent.core.middleware",
    "maybe_strip_tool_messages": "agent.core.middleware",
    # Config
    "AgentProcessorConfig": "agent.core.processor_config",
    # Cache
    "SearchCache": "agent.core.search_cache",
    "QueryDeduplicator": "agent.core.search_cache",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
