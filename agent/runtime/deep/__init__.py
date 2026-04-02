"""
Deep-research runtime entrypoints.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

__all__ = [
    "run_deep_research",
    "run_deep_research_runtime",
    "run_multi_agent_deep_research",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    "run_deep_research": "agent.runtime.deep.entrypoints",
    "run_deep_research_runtime": "agent.runtime.deep.orchestration",
    "run_multi_agent_deep_research": "agent.runtime.deep.orchestration",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
