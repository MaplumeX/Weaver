"""
Public entrypoints for the LangGraph-backed multi-agent Deep Research runtime.
"""

from __future__ import annotations

from agent.runtime.deep.multi_agent.graph import (
    GapAnalysisResult,
    MultiAgentDeepSearchRuntime,
    create_multi_agent_deepsearch_graph,
    run_multi_agent_deepsearch,
)

run_deepsearch_runtime = run_multi_agent_deepsearch
create_deepsearch_runtime_graph = create_multi_agent_deepsearch_graph

__all__ = [
    "GapAnalysisResult",
    "MultiAgentDeepSearchRuntime",
    "create_deepsearch_runtime_graph",
    "create_multi_agent_deepsearch_graph",
    "run_deepsearch_runtime",
    "run_multi_agent_deepsearch",
]
