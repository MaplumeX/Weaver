"""
Structured runtime entrypoints for agent execution internals.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

__all__ = [
    "chat_respond_node",
    "check_cancellation",
    "create_research_graph",
    "deep_research_node",
    "finalize_answer_node",
    "handle_cancellation",
    "human_review_node",
    "route_node",
    "run_deep_research",
    "tool_agent_node",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    "chat_respond_node": "agent.runtime.nodes",
    "check_cancellation": "agent.runtime.nodes",
    "create_research_graph": "agent.runtime.graph",
    "deep_research_node": "agent.runtime.nodes",
    "finalize_answer_node": "agent.runtime.nodes",
    "handle_cancellation": "agent.runtime.nodes",
    "human_review_node": "agent.runtime.nodes",
    "route_node": "agent.runtime.nodes",
    "run_deep_research": "agent.runtime.deep",
    "tool_agent_node": "agent.runtime.nodes",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
