"""
Supported Deep Research runtime entrypoints.
"""

from __future__ import annotations

from typing import Any

from langgraph.errors import GraphBubbleUp

from agent.deep_research.config import ensure_supported_runtime_inputs
from agent.deep_research.engine.graph import (
    run_multi_agent_deep_research as _run_multi_agent_deep_research,
)


def run_deep_research(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    ensure_supported_runtime_inputs(config)
    try:
        result = _run_multi_agent_deep_research(state, config)
    except GraphBubbleUp:
        raise
    if isinstance(result, dict) and not bool(result.get("is_cancelled")):
        result.setdefault("_deep_research_events_emitted", True)
    return result


__all__ = ["run_deep_research"]
