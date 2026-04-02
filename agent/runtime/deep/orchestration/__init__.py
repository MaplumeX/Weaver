"""Deep runtime orchestration entrypoints and loop-owned helpers."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "GapAnalysisResult",
    "MultiAgentDeepResearchRuntime",
    "create_deep_research_runtime_graph",
    "create_multi_agent_deep_research_graph",
    "run_deep_research_runtime",
    "run_multi_agent_deep_research",
]

_SYMBOL_TO_MODULE = {
    "GapAnalysisResult": "agent.runtime.deep.orchestration.runtime",
    "MultiAgentDeepResearchRuntime": "agent.runtime.deep.orchestration.runtime",
    "create_deep_research_runtime_graph": "agent.runtime.deep.orchestration.runtime",
    "create_multi_agent_deep_research_graph": "agent.runtime.deep.orchestration.runtime",
    "run_deep_research_runtime": "agent.runtime.deep.orchestration.runtime",
    "run_multi_agent_deep_research": "agent.runtime.deep.orchestration.runtime",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
