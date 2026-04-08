"""
Deterministic assessment helpers for branch-scoped researcher loops.
"""

from __future__ import annotations

from typing import Any

from agent.runtime.deep.researcher_runtime.contracts import (
    BranchContradictionSummary,
    BranchCoverageSummary,
    BranchDecision,
    BranchGroundingSummary,
    BranchQualitySummary,
)
from agent.runtime.deep.researcher_runtime.shared import dedupe_strings, source_domain, tokenize
from agent.runtime.deep.schema import ResearchTask


def evaluate_coverage(
    task: ResearchTask,
    passages: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> BranchCoverageSummary:
    criteria = task.acceptance_criteria or task.coverage_targets or [task.objective or task.goal or task.query]
    evaluated: list[dict[str, Any]] = []
    missing_topics: list[str] = []
    covered = 0
    partial = 0

    for criterion in criteria:
        criterion_text = str(criterion or "").strip()
        if not criterion_text:
            continue
        criterion_tokens = tokenize(criterion_text)
        best_passage_overlap = 0
        best_passage_ids: list[str] = []
        for passage in passages or []:
            text = str(passage.get("text") or passage.get("quote") or "").strip()
            overlap = len(criterion_tokens & tokenize(text))
            if overlap > best_passage_overlap:
                best_passage_overlap = overlap
                best_passage_ids = [str(passage.get("id") or "").strip()] if str(passage.get("id") or "").strip() else []

        best_document_overlap = 0
        for document in documents or []:
            text = str(document.get("content") or document.get("excerpt") or "").strip()
            best_document_overlap = max(best_document_overlap, len(criterion_tokens & tokenize(text)))

        if best_passage_overlap > 0:
            status = "covered"
            covered += 1
            notes = "found supporting passage"
        elif best_document_overlap > 0:
            status = "partial"
            partial += 1
            notes = "found weak document-only support"
            missing_topics.append(criterion_text)
        else:
            status = "missing"
            notes = "no matching evidence found"
            missing_topics.append(criterion_text)
            best_passage_ids = []
        evaluated.append(
            {
                "criterion": criterion_text,
                "status": status,
                "evidence_passage_ids": best_passage_ids,
                "notes": notes,
            }
        )

    missing = max(0, len(evaluated) - covered - partial)
    coverage_ready = bool(evaluated) and missing == 0 and covered >= max(1, len(evaluated) - partial)
    return BranchCoverageSummary(
        criteria=evaluated,
        covered_count=covered,
        partial_count=partial,
        missing_count=missing,
        missing_topics=dedupe_strings(missing_topics, limit=4),
        coverage_ready=coverage_ready,
        notes="all acceptance criteria covered" if coverage_ready else "additional coverage needed",
    )


def evaluate_quality(
    task: ResearchTask,
    sources: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    coverage_summary: BranchCoverageSummary,
) -> BranchQualitySummary:
    source_count = len(sources or [])
    authoritative_count = sum(1 for item in sources or [] if bool(item.get("authoritative", False)))
    authority_score = round(authoritative_count / max(1, source_count), 3) if source_count else 0.0

    published_count = sum(1 for item in sources or [] if str(item.get("published_date") or "").strip())
    freshness_score = round(published_count / max(1, source_count), 3) if source_count else 0.0

    unique_domains = {source_domain(str(item.get("url") or "").strip()) for item in sources or [] if str(item.get("url") or "").strip()}
    unique_domains.discard("")
    source_diversity_score = round(min(1.0, len(unique_domains) / max(1, source_count)), 3) if source_count else 0.0

    evidence_density_score = round(min(1.0, len(passages or []) / max(1, len(task.acceptance_criteria or [task.objective]))), 3)
    objective_alignment_score = round(
        (coverage_summary.covered_count + (coverage_summary.partial_count * 0.5)) / max(1, len(coverage_summary.criteria)),
        3,
    )

    gaps: list[str] = []
    if authority_score < 0.5:
        gaps.append("authority")
    if freshness_score < 0.5 and str(task.freshness_policy or "").strip():
        gaps.append("freshness")
    if source_diversity_score < 0.34:
        gaps.append("diversity")
    if evidence_density_score < 0.5:
        gaps.append("evidence_density")
    if objective_alignment_score < 0.75:
        gaps.append("objective_alignment")

    quality_ready = authority_score >= 0.5 and objective_alignment_score >= 0.75 and evidence_density_score >= 0.5
    notes = "quality thresholds met" if quality_ready else f"quality gaps: {', '.join(gaps) or 'unknown'}"
    return BranchQualitySummary(
        authority_score=authority_score,
        freshness_score=freshness_score,
        source_diversity_score=source_diversity_score,
        evidence_density_score=evidence_density_score,
        objective_alignment_score=objective_alignment_score,
        quality_ready=quality_ready,
        gaps=gaps,
        notes=notes,
    )


def evaluate_contradictions(
    sources: list[dict[str, Any]],
    quality_summary: BranchQualitySummary,
) -> BranchContradictionSummary:
    domains = [source_domain(str(item.get("url") or "").strip()) for item in sources or [] if str(item.get("url") or "").strip()]
    unique_domains = dedupe_strings(domains)
    needs_counterevidence_query = bool(sources) and len(unique_domains) <= 1 and quality_summary.source_diversity_score < 0.34
    conflict_notes: list[str] = []
    if needs_counterevidence_query:
        conflict_notes.append("current evidence is dominated by a single source domain")
    return BranchContradictionSummary(
        has_material_conflict=False,
        conflict_count=0,
        conflict_source_urls=[],
        conflict_notes=conflict_notes,
        needs_counterevidence_query=needs_counterevidence_query,
    )


def evaluate_grounding(claim_units: list[dict[str, Any]]) -> BranchGroundingSummary:
    total_claim_count = len(claim_units or [])
    grounded_claim_count = sum(1 for item in claim_units or [] if bool(item.get("grounded")))
    primary_claims = [
        item for item in claim_units or []
        if str(item.get("importance") or "").strip().lower() == "primary"
    ]
    secondary_claims = [
        item for item in claim_units or []
        if str(item.get("importance") or "").strip().lower() != "primary"
    ]
    primary_grounding_ratio = round(
        sum(1 for item in primary_claims if bool(item.get("grounded"))) / max(1, len(primary_claims)),
        3,
    )
    secondary_grounding_ratio = round(
        sum(1 for item in secondary_claims if bool(item.get("grounded"))) / max(1, len(secondary_claims)),
        3,
    )
    return BranchGroundingSummary(
        claims=list(claim_units or []),
        total_claim_count=total_claim_count,
        grounded_claim_count=grounded_claim_count,
        primary_grounding_ratio=primary_grounding_ratio,
        secondary_grounding_ratio=secondary_grounding_ratio,
        grounding_ready=(primary_grounding_ratio >= 0.8 if primary_claims else grounded_claim_count > 0),
    )


def decide_next_action(
    *,
    coverage_summary: BranchCoverageSummary,
    quality_summary: BranchQualitySummary,
    contradiction_summary: BranchContradictionSummary,
    grounding_summary: BranchGroundingSummary | None,
    round_index: int,
    max_rounds: int,
    new_source_count: int,
    follow_up_queries: list[str],
) -> BranchDecision:
    if coverage_summary.coverage_ready and quality_summary.quality_ready and (
        grounding_summary is None or grounding_summary.grounding_ready
    ):
        return BranchDecision(action="synthesize", reason="coverage and quality thresholds satisfied")
    if round_index >= max_rounds:
        return BranchDecision(
            action="bounded_stop",
            reason="branch round budget exhausted",
            stop_reason="max_rounds_exhausted",
        )
    if new_source_count <= 0 and not follow_up_queries:
        return BranchDecision(
            action="bounded_stop",
            reason="no new high-value evidence or queries available",
            stop_reason="evidence_stagnated",
        )
    if contradiction_summary.needs_counterevidence_query:
        return BranchDecision(
            action="compare_evidence",
            reason="source diversity is too low; counterevidence query needed",
            follow_up_queries=follow_up_queries,
        )
    if follow_up_queries:
        return BranchDecision(
            action="refine_queries",
            reason="coverage or quality gaps remain",
            follow_up_queries=follow_up_queries,
        )
    return BranchDecision(
        action="bounded_stop",
        reason="no safe next step available",
        stop_reason="no_follow_up_queries",
    )
