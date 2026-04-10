"""Deep runtime orchestration entrypoints and loop-owned helpers."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "MultiAgentDeepResearchRuntime",
    "run_multi_agent_deep_research",
]

_SYMBOL_TO_MODULE = {
    "MultiAgentDeepResearchRuntime": "agent.deep_research.engine.graph",
    "run_multi_agent_deep_research": "agent.deep_research.engine.graph",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
