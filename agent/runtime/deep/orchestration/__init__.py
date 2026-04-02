"""Deep runtime orchestration entrypoints and loop-owned helpers."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "GapAnalysisResult",
    "MultiAgentDeepSearchRuntime",
    "create_deepsearch_runtime_graph",
    "create_multi_agent_deepsearch_graph",
    "run_deepsearch_runtime",
    "run_multi_agent_deepsearch",
]

_SYMBOL_TO_MODULE = {
    "GapAnalysisResult": "agent.runtime.deep.orchestration.runtime",
    "MultiAgentDeepSearchRuntime": "agent.runtime.deep.orchestration.runtime",
    "create_deepsearch_runtime_graph": "agent.runtime.deep.orchestration.runtime",
    "create_multi_agent_deepsearch_graph": "agent.runtime.deep.orchestration.runtime",
    "run_deepsearch_runtime": "agent.runtime.deep.orchestration.runtime",
    "run_multi_agent_deepsearch": "agent.runtime.deep.orchestration.runtime",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
