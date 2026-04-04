"""Runtime-owned Deep Research services."""

from agent.runtime.deep.services.knowledge_gap import (
    GapAnalysisResult,
    KnowledgeGap,
    KnowledgeGapAnalyzer,
    integrate_gap_analysis,
)

__all__ = [
    "GapAnalysisResult",
    "KnowledgeGap",
    "KnowledgeGapAnalyzer",
    "integrate_gap_analysis",
]
