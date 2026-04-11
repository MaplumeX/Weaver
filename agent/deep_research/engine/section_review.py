"""Section draft, review, and report-context helpers for Deep Research."""

from __future__ import annotations

import copy
from typing import Any

from agent.deep_research.agents.reporter import ReportSectionContext
from agent.deep_research.engine.artifact_store import LightweightArtifactStore
from agent.deep_research.engine.section_logic import (
    _branch_title,
    _claim_grounding_ratio,
    _issue_types,
    _resolved_section_reportability,
    _section_admitted_for_report,
    _section_draft_text,
    _section_title,
)
from agent.deep_research.engine.text_analysis import (
    _dedupe_texts,
    _needs_freshness_advisory,
    _text_overlap_score,
)
from agent.deep_research.engine.workflow_state import split_findings as _split_findings
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import (
    ResearchTask,
    SectionCertificationArtifact,
    SectionDraftArtifact,
    SectionReviewArtifact,
    _now_iso,
)

_SECTION_OBJECTIVE_HARD_GATE_THRESHOLD = 0.7
_SECTION_GROUNDING_HARD_GATE_THRESHOLD = 0.6


def build_section_draft(
    task: ResearchTask,
    section: dict[str, Any],
    bundle: dict[str, Any],
    outcome: dict[str, Any],
    created_by: str,
) -> dict[str, Any]:
    summary = str(outcome.get("summary") or "").strip()
    claim_units = [
        item
        for item in list(outcome.get("claim_units") or [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    if not claim_units:
        fallback_passage_ids = [
            str(item.get("id") or "").strip()
            for item in bundle.get("passages", []) or []
            if str(item.get("id") or "").strip()
        ]
        fallback_source_urls = [
            str(item.get("url") or "").strip()
            for item in bundle.get("sources", []) or []
            if str(item.get("url") or "").strip()
        ]
        fallback_claim_texts = _dedupe_texts([summary, *(outcome.get("key_findings") or [])])
        claim_units = [
            {
                "id": f"claim_{index}",
                "text": text,
                "importance": "primary" if index <= 2 else "secondary",
                "evidence_passage_ids": fallback_passage_ids[:1],
                "evidence_urls": fallback_source_urls[:1],
                "grounded": bool(fallback_passage_ids),
            }
            for index, text in enumerate(fallback_claim_texts, 1)
            if text
        ]
    draft = SectionDraftArtifact(
        id=_new_id("section_draft"),
        task_id=task.id,
        section_id=str(task.section_id or ""),
        branch_id=task.branch_id,
        title=_section_title(section) or _branch_title(task),
        objective=str(section.get("objective") or task.objective or task.goal).strip(),
        core_question=str(section.get("core_question") or task.objective or task.goal).strip(),
        summary=summary,
        key_findings=list(outcome.get("key_findings") or _split_findings(summary) or [summary]),
        open_questions=list(outcome.get("open_questions") or []),
        confidence_note=str(outcome.get("confidence_note") or "").strip(),
        source_urls=[str(item.get("url") or "").strip() for item in bundle.get("sources", []) if item.get("url")],
        claim_units=claim_units,
        limitations=list(outcome.get("limitations") or []),
        coverage_summary=copy.deepcopy(outcome.get("coverage_summary") or {}),
        quality_summary=copy.deepcopy(outcome.get("quality_summary") or {}),
        contradiction_summary=copy.deepcopy(outcome.get("contradiction_summary") or {}),
        grounding_summary=copy.deepcopy(outcome.get("grounding_summary") or {}),
        evidence_bundle_id=str(bundle.get("id") or "") or None,
        created_by=created_by,
    ).to_dict()
    draft["section_order"] = int(section.get("section_order", 0) or 0)
    return draft


def build_review_issue(issue_type: str, message: str, *, blocking: bool) -> dict[str, Any]:
    return {
        "id": _new_id("issue"),
        "issue_type": issue_type,
        "message": message,
        "blocking": blocking,
        "status": "open",
        "created_at": _now_iso(),
    }


def review_section_draft(
    *,
    topic: str,
    section_revision_limit: int,
    section: dict[str, Any],
    draft: dict[str, Any],
    bundle: dict[str, Any],
    revision_count: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    draft_text = _section_draft_text(draft)
    objective = str(section.get("objective") or section.get("core_question") or draft.get("objective") or "").strip()
    objective_overlap = _text_overlap_score(objective, draft_text)
    objective_score = 1.0 if objective_overlap >= 0.15 else (0.8 if objective_overlap >= 0.05 else 0.55)

    coverage_summary = dict(draft.get("coverage_summary") or {})
    quality_summary = dict(draft.get("quality_summary") or {})
    contradiction_summary = dict(draft.get("contradiction_summary") or {})
    grounding_summary = dict(draft.get("grounding_summary") or {})

    grounding_ratio = float(
        grounding_summary.get("primary_grounding_ratio")
        if grounding_summary.get("primary_grounding_ratio") is not None
        else _claim_grounding_ratio(draft)
    )
    grounding_score = round(grounding_ratio, 3)
    source_count = len(bundle.get("sources") or [])
    has_primary_sources = source_count > 0 and len(bundle.get("passages") or []) > 0
    has_summary = bool(str(draft.get("summary") or "").strip())
    has_findings = bool([item for item in draft.get("key_findings", []) or [] if str(item).strip()])
    objective_met = bool(str(draft.get("summary") or "").strip()) and (
        bool(coverage_summary.get("coverage_ready"))
        or bool(quality_summary.get("quality_ready"))
        or bool(grounding_summary.get("grounding_ready"))
        or objective_score >= _SECTION_OBJECTIVE_HARD_GATE_THRESHOLD
        or source_count > 0
    )

    blocking_issues: list[dict[str, Any]] = []
    advisory_issues: list[dict[str, Any]] = []
    follow_up_queries: list[str] = []

    if not draft_text:
        blocking_issues.append(
            build_review_issue("objective_not_met", "章节草稿为空，尚未回答核心问题", blocking=True)
        )
    elif not objective_met:
        blocking_issues.append(
            build_review_issue("objective_not_met", "章节尚未稳定回答核心问题", blocking=True)
        )

    if not has_primary_sources:
        blocking_issues.append(
            build_review_issue("insufficient_sources", "缺少可定位来源或 passage，无法支撑主结论", blocking=True)
        )

    if grounding_ratio < _SECTION_GROUNDING_HARD_GATE_THRESHOLD:
        blocking_issues.append(
            build_review_issue(
                "primary_claim_ungrounded",
                f"主结论的证据绑定比例不足 {int(_SECTION_GROUNDING_HARD_GATE_THRESHOLD * 100)}%",
                blocking=True,
            )
        )
        follow_up_queries.extend(
            _dedupe_texts(
                [
                    *(coverage_summary.get("missing_topics") or []),
                    *(draft.get("open_questions") or []),
                    objective,
                    str(section.get("core_question") or ""),
                ]
            )
        )
    elif grounding_ratio < 1.0:
        advisory_issues.append(
            build_review_issue(
                "secondary_claim_ungrounded",
                "仍有部分结论未完全绑定证据，建议在报告中保留限制说明",
                blocking=False,
            )
        )

    if bool(contradiction_summary.get("has_material_conflict")):
        advisory_issues.append(
            build_review_issue(
                "conflicting_evidence",
                "存在需要人工复核的证据冲突，报告中应保留限制说明",
                blocking=False,
            )
        )
    elif bool(contradiction_summary.get("needs_counterevidence_query")):
        advisory_issues.append(
            build_review_issue(
                "limited_source_diversity",
                "当前结论主要来自单一来源域，建议补充对比来源",
                blocking=False,
            )
        )

    if _needs_freshness_advisory(f"{topic} {objective}"):
        published_dates = [
            str(item.get("published_date") or "").strip()
            for item in bundle.get("sources", []) or []
            if str(item.get("published_date") or "").strip()
        ]
        if not published_dates:
            advisory_issues.append(
                build_review_issue(
                    "freshness_risk",
                    "该章节关注最新信息，但来源缺少明确发布时间，默认作为 advisory 处理",
                    blocking=False,
                )
            )

    if not has_summary and not has_findings:
        reportability = "insufficient"
        quality_band = "insufficient"
    elif (
        has_primary_sources
        and grounding_ratio >= 0.85
        and objective_score >= _SECTION_OBJECTIVE_HARD_GATE_THRESHOLD
        and not advisory_issues
    ):
        reportability = "high"
        quality_band = "strong"
    elif has_primary_sources and grounding_ratio >= _SECTION_GROUNDING_HARD_GATE_THRESHOLD and objective_met:
        reportability = "medium"
        quality_band = "supported" if not advisory_issues else "usable_with_limitations"
    else:
        reportability = "low"
        quality_band = "needs_follow_up"

    risk_flags = _issue_types(blocking_issues, advisory_issues)
    suggested_actions = _dedupe_texts(
        [
            "expand_research" if blocking_issues else "",
            "tighten_summary" if has_summary and not objective_met else "",
            "add_citable_sources" if not has_primary_sources else "",
            "ground_primary_claims" if grounding_ratio < _SECTION_GROUNDING_HARD_GATE_THRESHOLD else "",
            (
                "ground_secondary_claims"
                if grounding_ratio >= _SECTION_GROUNDING_HARD_GATE_THRESHOLD and grounding_ratio < 1.0
                else ""
            ),
            "confirm_freshness" if "freshness_risk" in risk_flags else "",
            "manual_review" if reportability == "low" or "freshness_risk" in risk_flags else "",
        ]
    )
    needs_manual_review = reportability == "low" or "freshness_risk" in risk_flags

    if (
        advisory_issues
        and not blocking_issues
        and revision_count < section_revision_limit
        and objective_score < _SECTION_OBJECTIVE_HARD_GATE_THRESHOLD
    ):
        verdict = "revise_section"
    elif blocking_issues:
        verdict = "request_research"
    else:
        verdict = "accept_section"

    review = SectionReviewArtifact(
        id=_new_id("section_review"),
        task_id=str(draft.get("task_id") or ""),
        section_id=str(draft.get("section_id") or ""),
        branch_id=draft.get("branch_id"),
        verdict=verdict,
        reportability=reportability,
        quality_band=quality_band,
        objective_score=round(objective_score, 3),
        grounding_score=grounding_score,
        freshness_score=0.65 if advisory_issues else 0.8,
        contradiction_score=1.0,
        risk_flags=risk_flags,
        suggested_actions=suggested_actions,
        needs_manual_review=needs_manual_review,
        blocking_issues=blocking_issues,
        advisory_issues=advisory_issues,
        follow_up_queries=_dedupe_texts(follow_up_queries or [objective]),
        notes="; ".join(
            [
                str(item.get("message") or "").strip()
                for item in [*blocking_issues, *advisory_issues]
                if str(item.get("message") or "").strip()
            ]
        ),
    ).to_dict()
    review["section_order"] = int(section.get("section_order", 0) or 0)

    certification: dict[str, Any] | None = None
    if reportability != "insufficient":
        certification = SectionCertificationArtifact(
            id=_new_id("section_certification"),
            section_id=str(draft.get("section_id") or ""),
            certified=reportability in {"high", "medium"},
            reportability=reportability,
            quality_band=quality_band,
            key_claims_grounded_ratio=round(grounding_ratio, 3),
            objective_met=objective_met,
            has_primary_sources=has_primary_sources,
            freshness_warning=(
                "freshness_risk"
                if any(str(item.get("issue_type") or "") == "freshness_risk" for item in advisory_issues)
                else ""
            ),
            risk_flags=risk_flags,
            suggested_actions=suggested_actions,
            needs_manual_review=needs_manual_review,
            limitations=[
                str(item.get("message") or "").strip()
                for item in advisory_issues
                if str(item.get("message") or "").strip()
            ],
            blocking_issue_count=len(blocking_issues),
            advisory_issue_count=len(advisory_issues),
        ).to_dict()
        certification["section_order"] = int(section.get("section_order", 0) or 0)

    return review, certification


def artifact_store_section_draft_by_task(
    store: LightweightArtifactStore,
    task_id: str,
) -> dict[str, Any]:
    task_key = str(task_id or "").strip()
    if not task_key:
        return {}
    for draft in store.section_drafts():
        if str(draft.get("task_id") or "").strip() == task_key:
            return copy.deepcopy(draft)
    return {}


def build_report_sections(store: LightweightArtifactStore) -> list[ReportSectionContext]:
    sections: list[ReportSectionContext] = []
    for item in store.reportable_section_drafts():
        section_id = str(item.get("section_id") or "").strip()
        review = store.section_review(section_id) if section_id else {}
        certification = store.section_certification(section_id) if section_id else {}
        reportability = _resolved_section_reportability(item, review, certification)
        if not _section_admitted_for_report(item, review, certification):
            continue
        summary = str(item.get("summary") or "").strip()
        findings = _dedupe_texts(
            [str(value).strip() for value in item.get("key_findings", []) or [] if str(value).strip()]
        )
        if reportability == "medium":
            findings = findings[:2]
        sections.append(
            ReportSectionContext(
                title=str(item.get("title") or "研究章节"),
                summary=summary or (findings[0] if findings else "暂无充分章节摘要"),
                branch_summaries=[],
                findings=findings,
                citation_urls=list(item.get("source_urls") or []),
                confidence_level=reportability,
                limitation_summary="",
                risk_highlights=[],
                manual_review_items=[],
            )
        )
    return sections

__all__ = [
    "artifact_store_section_draft_by_task",
    "build_report_sections",
    "build_review_issue",
    "build_section_draft",
    "review_section_draft",
]
