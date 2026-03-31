"""
Compatibility wrapper for the LangGraph-backed multi-agent deep runtime.
"""

from __future__ import annotations

from agent.runtime.deep.multi_agent.graph import (
    GapAnalysisResult,
    MultiAgentDeepSearchRuntime,
    create_multi_agent_deepsearch_graph,
    run_multi_agent_deepsearch,
)

__all__ = [
    "GapAnalysisResult",
    "MultiAgentDeepSearchRuntime",
    "create_multi_agent_deepsearch_graph",
    "run_multi_agent_deepsearch",
]
