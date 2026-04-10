"""
Public API surface for `agent.foundation`.

Importing submodules like `agent.foundation.search_cache` should not pull in
execution orchestration unless explicitly requested.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "AgentState",
    "ConversationState",
    "DeepRuntimeSnapshot",
    "Event",
    "EventEmitter",
    "ExecutionState",
    "QueryDeduplicator",
    "ResearchState",
    "RuntimeSnapshot",
    "SearchCache",
    "ToolEvent",
    "ToolEventType",
    "build_deep_runtime_snapshot",
    "event_stream_generator",
    "get_emitter",
    "get_emitter_sync",
    "maybe_strip_tool_messages",
    "project_state_updates",
    "remove_emitter",
    "smart_route",
]

_SYMBOL_TO_MODULE: dict[str, str] = {
    "AgentState": "agent.foundation.state",
    "ConversationState": "agent.foundation.state",
    "DeepRuntimeSnapshot": "agent.foundation.state",
    "ExecutionState": "agent.foundation.state",
    "ResearchState": "agent.foundation.state",
    "RuntimeSnapshot": "agent.foundation.state",
    "build_deep_runtime_snapshot": "agent.foundation.state",
    "project_state_updates": "agent.foundation.state",
    "Event": "agent.foundation.events",
    "EventEmitter": "agent.foundation.events",
    "ToolEvent": "agent.foundation.events",
    "ToolEventType": "agent.foundation.events",
    "event_stream_generator": "agent.foundation.events",
    "get_emitter": "agent.foundation.events",
    "get_emitter_sync": "agent.foundation.events",
    "remove_emitter": "agent.foundation.events",
    "smart_route": "agent.foundation.smart_router",
    "maybe_strip_tool_messages": "agent.foundation.middleware",
    "SearchCache": "agent.foundation.search_cache",
    "QueryDeduplicator": "agent.foundation.search_cache",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
