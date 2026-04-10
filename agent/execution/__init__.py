"""
Execution entrypoints and request-state assembly.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "AgentProfileConfig",
    "ExecutionMode",
    "ExecutionRequest",
    "ExecutionResult",
    "ReviewDecision",
    "build_execution_request",
    "build_initial_agent_state",
    "create_checkpointer",
    "create_research_graph",
    "execution_mode_from_public_mode",
    "route_name_for_mode",
]

_SYMBOL_TO_MODULE: dict[str, str] = {
    "AgentProfileConfig": "agent.execution.models",
    "ExecutionMode": "agent.execution.models",
    "ExecutionRequest": "agent.execution.models",
    "ExecutionResult": "agent.execution.models",
    "ReviewDecision": "agent.execution.models",
    "execution_mode_from_public_mode": "agent.execution.models",
    "route_name_for_mode": "agent.execution.models",
    "build_execution_request": "agent.execution.state",
    "build_initial_agent_state": "agent.execution.state",
    "create_checkpointer": "agent.execution.graph",
    "create_research_graph": "agent.execution.graph",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
