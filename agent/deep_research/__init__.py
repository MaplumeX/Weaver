"""
Deep Research capability entrypoints.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "deep_research_node",
    "run_deep_research",
]

_SYMBOL_TO_MODULE: dict[str, str] = {
    "deep_research_node": "agent.deep_research.node",
    "run_deep_research": "agent.deep_research.entrypoints",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
