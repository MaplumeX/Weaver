"""Deep runtime supporting helpers separated from the orchestration loop."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "DeepResearchToolAgentSession",
    "MultiAgentGraphState",
    "format_scope_draft_markdown",
    "restore_agent_runs",
    "restore_worker_result",
    "run_bounded_tool_agent",
]

_SYMBOL_TO_MODULE = {
    "DeepResearchToolAgentSession": "agent.runtime.deep.support.tool_agents",
    "MultiAgentGraphState": "agent.runtime.deep.support.graph_helpers",
    "format_scope_draft_markdown": "agent.runtime.deep.support.graph_helpers",
    "restore_agent_runs": "agent.runtime.deep.support.graph_helpers",
    "restore_worker_result": "agent.runtime.deep.support.graph_helpers",
    "run_bounded_tool_agent": "agent.runtime.deep.support.tool_agents",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
