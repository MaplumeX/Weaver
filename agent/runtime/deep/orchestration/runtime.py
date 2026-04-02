"""
Public entrypoints for the LangGraph-backed multi-agent Deep Research runtime.
"""

from __future__ import annotations

from agent.runtime.deep.orchestration.graph import (
    GapAnalysisResult,
    MultiAgentDeepResearchRuntime,
    create_multi_agent_deep_research_graph,
    run_multi_agent_deep_research,
)

run_deep_research_runtime = run_multi_agent_deep_research
create_deep_research_runtime_graph = create_multi_agent_deep_research_graph

__all__ = [
    "GapAnalysisResult",
    "MultiAgentDeepResearchRuntime",
    "create_deep_research_runtime_graph",
    "create_multi_agent_deep_research_graph",
    "run_deep_research_runtime",
    "run_multi_agent_deep_research",
]
