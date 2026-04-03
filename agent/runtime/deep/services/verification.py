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
    AnswerUnit,
    BranchBrief,
    BranchRevisionBrief,
    BranchSynthesis,
    BranchValidationSummary,
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


def _claim_evidence_urls(claim: ClaimUnit, grounding: ClaimGroundingResult | None) -> list[str]:
    return _dedupe_texts(
        list(grounding.evidence_urls if grounding else [])
        + list(claim.citation_urls)
    )


def _claim_evidence_passage_ids(claim: ClaimUnit, grounding: ClaimGroundingResult | None) -> list[str]:
    return _dedupe_texts(
        list(grounding.evidence_passage_ids if grounding else [])
        + list(claim.evidence_passage_ids)
    )


def _supported_grounded_claims(
    *,
    claims: list[ClaimUnit],
    grounding_by_claim: dict[str, ClaimGroundingResult],
    target: str,
) -> list[tuple[ClaimUnit, ClaimGroundingResult]]:
    matches: list[tuple[ClaimUnit, ClaimGroundingResult]] = []
    for claim in claims:
        grounding = grounding_by_claim.get(claim.id)
        if grounding is None or grounding.status != "grounded":
            continue
        evidence_urls = _claim_evidence_urls(claim, grounding)
        evidence_passage_ids = _claim_evidence_passage_ids(claim, grounding)
        if not evidence_urls and not evidence_passage_ids:
            continue
        if _match_text(claim.claim, target):
            matches.append((claim, grounding))
    return matches


def claim_units_to_answer_units(claim_units: list[ClaimUnit] | None) -> list[AnswerUnit]:
    return [AnswerUnit.from_claim_unit(item) for item in claim_units or []]


def answer_units_to_claim_units(answer_units: list[AnswerUnit] | None) -> list[ClaimUnit]:
    return [item.to_claim_unit() for item in answer_units or []]


def _infer_answer_unit_type(text: str, *, dependent_answer_unit_ids: list[str] | None = None) -> str:
    normalized = str(text or "").strip().lower()
    if dependent_answer_unit_ids:
        return "composite_conclusion"
    if re.search(r"\b(20\d{2}|\d{4}-\d{2}-\d{2})\b", normalized):
        return "date"
    if re.search(r"\d+(?:\.\d+)?%?", normalized):
        return "numeric"
    if any(marker in normalized for marker in ("increase", "growth", "decline", "trend", "增长", "下降", "上升")):
        return "trend"
    if any(marker in normalized for marker in ("than", "versus", "compared", "高于", "低于", "相比")):
        return "comparison"
    return "claim"


def _answer_unit_targets(answer_unit: AnswerUnit) -> list[str]:
    metadata = dict(answer_unit.metadata or {})
    return _dedupe_texts(
        list(metadata.get("coverage_targets") or [])
        + list(metadata.get("obligation_targets") or [])
    )


def _answer_unit_links_to_obligation(
    answer_unit: AnswerUnit,
    obligation: CoverageObligation,
    *,
    total_obligations: int,
) -> bool:
    if obligation.id in set(answer_unit.obligation_ids):
        return True
    explicit_targets = set(_answer_unit_targets(answer_unit))
    if obligation.target in explicit_targets:
        return True
    if explicit_targets and any(criterion in explicit_targets for criterion in obligation.completion_criteria):
        return True
    return total_obligations == 1 and not answer_unit.obligation_ids and not explicit_targets


