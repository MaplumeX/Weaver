"""
Supported Deep Research runtime entrypoints.
"""

from __future__ import annotations

from typing import Any

from langgraph.errors import GraphBubbleUp

from agent.runtime.deep.config import ensure_supported_runtime_inputs
from agent.runtime.deep.orchestration.runtime import (
    run_deepsearch_runtime as _run_deepsearch_runtime,
)


def run_deepsearch_auto(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    ensure_supported_runtime_inputs(config)
    try:
        result = _run_deepsearch_runtime(state, config)
    except GraphBubbleUp:
        raise
    if isinstance(result, dict) and not bool(result.get("is_cancelled")):
        result.setdefault("_deepsearch_events_emitted", True)
    return result


def run_multi_agent_deepsearch(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return run_deepsearch_auto(state, config)


__all__ = ["run_deepsearch_auto", "run_multi_agent_deepsearch"]
