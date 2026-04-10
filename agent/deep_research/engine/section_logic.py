"""Section-level naming, admission, and claim-quality helpers."""

from __future__ import annotations

from typing import Any

from agent.deep_research.schema import ResearchTask


def _branch_title(task: ResearchTask) -> str:
    return task.title or task.objective or task.goal or task.query


def _section_title(payload: dict[str, Any]) -> str:
    return str(
        payload.get("title")
        or payload.get("objective")
        or payload.get("core_question")
        or payload.get("query")
        or "研究章节"
    ).strip()


def _section_draft_text(payload: dict[str, Any]) -> str:
    summary = str(payload.get("summary") or "").strip()
    findings = [str(item).strip() for item in payload.get("key_findings", []) or [] if str(item).strip()]
    limitations = [str(item).strip() for item in payload.get("limitations", []) or [] if str(item).strip()]
    return "\n".join([summary, *findings, *limitations]).strip()


def _resolved_section_reportability(
    draft: dict[str, Any],
    review: dict[str, Any],
    certification: dict[str, Any],
) -> str:
    return str(
        certification.get("reportability")
        or review.get("reportability")
        or ("high" if certification.get("certified") or draft.get("certified") else "low")
    ).strip().lower()


def _section_admitted_for_report(
    draft: dict[str, Any],
    review: dict[str, Any],
    certification: dict[str, Any],
) -> bool:
    reportability = _resolved_section_reportability(draft, review, certification)
    contradiction_summary = dict(draft.get("contradiction_summary") or {})
    if reportability not in {"high", "medium"}:
        return False
    if bool(contradiction_summary.get("has_material_conflict")):
        return False
    return True


def _issue_types(*issue_groups: list[dict[str, Any]]) -> list[str]:
    issue_types: list[str] = []
    seen: set[str] = set()
    for group in issue_groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            issue_type = str(item.get("issue_type") or "").strip()
            key = issue_type.lower()
            if not issue_type or key in seen:
                continue
            seen.add(key)
            issue_types.append(issue_type)
    return issue_types


def _primary_claim_units(payload: dict[str, Any]) -> list[dict[str, Any]]:
    claim_units = [
        item
        for item in payload.get("claim_units", []) or []
        if isinstance(item, dict)
    ]
    primary = [
        item
        for item in claim_units
        if str(item.get("importance") or "secondary").strip().lower() == "primary"
    ]
    return primary or claim_units[:1]


def _claim_grounding_ratio(payload: dict[str, Any]) -> float:
    primary = _primary_claim_units(payload)
    if not primary:
        return 0.0
    grounded = 0
    for item in primary:
        if bool(item.get("grounded")) or list(item.get("evidence_passage_ids") or []):
            grounded += 1
    return grounded / max(1, len(primary))


__all__ = [
    "_branch_title",
    "_claim_grounding_ratio",
    "_issue_types",
    "_resolved_section_reportability",
    "_section_admitted_for_report",
    "_section_draft_text",
    "_section_title",
]