def _filter_admissible_passages(passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    admissible: list[dict[str, Any]] = []
    for passage in passages:
        if not isinstance(passage, dict):
            continue
        passage_id = str(passage.get("passage_id") or passage.get("id") or "").strip()
        url = str(passage.get("url") or "").strip()
        text = str(passage.get("text") or "").strip()
        has_locator = bool(
            passage.get("quote")
            or passage.get("heading_path")
            or passage.get("locator")
            or passage.get("document_id")
        )
        if not passage_id or not url or not text or not has_locator:
            continue
        if passage.get("admissible") is False:
            continue
        payload = dict(passage)
        payload["passage_id"] = passage_id
        payload["admissible"] = True
        admissible.append(payload)
    return admissible


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
    return answer_units_to_claim_units(
        derive_answer_units(
            claim_verifier=claim_verifier,
            task=task,
            synthesis=synthesis,
            created_by=created_by,
            existing_claim_units=existing_claim_units,
        )
    )


def derive_answer_units(
    *,
    claim_verifier: ClaimVerifier,
    task: ResearchTask,
    synthesis: BranchSynthesis,
    created_by: str,
    existing_answer_units: list[AnswerUnit] | None = None,
    existing_claim_units: list[ClaimUnit] | None = None,
) -> list[AnswerUnit]:
    if existing_answer_units:
        return [copy.deepcopy(item) for item in existing_answer_units]
    existing_claims = list(existing_claim_units or [])
    if existing_claims:
        return claim_units_to_answer_units(existing_claims)

    raw_answer_units = synthesis.metadata.get("answer_units") if isinstance(synthesis.metadata, dict) else None
    units: list[AnswerUnit] = []
    if isinstance(raw_answer_units, list) and raw_answer_units:
        for index, item in enumerate(raw_answer_units, 1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("claim") or "").strip()
            if not text:
                continue
            dependent_ids = _dedupe_texts(list(item.get("dependent_answer_unit_ids") or []))
            units.append(
                AnswerUnit(
                    id=str(item.get("id") or "").strip() or support._new_id("answer_unit"),
                    task_id=task.id,
                    branch_id=task.branch_id,
                    text=text,
                    unit_type=str(item.get("unit_type") or _infer_answer_unit_type(text, dependent_answer_unit_ids=dependent_ids)),
                    provenance=dict(item.get("provenance") or {
                        "source": "researcher_bundle",
                        "synthesis_id": synthesis.id,
                        "index": index,
                    }),
                    supporting_passage_ids=_dedupe_texts(
                        list(item.get("supporting_passage_ids") or item.get("evidence_passage_ids") or synthesis.evidence_passage_ids)
                    ),
                    citation_urls=_dedupe_texts(list(item.get("citation_urls") or synthesis.citation_urls)),
                    obligation_ids=_dedupe_texts(list(item.get("obligation_ids") or [])),
                    dependent_answer_unit_ids=dependent_ids,
                    required=bool(item.get("required", True)),
                    created_by=created_by,
                    metadata={
                        "objective": synthesis.objective,
                        "task_kind": task.task_kind,
                        "task_id": task.id,
                        **dict(item.get("metadata") or {}),
                    },
                )
            )
    if units:
        return units

    seed_text = "\n".join(_dedupe_texts([*(synthesis.findings or []), synthesis.summary]))
    if hasattr(claim_verifier, "extract_claims"):
        extracted_claims = claim_verifier.extract_claims(seed_text or synthesis.summary, max_claims=8)
    else:
        extracted_claims = _dedupe_texts([*(synthesis.findings or []), synthesis.summary])[:8]

    default_targets = list(task.acceptance_criteria) if len(task.acceptance_criteria) == 1 else []
    for index, claim in enumerate(extracted_claims, 1):
        units.append(
            AnswerUnit(
                id=support._new_id("answer_unit"),
                task_id=task.id,
                branch_id=task.branch_id,
                text=claim,
                unit_type=_infer_answer_unit_type(claim),
                provenance={
                    "source": "researcher_synthesis",
                    "synthesis_id": synthesis.id,
                    "finding_index": index,
                    "revision_brief_id": synthesis.revision_brief_id or task.revision_brief_id,
                },
                supporting_passage_ids=list(synthesis.evidence_passage_ids),
                citation_urls=list(synthesis.citation_urls),
                created_by=created_by,
                metadata={
                    "objective": synthesis.objective,
                    "task_kind": task.task_kind,
                    "task_id": task.id,
                    "coverage_targets": default_targets,
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
    claim_units: list[ClaimUnit] | None,
    passages: list[dict[str, Any]],
    answer_units: list[AnswerUnit] | None = None,
    created_by: str = "verifier",
) -> list[ClaimGroundingResult]:
    resolved_answer_units = list(answer_units or claim_units_to_answer_units(claim_units or []))
    admissible_passages = _filter_admissible_passages(list(passages))
    results: list[ClaimGroundingResult] = []
    result_by_unit_id: dict[str, ClaimGroundingResult] = {}
    deferred_composites: list[AnswerUnit] = []
    for answer_unit in resolved_answer_units:
        if answer_unit.unit_type == "composite_conclusion" and answer_unit.dependent_answer_unit_ids:
            deferred_composites.append(answer_unit)
            continue
        candidate_passages = list(admissible_passages)
        if answer_unit.supporting_passage_ids:
            allowed_ids = set(answer_unit.supporting_passage_ids)
            filtered = [
                item
                for item in candidate_passages
                if str(item.get("passage_id") or item.get("id") or "").strip() in allowed_ids
            ]
            if filtered:
                candidate_passages = filtered
        check = claim_verifier.verify_claim_unit(
            {
                "id": answer_unit.id,
                "claim": answer_unit.text,
                "unit_type": answer_unit.unit_type,
                "required": answer_unit.required,
            },
            candidate_passages,
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
                task_id=answer_unit.task_id,
                branch_id=answer_unit.branch_id,
                claim_id=answer_unit.id,
                status=status,
                summary=check.notes,
                evidence_urls=list(check.evidence_urls),
                evidence_passage_ids=list(check.evidence_passage_ids),
                severity=severity,
                created_by=created_by,
                metadata={
                    "claim": answer_unit.text,
                    "answer_unit_id": answer_unit.id,
                    "unit_type": answer_unit.unit_type,
                    "required": answer_unit.required,
                    "score": check.score,
                    "evidence_passages": list(check.evidence_passages),
                },
            )
        )
        result_by_unit_id[answer_unit.id] = results[-1]

    for answer_unit in deferred_composites:
        dependency_results = [
            result_by_unit_id.get(item_id)
            for item_id in answer_unit.dependent_answer_unit_ids
            if result_by_unit_id.get(item_id) is not None
        ]
        if dependency_results and all(item.status == "grounded" for item in dependency_results):
            status = "grounded"
            severity = "low"
            summary = "supported by dependent answer units"
        elif any(item.status == "contradicted" for item in dependency_results):
            status = "contradicted"
            severity = "high"
            summary = "contradicted by dependent answer units"
        else:
            status = "unsupported"
            severity = "medium"
            summary = "dependent answer units are not fully grounded"
        results.append(
            ClaimGroundingResult(
                id=support._new_id("claim_grounding"),
                task_id=answer_unit.task_id,
                branch_id=answer_unit.branch_id,
                claim_id=answer_unit.id,
                status=status,
                summary=summary,
                evidence_urls=_dedupe_texts(
                    [url for item in dependency_results for url in item.evidence_urls]
                ),
                evidence_passage_ids=_dedupe_texts(
                    [passage_id for item in dependency_results for passage_id in item.evidence_passage_ids]
                ),
                severity=severity,
                created_by=created_by,
                metadata={
                    "claim": answer_unit.text,
                    "answer_unit_id": answer_unit.id,
                    "unit_type": answer_unit.unit_type,
                    "required": answer_unit.required,
                    "dependent_answer_unit_ids": list(answer_unit.dependent_answer_unit_ids),
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
    answer_units: list[AnswerUnit] | None = None,
    created_by: str = "verifier",
) -> list[CoverageEvaluationResult]:
    resolved_answer_units = list(answer_units or claim_units_to_answer_units(claim_units))
    grounding_by_claim = {item.claim_id: item for item in grounding_results}
    grounded_answer_units = [
        answer_unit
        for answer_unit in resolved_answer_units
        if grounding_by_claim.get(answer_unit.id) and grounding_by_claim[answer_unit.id].status == "grounded"
    ]

    results: list[CoverageEvaluationResult] = []
    for obligation in obligations:
        criteria = _dedupe_texts(obligation.completion_criteria or [obligation.target])
        covered: list[str] = []
        supported_answer_unit_ids: list[str] = []
        evidence_urls: list[str] = []
        evidence_passage_ids: list[str] = []
        criterion_answer_unit_map: dict[str, list[str]] = {}

        linked_answer_units = [
            answer_unit
            for answer_unit in grounded_answer_units
            if _answer_unit_links_to_obligation(
                answer_unit,
                obligation,
                total_obligations=len(obligations),
            )
        ]

        for criterion in criteria:
            criterion_matches = [
                answer_unit
                for answer_unit in linked_answer_units
                if criterion in set(_answer_unit_targets(answer_unit))
            ]
            if not criterion_matches and linked_answer_units and len(criteria) == 1:
                criterion_matches = list(linked_answer_units)
            if not criterion_matches:
                continue
            covered.append(criterion)
            answer_unit_ids = [answer_unit.id for answer_unit in criterion_matches]
            criterion_answer_unit_map[criterion] = answer_unit_ids
            supported_answer_unit_ids.extend(answer_unit_ids)
            for answer_unit in criterion_matches:
                grounding = grounding_by_claim.get(answer_unit.id)
                if grounding is None:
                    continue
                evidence_urls.extend(_dedupe_texts(list(grounding.evidence_urls) + list(answer_unit.citation_urls)))
                evidence_passage_ids.extend(
                    _dedupe_texts(list(grounding.evidence_passage_ids) + list(answer_unit.supporting_passage_ids))
                )

        covered = _dedupe_texts(covered)
        supported_answer_unit_ids = _dedupe_texts(supported_answer_unit_ids)
        evidence_urls = _dedupe_texts(evidence_urls)
        evidence_passage_ids = _dedupe_texts(evidence_passage_ids)
        missing_criteria = [criterion for criterion in criteria if criterion not in covered]

        status = "unsatisfied"
        if covered and len(covered) == len(criteria):
            status = "satisfied"
        elif covered or linked_answer_units:
            status = "partially_satisfied"

        if status == "satisfied":
            summary = f"obligation satisfied with grounded claim coverage: {obligation.target}"
        elif status == "partially_satisfied":
            summary = (
                f"obligation partially satisfied; grounded evidence covers "
                f"{len(covered)}/{len(criteria)} criteria: {obligation.target}"
            )
        else:
            summary = f"obligation not yet satisfied by grounded evidence: {obligation.target}"

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
                    "missing_criteria": missing_criteria,
                    "target": obligation.target,
                    "supported_answer_unit_ids": supported_answer_unit_ids,
                    "supported_claim_ids": supported_answer_unit_ids,
                    "criterion_answer_unit_map": criterion_answer_unit_map,
                    "criterion_claim_map": criterion_answer_unit_map,
                    "target_answer_unit_ids": [answer_unit.id for answer_unit in linked_answer_units],
                    "target_claim_ids": [answer_unit.id for answer_unit in linked_answer_units],
                    "used_grounded_claims_only": True,
                    "used_synthesis_summary_as_authority": False,
                    "used_obligation_mapping": True,
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
    answer_units: list[AnswerUnit] | None = None,
    all_answer_units: list[AnswerUnit] | None = None,
    created_by: str = "verifier",
) -> list[ConsistencyResult]:
    resolved_answer_units = list(answer_units or claim_units_to_answer_units(claim_units))
    resolved_all_answer_units = list(all_answer_units or claim_units_to_answer_units(all_claim_units))
    grounding_by_claim = {item.claim_id: item for item in all_grounding_results}
    results: list[ConsistencyResult] = []
    seen_pairs: set[tuple[str, str]] = set()
    for answer_unit in resolved_answer_units:
        grounding = grounding_by_claim.get(answer_unit.id)
        if grounding is None or grounding.status != "grounded":
            continue
        left_scope = set(answer_unit.obligation_ids) | set(_answer_unit_targets(answer_unit))
        for other in resolved_all_answer_units:
            if other.id == answer_unit.id or other.branch_id == answer_unit.branch_id:
                continue
            other_grounding = grounding_by_claim.get(other.id)
            if other_grounding is None or other_grounding.status != "grounded":
                continue
            right_scope = set(other.obligation_ids) | set(_answer_unit_targets(other))
            if left_scope and right_scope and not (left_scope & right_scope):
                continue
            if not left_scope and not right_scope:
                left_tokens = set(_coverage_tokens(answer_unit.text))
                right_tokens = set(_coverage_tokens(other.text))
                if len(left_tokens & right_tokens) < 3:
                    continue
            pair = tuple(sorted([answer_unit.id, other.id]))
            if pair in seen_pairs:
                continue
            comparison = claim_verifier.compare_claims(answer_unit.text, other.text)
            if comparison != "contradicted":
                continue
            seen_pairs.add(pair)
            related_branch_ids = _dedupe_texts([answer_unit.branch_id, other.branch_id])
            results.append(
                ConsistencyResult(
                    id=support._new_id("consistency"),
                    task_id=answer_unit.task_id,
                    branch_id=answer_unit.branch_id,
                    claim_ids=[answer_unit.id, other.id],
                    related_branch_ids=related_branch_ids,
                    status="contradicted",
                    summary=f"claims conflict across branches: {answer_unit.text}",
                    evidence_urls=_dedupe_texts(grounding.evidence_urls + other_grounding.evidence_urls),
                    evidence_passage_ids=_dedupe_texts(
                        grounding.evidence_passage_ids + other_grounding.evidence_passage_ids
                    ),
                    created_by=created_by,
                    metadata={
                        "left_claim": answer_unit.text,
                        "right_claim": other.text,
                        "left_branch_id": answer_unit.branch_id,
                        "right_branch_id": other.branch_id,
                        "left_task_id": answer_unit.task_id,
                        "right_task_id": other.task_id,
                        "related_claims": {
                            item.id: item.text
                            for item in (answer_unit, other)
                            if item.id
                        },
                        "shared_scope": sorted(left_scope & right_scope),
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
    answer_units: list[AnswerUnit] | None = None,
    created_by: str = "verifier",
) -> list[RevisionIssue]:
    resolved_answer_units = list(answer_units or claim_units_to_answer_units(claim_units))
    answer_unit_by_id = {item.id: item for item in resolved_answer_units}
    obligation_by_id = {item.id: item for item in obligations}
    issues: list[RevisionIssue] = []

    for result in grounding_results:
        if result.status == "grounded":
            continue
        answer_unit = answer_unit_by_id.get(result.claim_id)
        if result.status == "contradicted":
            recommended_action = "spawn_counterevidence_branch"
            severity = "high" if (answer_unit.required if answer_unit else True) else "low"
        else:
            recommended_action = "patch_branch"
            severity = "medium" if (answer_unit.required if answer_unit else True) else "low"
        blocking = bool(answer_unit.required) if answer_unit else True
        claim_text = answer_unit.text if answer_unit else result.metadata.get("claim") or "claim"
        issues.append(
            RevisionIssue(
                id=support._new_id("issue"),
                task_id=task.id,
                branch_id=task.branch_id,
                issue_type="claim_grounding",
                summary=f"{claim_text} -> {result.status}",
                severity=severity,
                blocking=blocking,
                recommended_action=recommended_action,
                claim_ids=[result.claim_id],
                artifact_ids=[result.id],
                evidence_urls=list(result.evidence_urls),
                evidence_passage_ids=list(result.evidence_passage_ids),
                suggested_queries=[claim_text],
                created_by=created_by,
                metadata={
                    "issue_key": f"claim:{result.claim_id}:{result.status}",
                    "answer_unit_id": result.claim_id,
                    "unit_type": answer_unit.unit_type if answer_unit else result.metadata.get("unit_type", "claim"),
                    "required": answer_unit.required if answer_unit else result.metadata.get("required", True),
                },
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
                severity="high" if blocking else "low",
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


def build_branch_validation_summary(
    *,
    task: ResearchTask,
    synthesis: BranchSynthesis,
    answer_units: list[AnswerUnit],
    obligations: list[CoverageObligation],
    grounding_results: list[ClaimGroundingResult],
    coverage_results: list[CoverageEvaluationResult],
    consistency_results: list[ConsistencyResult],
    revision_issues: list[RevisionIssue],
    advisory_notes: list[str] | None = None,
    created_by: str = "verifier",
) -> BranchValidationSummary:
    grounding_by_unit = {item.claim_id: item for item in grounding_results}
    supported_answer_unit_ids: list[str] = []
    unsupported_answer_unit_ids: list[str] = []
    contradicted_answer_unit_ids: list[str] = []
    partially_supported_answer_unit_ids: list[str] = []
    for answer_unit in answer_units:
        grounding = grounding_by_unit.get(answer_unit.id)
        if grounding is None:
            unsupported_answer_unit_ids.append(answer_unit.id)
            continue
        if grounding.status == "grounded":
            supported_answer_unit_ids.append(answer_unit.id)
        elif grounding.status == "contradicted":
            contradicted_answer_unit_ids.append(answer_unit.id)
        elif grounding.status == "unresolved":
            partially_supported_answer_unit_ids.append(answer_unit.id)
        else:
            unsupported_answer_unit_ids.append(answer_unit.id)

    satisfied_obligation_ids = [
        item.obligation_id for item in coverage_results if item.status == "satisfied"
    ]
    partially_satisfied_obligation_ids = [
        item.obligation_id for item in coverage_results if item.status == "partially_satisfied"
    ]
    unsatisfied_obligation_ids = [
        item.obligation_id for item in coverage_results if item.status in {"unsatisfied", "unresolved"}
    ]
    issue_ids = [issue.id for issue in revision_issues]
    blocking_issue_ids = [
        issue.id for issue in revision_issues if issue.blocking and issue.status in {"open", "accepted"}
    ]
    ready_for_report = not blocking_issue_ids and not unsatisfied_obligation_ids and not contradicted_answer_unit_ids
    summary_parts = _dedupe_texts(
        [
            f"supported={len(supported_answer_unit_ids)}/{len(answer_units)}",
            f"unsupported={len(unsupported_answer_unit_ids)}" if unsupported_answer_unit_ids else "",
            f"contradicted={len(contradicted_answer_unit_ids)}" if contradicted_answer_unit_ids else "",
            f"unsatisfied_obligations={len(unsatisfied_obligation_ids)}" if unsatisfied_obligation_ids else "",
            f"blocking_issues={len(blocking_issue_ids)}" if blocking_issue_ids else "no blocking validation debt",
        ]
    )
    return BranchValidationSummary(
        id=support._new_id("branch_validation"),
        task_id=task.id,
        branch_id=task.branch_id,
        synthesis_id=synthesis.id,
        answer_unit_ids=[item.id for item in answer_units],
        obligation_ids=[item.id for item in obligations],
        consistency_result_ids=[item.id for item in consistency_results],
        issue_ids=issue_ids,
        blocking_issue_ids=blocking_issue_ids,
        supported_answer_unit_ids=_dedupe_texts(supported_answer_unit_ids),
        partially_supported_answer_unit_ids=_dedupe_texts(partially_supported_answer_unit_ids),
        unsupported_answer_unit_ids=_dedupe_texts(unsupported_answer_unit_ids),
        contradicted_answer_unit_ids=_dedupe_texts(contradicted_answer_unit_ids),
        satisfied_obligation_ids=_dedupe_texts(satisfied_obligation_ids),
        partially_satisfied_obligation_ids=_dedupe_texts(partially_satisfied_obligation_ids),
        unsatisfied_obligation_ids=_dedupe_texts(unsatisfied_obligation_ids),
        blocking=bool(blocking_issue_ids),
        ready_for_report=ready_for_report,
        advisory_notes=_dedupe_texts(list(advisory_notes or [])),
        summary="; ".join(summary_parts),
        created_by=created_by,
        metadata={
            "claim_ids": [item.id for item in answer_units],
            "required_answer_unit_ids": [item.id for item in answer_units if item.required],
        },
    )


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
    authoritative_gaps: list[AnalyzerKnowledgeGap] = []
    advisory_gaps: list[AnalyzerKnowledgeGap] = []
    suggested_queries = _dedupe_texts(list(fallback_queries or []))
    blocking_gap_count = 0
    for obligation in obligations:
        result = results_by_obligation.get(obligation.id)
        if result is None:
            authoritative_gaps.append(
                AnalyzerKnowledgeGap(
                    aspect=obligation.target,
                    importance="high",
                    reason="obligation has not been evaluated",
                    advisory=False,
                )
            )
            suggested_queries.append(obligation.target)
            blocking_gap_count += 1
            continue
        if result.status == "satisfied":
            satisfied += 1.0
            covered_aspects.append(obligation.target)
        elif result.status == "partially_satisfied":
            satisfied += 0.5
            authoritative_gaps.append(
                AnalyzerKnowledgeGap(
                    aspect=obligation.target,
                    importance="medium",
                    reason=result.summary,
                    advisory=False,
                )
            )
            suggested_queries.append(obligation.target)
        else:
            authoritative_gaps.append(
                AnalyzerKnowledgeGap(
                    aspect=obligation.target,
                    importance="high",
                    reason=result.summary,
                    advisory=False,
                )
            )
            suggested_queries.append(obligation.target)
            blocking_gap_count += 1
    total = len(obligations)
    overall_coverage = satisfied / total if total else 1.0
    confidence = 1.0 if total else 0.8
    if fallback_result is not None:
        confidence = max(
            confidence,
            max(0.0, min(1.0, float(fallback_result.confidence))),
        )
        covered_aspects = _dedupe_texts(covered_aspects + list(fallback_result.covered_aspects))
        suggested_queries = _dedupe_texts(suggested_queries + list(fallback_result.suggested_queries))
        for gap in fallback_result.gaps:
            advisory_gaps.append(
                AnalyzerKnowledgeGap(
                    aspect=gap.aspect,
                    importance=gap.importance,
                    reason=gap.reason,
                    advisory=True,
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
            (
                f"blocking verification debt={blocking_gap_count}"
                if blocking_gap_count
                else "no blocking verification debt detected"
            ),
            (
                f"advisory research gaps={len(advisory_gaps)}"
                if advisory_gaps
                else ""
            ),
        ]
    )
    return GapAnalysisResult(
        overall_coverage=overall_coverage,
        confidence=confidence,
        gaps=advisory_gaps,
        suggested_queries=_dedupe_texts(suggested_queries),
        covered_aspects=_dedupe_texts(covered_aspects),
        analysis="；".join(analysis_parts),
        is_sufficient=blocking_gap_count == 0,
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
    "build_branch_validation_summary",
    "build_gap_result",
    "claim_units_to_answer_units",
    "answer_units_to_claim_units",
    "derive_answer_units",
    "derive_claim_units",
    "derive_coverage_obligations",
    "evaluate_consistency",
    "evaluate_obligations",
    "ground_claim_units",
    "latest_branch_syntheses",
    "summarize_issue_statuses",
    "summarize_revision_lineage",
]
