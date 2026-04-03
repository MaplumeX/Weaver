"""Runtime-owned Deep Research services."""

from agent.runtime.deep.services.knowledge_gap import (
    GapAnalysisResult,
    KnowledgeGap,
    KnowledgeGapAnalyzer,
    integrate_gap_analysis,
)
from agent.runtime.deep.services.verification import (
    aggregate_revision_issues,
    build_gap_result,
    derive_claim_units,
    derive_coverage_obligations,
    evaluate_consistency,
    evaluate_obligations,
    ground_claim_units,
    latest_branch_syntheses,
    summarize_issue_statuses,
    summarize_revision_lineage,
)

__all__ = [
    "GapAnalysisResult",
    "KnowledgeGap",
    "KnowledgeGapAnalyzer",
    "aggregate_revision_issues",
    "build_gap_result",
    "derive_claim_units",
    "derive_coverage_obligations",
    "evaluate_consistency",
    "evaluate_obligations",
    "ground_claim_units",
    "integrate_gap_analysis",
    "latest_branch_syntheses",
    "summarize_issue_statuses",
    "summarize_revision_lineage",
]
