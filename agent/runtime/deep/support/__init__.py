"""Deep runtime supporting helpers separated from the orchestration loop."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "MultiAgentGraphState",
    "format_scope_draft_markdown",
]

_SYMBOL_TO_MODULE = {
    "MultiAgentGraphState": "agent.runtime.deep.support.graph_helpers",
    "format_scope_draft_markdown": "agent.runtime.deep.support.graph_helpers",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
