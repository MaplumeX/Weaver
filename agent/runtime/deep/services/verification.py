"""
Structured verification helpers for the Deep Research runtime.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

from agent.contracts.claim_verifier import ClaimStatus, ClaimVerifier
from agent.runtime.deep.schema import (
    BranchBrief,
    BranchRevisionBrief,
    BranchSynthesis,
    ClaimGroundingResult,
    ClaimUnit,
    ConsistencyResult,
    CoverageEvaluationResult,
    CoverageObligation,
    ResearchBriefArtifact,
    ResearchTask,
    RevisionIssue,
)
from agent.runtime.deep.services.knowledge_gap import GapAnalysisResult, KnowledgeGap as AnalyzerKnowledgeGap
import agent.runtime.deep.support.runtime_support as support


_COVERAGE_STOPWORDS = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "from",
    "into",
    "were",
    "was",
    "are",
    "for",
    "has",
    "have",
    "had",
    "will",
    "about",
    "of",
    "to",
    "explain",
    "describe",
    "summarize",
    "analyze",
    "review",
    "说明",
    "解释",
    "总结",
    "分析",
    "介绍",
}


def _dedupe_texts(values: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


def _coverage_tokens(text: str) -> list[str]:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return []

    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", normalized):
        if ((len(token) <= 1 and not token.isdigit()) or token in _COVERAGE_STOPWORDS):
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)

    for chunk in re.findall(r"[\u4e00-\u9fff]+", normalized):
        if len(chunk) == 1:
            if chunk not in _COVERAGE_STOPWORDS and chunk not in seen:
                seen.add(chunk)
                tokens.append(chunk)
            continue
        for index in range(len(chunk) - 1):
            token = chunk[index:index + 2]
            if token in _COVERAGE_STOPWORDS or token in seen:
                continue
            seen.add(token)
            tokens.append(token)

    return tokens


def _required_match_count(token_count: int) -> int:
    if token_count <= 2:
        return token_count
    return max(2, (token_count * 3 + 4) // 5)


def _match_text(text: str, target: str) -> bool:
    haystack = str(text or "").strip().lower()
    needle = str(target or "").strip().lower()
    if not haystack or not needle:
        return False
    if needle in haystack:
        return True
    target_tokens = _coverage_tokens(needle)
    if not target_tokens:
        return False
    haystack_tokens = set(_coverage_tokens(haystack))
    matches = sum(1 for token in target_tokens if token in haystack_tokens or token in haystack)
    return matches >= _required_match_count(len(target_tokens))


def latest_branch_syntheses(
    syntheses: list[BranchSynthesis],
    briefs: list[BranchBrief] | None = None,
) -> list[BranchSynthesis]:
    by_branch: dict[str, BranchSynthesis] = {}
    brief_by_branch = {
        brief.id: brief
        for brief in briefs or []
        if isinstance(brief.id, str) and brief.id
    }
    for synthesis in sorted(syntheses, key=lambda item: (item.created_at, item.id)):
        branch_id = str(synthesis.branch_id or "").strip()
        if not branch_id:
            continue
        brief = brief_by_branch.get(branch_id)
        if brief and brief.latest_synthesis_id and brief.latest_synthesis_id != synthesis.id:
            continue
        by_branch[branch_id] = synthesis
    if by_branch:
        return list(by_branch.values())
    latest: dict[str, BranchSynthesis] = {}
    for synthesis in sorted(syntheses, key=lambda item: (item.created_at, item.id)):
        branch_id = str(synthesis.branch_id or synthesis.task_id or "").strip()
        if branch_id:
            latest[branch_id] = synthesis
    return list(latest.values())


def derive_claim_units(
    *,
    claim_verifier: ClaimVerifier,
    task: ResearchTask,
    synthesis: BranchSynthesis,
    created_by: str,
    existing_claim_units: list[ClaimUnit] | None = None,
) -> list[ClaimUnit]:
    existing = list(existing_claim_units or [])
    if existing:
        return [copy.deepcopy(item) for item in existing]

    seed_text = "\n".join(_dedupe_texts([*synthesis.findings, synthesis.summary]))
    if hasattr(claim_verifier, "extract_claims"):
        extracted_claims = claim_verifier.extract_claims(seed_text or synthesis.summary, max_claims=8)
    else:
        extracted_claims = _dedupe_texts([*(synthesis.findings or []), synthesis.summary])[:8]
    units: list[ClaimUnit] = []
    for index, claim in enumerate(extracted_claims, 1):
        units.append(
            ClaimUnit(
                id=support._new_id("claim"),
                task_id=task.id,
                branch_id=task.branch_id,
                claim=claim,
                claim_provenance={
                    "source": "branch_synthesis",
                    "synthesis_id": synthesis.id,
                    "finding_index": index,
                    "revision_brief_id": synthesis.revision_brief_id or task.revision_brief_id,
                },
                evidence_passage_ids=list(synthesis.evidence_passage_ids),
                citation_urls=list(synthesis.citation_urls),
                created_by=created_by,
                metadata={
                    "objective": synthesis.objective,
                    "task_kind": task.task_kind,
                    "task_id": task.id,
                },
            )
        )
    return units


def derive_coverage_obligations(
    *,
    research_brief: ResearchBriefArtifact | None,
    task: ResearchTask,
    branch_id: str | None,
    revision_brief: BranchRevisionBrief | None = None,
    created_by: str = "supervisor",
    existing_obligations: list[CoverageObligation] | None = None,
) -> list[CoverageObligation]:
    existing = list(existing_obligations or [])
    if existing:
        return [copy.deepcopy(item) for item in existing]

    sources: list[tuple[str, str, list[str]]] = []
    if revision_brief and revision_brief.completion_criteria:
        for criterion in revision_brief.completion_criteria:
            sources.append(("revision_brief", criterion, [criterion]))
    if task.acceptance_criteria:
        for criterion in task.acceptance_criteria:
            sources.append(("task.acceptance_criteria", criterion, [criterion]))
    if not sources and research_brief:
        for criterion in _dedupe_texts(
            list(research_brief.core_questions)
            + list(research_brief.coverage_dimensions)
            + list(research_brief.acceptance_criteria)
        ):
            sources.append(("research_brief", criterion, [criterion]))

    obligations: list[CoverageObligation] = []
    for source, target, criteria in sources:
        obligations.append(
            CoverageObligation(
                id=support._new_id("obligation"),
                task_id=task.id,
                branch_id=branch_id,
                source=source,
                target=target,
                completion_criteria=_dedupe_texts(criteria),
                created_by=created_by,
                metadata={
                    "task_kind": task.task_kind,
                    "revision_brief_id": revision_brief.id if revision_brief else task.revision_brief_id,
                },
            )
        )
    return obligations


def ground_claim_units(
    *,
    claim_verifier: ClaimVerifier,
    claim_units: list[ClaimUnit],
    passages: list[dict[str, Any]],
    created_by: str = "verifier",
) -> list[ClaimGroundingResult]:
    results: list[ClaimGroundingResult] = []
    for claim_unit in claim_units:
        check = claim_verifier.verify_claim_unit(
            claim_unit.to_dict(),
            list(passages),
        )
        if check.status == ClaimStatus.VERIFIED:
            status = "grounded"
            severity = "low"
        elif check.status == ClaimStatus.CONTRADICTED:
            status = "contradicted"
            severity = "high"
        else:
            status = "unsupported"
            severity = "medium"
        results.append(
            ClaimGroundingResult(
                id=support._new_id("claim_grounding"),
                task_id=claim_unit.task_id,
                branch_id=claim_unit.branch_id,
                claim_id=claim_unit.id,
                status=status,
                summary=check.notes,
                evidence_urls=list(check.evidence_urls),
                evidence_passage_ids=list(check.evidence_passage_ids),
                severity=severity,
                created_by=created_by,
                metadata={
                    "claim": claim_unit.claim,
                    "score": check.score,
                    "evidence_passages": list(check.evidence_passages),
                },
            )
        )
    return results


def evaluate_obligations(
    *,
    task: ResearchTask,
    synthesis: BranchSynthesis,
    obligations: list[CoverageObligation],
    claim_units: list[ClaimUnit],
    grounding_results: list[ClaimGroundingResult],
    created_by: str = "verifier",
) -> list[CoverageEvaluationResult]:
    grounding_by_claim = {item.claim_id: item for item in grounding_results}
    grounded_claims = [
        claim
        for claim in claim_units
        if grounding_by_claim.get(claim.id) and grounding_by_claim[claim.id].status == "grounded"
    ]
    all_claim_text = "\n".join(item.claim for item in grounded_claims)
    synthesis_text = "\n".join([synthesis.summary, *synthesis.findings, all_claim_text])

    results: list[CoverageEvaluationResult] = []
    for obligation in obligations:
        criteria = obligation.completion_criteria or [obligation.target]
        covered = [criterion for criterion in criteria if _match_text(synthesis_text, criterion)]
        status = "unsatisfied"
        if covered and len(covered) == len(criteria):
            status = "satisfied"
        elif covered:
            status = "partially_satisfied"
        elif grounded_claims and _match_text(all_claim_text, obligation.target):
            status = "partially_satisfied"
        summary = (
            f"obligation satisfied: {obligation.target}"
            if status == "satisfied"
            else (
                f"obligation partially satisfied: {obligation.target}"
                if status == "partially_satisfied"
                else f"obligation not yet satisfied: {obligation.target}"
            )
        )
        evidence_urls = list(
            dict.fromkeys(
                url
                for claim in grounded_claims
                if _match_text(claim.claim, obligation.target)
                for url in claim.citation_urls
                if url
            )
        ) or list(synthesis.citation_urls)
        evidence_passage_ids = list(
            dict.fromkeys(
                passage_id
                for claim in grounded_claims
                if _match_text(claim.claim, obligation.target)
                for passage_id in claim.evidence_passage_ids
                if passage_id
            )
        ) or list(synthesis.evidence_passage_ids)
        results.append(
            CoverageEvaluationResult(
                id=support._new_id("coverage_eval"),
                task_id=task.id,
                branch_id=task.branch_id,
                obligation_id=obligation.id,
                status=status,
                summary=summary,
                evidence_urls=evidence_urls,
                evidence_passage_ids=evidence_passage_ids,
                created_by=created_by,
                metadata={
                    "covered_criteria": covered,
                    "missing_criteria": [criterion for criterion in criteria if criterion not in covered],
                    "target": obligation.target,
                },
            )
        )
    return results


def evaluate_consistency(
    *,
    claim_verifier: ClaimVerifier,
    claim_units: list[ClaimUnit],
    grounding_results: list[ClaimGroundingResult],
    all_claim_units: list[ClaimUnit],
    all_grounding_results: list[ClaimGroundingResult],
    created_by: str = "verifier",
) -> list[ConsistencyResult]:
    claim_by_id = {item.id: item for item in all_claim_units}
    grounding_by_claim = {item.claim_id: item for item in all_grounding_results}
    results: list[ConsistencyResult] = []
    seen_pairs: set[tuple[str, str]] = set()
    for claim in claim_units:
        grounding = grounding_by_claim.get(claim.id)
        if grounding is None or grounding.status != "grounded":
            continue
        for other in all_claim_units:
            if other.id == claim.id or other.branch_id == claim.branch_id:
                continue
            other_grounding = grounding_by_claim.get(other.id)
            if other_grounding is None or other_grounding.status != "grounded":
                continue
            pair = tuple(sorted([claim.id, other.id]))
            if pair in seen_pairs:
                continue
            comparison = claim_verifier.compare_claims(claim.claim, other.claim)
            if comparison != "contradicted":
                continue
            seen_pairs.add(pair)
            related_branch_ids = _dedupe_texts([claim.branch_id, other.branch_id])
            results.append(
                ConsistencyResult(
                    id=support._new_id("consistency"),
                    task_id=claim.task_id,
                    branch_id=claim.branch_id,
                    claim_ids=[claim.id, other.id],
                    related_branch_ids=related_branch_ids,
                    status="contradicted",
                    summary=f"claims conflict across branches: {claim.claim}",
                    evidence_urls=_dedupe_texts(grounding.evidence_urls + other_grounding.evidence_urls),
                    evidence_passage_ids=_dedupe_texts(
                        grounding.evidence_passage_ids + other_grounding.evidence_passage_ids
                    ),
                    created_by=created_by,
                    metadata={
                        "left_claim": claim.claim,
                        "right_claim": other.claim,
                        "left_branch_id": claim.branch_id,
                        "right_branch_id": other.branch_id,
                        "left_task_id": claim.task_id,
                        "right_task_id": other.task_id,
                        "related_claims": {
                            item.id: item.claim
                            for item in (claim, other)
                            if item.id
                        },
                    },
                )
            )
    return results


def aggregate_revision_issues(
    *,
    task: ResearchTask,
    claim_units: list[ClaimUnit],
    obligations: list[CoverageObligation],
    grounding_results: list[ClaimGroundingResult],
    coverage_results: list[CoverageEvaluationResult],
    consistency_results: list[ConsistencyResult],
    created_by: str = "verifier",
) -> list[RevisionIssue]:
    claim_by_id = {item.id: item for item in claim_units}
    obligation_by_id = {item.id: item for item in obligations}
    issues: list[RevisionIssue] = []

    for result in grounding_results:
        if result.status == "grounded":
            continue
        claim = claim_by_id.get(result.claim_id)
        if result.status == "contradicted":
            recommended_action = "spawn_counterevidence_branch"
            severity = "high"
        else:
            recommended_action = "patch_branch"
            severity = "medium"
        claim_text = claim.claim if claim else result.metadata.get("claim") or "claim"
        issues.append(
            RevisionIssue(
                id=support._new_id("issue"),
                task_id=task.id,
                branch_id=task.branch_id,
                issue_type="claim_grounding",
                summary=f"{claim_text} -> {result.status}",
                severity=severity,
                blocking=True,
                recommended_action=recommended_action,
                claim_ids=[result.claim_id],
                artifact_ids=[result.id],
                evidence_urls=list(result.evidence_urls),
                evidence_passage_ids=list(result.evidence_passage_ids),
                suggested_queries=[claim_text],
                created_by=created_by,
                metadata={"issue_key": f"claim:{result.claim_id}:{result.status}"},
            )
        )

    for result in coverage_results:
        if result.status == "satisfied":
            continue
        obligation = obligation_by_id.get(result.obligation_id)
        blocking = result.status in {"unsatisfied", "unresolved"}
        issues.append(
            RevisionIssue(
                id=support._new_id("issue"),
                task_id=task.id,
                branch_id=task.branch_id,
                issue_type="coverage_obligation",
                summary=result.summary,
                severity="high" if blocking else "medium",
                blocking=blocking,
                recommended_action="patch_branch" if blocking else "spawn_follow_up_branch",
                obligation_ids=[result.obligation_id],
                artifact_ids=[result.id],
                evidence_urls=list(result.evidence_urls),
                evidence_passage_ids=list(result.evidence_passage_ids),
                suggested_queries=[obligation.target] if obligation else [],
                created_by=created_by,
                metadata={"issue_key": f"obligation:{result.obligation_id}:{result.status}"},
            )
        )

    for result in consistency_results:
        if result.status != "contradicted":
            continue
        issues.append(
            RevisionIssue(
                id=support._new_id("issue"),
                task_id=task.id,
                branch_id=task.branch_id,
                issue_type="consistency_conflict",
                summary=result.summary,
                severity="critical",
                blocking=True,
                recommended_action="spawn_counterevidence_branch",
                consistency_result_ids=[result.id],
                claim_ids=list(result.claim_ids),
                artifact_ids=[result.id],
                evidence_urls=list(result.evidence_urls),
                evidence_passage_ids=list(result.evidence_passage_ids),
                created_by=created_by,
                metadata={"issue_key": f"consistency:{':'.join(sorted(result.claim_ids))}"},
            )
        )

    deduped: dict[str, RevisionIssue] = {}
    for issue in issues:
        key = str(issue.metadata.get("issue_key") or issue.id)
        deduped[key] = issue
    return list(deduped.values())


def build_gap_result(
    *,
    obligations: list[CoverageObligation],
    coverage_results: list[CoverageEvaluationResult],
    fallback_result: GapAnalysisResult | None = None,
    fallback_analysis: str = "",
    fallback_queries: list[str] | None = None,
) -> GapAnalysisResult:
    results_by_obligation = {item.obligation_id: item for item in coverage_results}
    satisfied = 0.0
    covered_aspects: list[str] = []
    gaps: list[AnalyzerKnowledgeGap] = []
    suggested_queries = _dedupe_texts(list(fallback_queries or []))
    for obligation in obligations:
        result = results_by_obligation.get(obligation.id)
        if result is None:
            gaps.append(
                AnalyzerKnowledgeGap(
                    aspect=obligation.target,
                    importance="high",
                    reason="obligation has not been evaluated",
                )
            )
            suggested_queries.append(obligation.target)
            continue
        if result.status == "satisfied":
            satisfied += 1.0
            covered_aspects.append(obligation.target)
        elif result.status == "partially_satisfied":
            satisfied += 0.5
            gaps.append(
                AnalyzerKnowledgeGap(
                    aspect=obligation.target,
                    importance="medium",
                    reason=result.summary,
                )
            )
            suggested_queries.append(obligation.target)
        else:
            gaps.append(
                AnalyzerKnowledgeGap(
                    aspect=obligation.target,
                    importance="high",
                    reason=result.summary,
                )
            )
            suggested_queries.append(obligation.target)
    total = len(obligations)
    overall_coverage = satisfied / total if total else 1.0
    confidence = 1.0 if total else 0.8
    if fallback_result is not None:
        overall_coverage = min(
            overall_coverage,
            max(0.0, min(1.0, float(fallback_result.overall_coverage))),
        )
        confidence = min(
            confidence,
            max(0.0, min(1.0, float(fallback_result.confidence))),
        )
        covered_aspects = _dedupe_texts(covered_aspects + list(fallback_result.covered_aspects))
        suggested_queries = _dedupe_texts(suggested_queries + list(fallback_result.suggested_queries))
        seen_gap_keys = {
            (str(gap.aspect or "").strip().lower(), str(gap.reason or "").strip().lower())
            for gap in gaps
        }
        for gap in fallback_result.gaps:
            key = (
                str(gap.aspect or "").strip().lower(),
                str(gap.reason or "").strip().lower(),
            )
            if key in seen_gap_keys:
                continue
            seen_gap_keys.add(key)
            gaps.append(
                AnalyzerKnowledgeGap(
                    aspect=gap.aspect,
                    importance=gap.importance,
                    reason=gap.reason,
                )
            )
        if not fallback_analysis:
            fallback_analysis = fallback_result.analysis
    analysis_parts = _dedupe_texts(
        [
            fallback_analysis,
            (
                "coverage obligations evaluated from authoritative branch contracts"
                if obligations
                else "coverage evaluated from fallback verifier and branch contracts"
            ),
        ]
    )
    return GapAnalysisResult(
        overall_coverage=overall_coverage,
        confidence=confidence,
        gaps=gaps,
        suggested_queries=_dedupe_texts(suggested_queries),
        covered_aspects=_dedupe_texts(covered_aspects),
        analysis="；".join(analysis_parts),
        is_sufficient=overall_coverage >= 0.8 and not any(g.importance == "high" for g in gaps),
    )


def summarize_issue_statuses(issues: list[RevisionIssue]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for issue in sorted(issues, key=lambda item: (item.created_at, item.id)):
        rows.append(
            {
                "issue_id": issue.id,
                "branch_id": issue.branch_id,
                "task_id": issue.task_id,
                "issue_type": issue.issue_type,
                "status": issue.status,
                "blocking": issue.blocking,
                "severity": issue.severity,
                "recommended_action": issue.recommended_action,
            }
        )
    return rows


def summarize_revision_lineage(
    *,
    revision_briefs: list[BranchRevisionBrief],
    issues: list[RevisionIssue],
) -> list[dict[str, Any]]:
    issues_by_id = {issue.id: issue for issue in issues}
    lineage: list[dict[str, Any]] = []
    for brief in sorted(revision_briefs, key=lambda item: (item.created_at, item.id)):
        lineage.append(
            {
                "revision_brief_id": brief.id,
                "revision_kind": brief.revision_kind,
                "target_branch_id": brief.target_branch_id,
                "target_task_id": brief.target_task_id,
                "issue_ids": list(brief.issue_ids),
                "open_issue_ids": [
                    issue_id
                    for issue_id in brief.issue_ids
                    if issues_by_id.get(issue_id) and issues_by_id[issue_id].status in {"open", "accepted"}
                ],
                "resolved_issue_ids": [
                    issue_id
                    for issue_id in brief.issue_ids
                    if issues_by_id.get(issue_id) and issues_by_id[issue_id].status == "resolved"
                ],
            }
        )
    return lineage


__all__ = [
    "aggregate_revision_issues",
    "build_gap_result",
    "derive_claim_units",
    "derive_coverage_obligations",
    "evaluate_consistency",
    "evaluate_obligations",
    "ground_claim_units",
    "latest_branch_syntheses",
    "summarize_issue_statuses",
    "summarize_revision_lineage",
]
