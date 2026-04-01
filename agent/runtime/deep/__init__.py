"""
Deep-research runtime entrypoints.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

__all__ = [
    "run_deepsearch_auto",
    "run_deepsearch_runtime",
    "run_multi_agent_deepsearch",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    "run_deepsearch_auto": "agent.runtime.deep.entrypoints",
    "run_deepsearch_runtime": "agent.runtime.deep.multi_agent",
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
