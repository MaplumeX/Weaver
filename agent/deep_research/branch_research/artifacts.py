"""Artifact builders for branch research outcomes."""

from __future__ import annotations

from typing import Any

from agent.deep_research.branch_research.contracts import (
    BranchContradictionSummary,
    BranchCoverageSummary,
    BranchGroundingSummary,
    BranchQualitySummary,
)
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import (
    BranchContradictionArtifact,
    BranchCoverageArtifact,
    BranchGroundingArtifact,
    BranchQualityArtifact,
    ResearchTask,
)


def build_branch_artifacts(
    task: ResearchTask,
    *,
    coverage: BranchCoverageSummary,
    quality: BranchQualitySummary,
    contradiction: BranchContradictionSummary,
    grounding: BranchGroundingSummary,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    coverage_artifact = BranchCoverageArtifact(
        id=_new_id("branch_coverage"),
        task_id=task.id,
        section_id=task.section_id,
        branch_id=task.branch_id,
        criteria=list(coverage.criteria),
        covered_count=coverage.covered_count,
        partial_count=coverage.partial_count,
        missing_count=coverage.missing_count,
        missing_topics=list(coverage.missing_topics),
        coverage_ready=coverage.coverage_ready,
    ).to_dict()
    quality_artifact = BranchQualityArtifact(
        id=_new_id("branch_quality"),
        task_id=task.id,
        section_id=task.section_id,
        branch_id=task.branch_id,
        authority_score=quality.authority_score,
        freshness_score=quality.freshness_score,
        source_diversity_score=quality.source_diversity_score,
        evidence_density_score=quality.evidence_density_score,
        objective_alignment_score=quality.objective_alignment_score,
        quality_ready=quality.quality_ready,
        notes=quality.notes,
    ).to_dict()
    contradiction_artifact = BranchContradictionArtifact(
        id=_new_id("branch_contradiction"),
        task_id=task.id,
        section_id=task.section_id,
        branch_id=task.branch_id,
        has_material_conflict=contradiction.has_material_conflict,
        conflict_count=contradiction.conflict_count,
        conflict_source_urls=list(contradiction.conflict_source_urls),
        conflict_notes=list(contradiction.conflict_notes),
        needs_counterevidence_query=contradiction.needs_counterevidence_query,
    ).to_dict()
    grounding_artifact = BranchGroundingArtifact(
        id=_new_id("branch_grounding"),
        task_id=task.id,
        section_id=task.section_id,
        branch_id=task.branch_id,
        claims=list(grounding.claims),
        total_claim_count=grounding.total_claim_count,
        grounded_claim_count=grounding.grounded_claim_count,
        primary_grounding_ratio=grounding.primary_grounding_ratio,
        secondary_grounding_ratio=grounding.secondary_grounding_ratio,
        grounding_ready=grounding.grounding_ready,
    ).to_dict()
    return {
        "coverage": coverage_artifact,
        "quality": quality_artifact,
        "contradiction": contradiction_artifact,
        "grounding": grounding_artifact,
        "decisions": decisions,
    }
