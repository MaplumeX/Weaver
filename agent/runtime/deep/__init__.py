"""
Deep-research runtime entrypoints.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

__all__ = [
    "run_deepsearch_auto",
    "run_deepsearch_optimized",
    "run_deepsearch_tree",
    "run_multi_agent_deepsearch",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    "run_deepsearch_auto": "agent.runtime.deep.selector",
    "run_deepsearch_optimized": "agent.runtime.deep.legacy",
    "run_deepsearch_tree": "agent.runtime.deep.legacy",
    "run_multi_agent_deepsearch": "agent.runtime.deep.multi_agent",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
