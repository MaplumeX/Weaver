"""Section, branch, and validation adapters for public Deep Research artifacts."""

from __future__ import annotations

from typing import Any

from agent.foundation.source_urls import canonicalize_source_url


def _normalize_public_branch_results(items: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "branch_id": item.get("branch_id"),
                "title": str(item.get("title") or "").strip(),
                "objective": str(item.get("objective") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "key_findings": list(item.get("key_findings") or []),
                "open_questions": list(item.get("open_questions") or []),
                "confidence_note": str(item.get("confidence_note") or "").strip(),
                "source_urls": [
                    canonicalize_source_url(url)
                    for url in item.get("source_urls", []) or []
                    if canonicalize_source_url(url)
                ],
                "validation_status": str(item.get("validation_status") or "pending").strip(),
            }
        )
    return results


def _normalize_public_section_drafts(items: Any) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        drafts.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "section_id": item.get("section_id"),
                "branch_id": item.get("branch_id"),
                "title": str(item.get("title") or "").strip(),
                "objective": str(item.get("objective") or "").strip(),
                "core_question": str(item.get("core_question") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "key_findings": list(item.get("key_findings") or []),
                "open_questions": list(item.get("open_questions") or []),
                "confidence_note": str(item.get("confidence_note") or "").strip(),
                "source_urls": [
                    canonicalize_source_url(url)
                    for url in item.get("source_urls", []) or []
                    if canonicalize_source_url(url)
                ],
                "claim_units": list(item.get("claim_units") or []),
                "limitations": list(item.get("limitations") or []),
                "coverage_summary": dict(item.get("coverage_summary") or {}),
                "quality_summary": dict(item.get("quality_summary") or {}),
                "contradiction_summary": dict(item.get("contradiction_summary") or {}),
                "grounding_summary": dict(item.get("grounding_summary") or {}),
                "review_status": str(item.get("review_status") or "pending").strip(),
                "certified": bool(item.get("certified", False)),
            }
        )
    return drafts


def _normalize_public_section_reviews(items: Any) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        reviews.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "section_id": item.get("section_id"),
                "branch_id": item.get("branch_id"),
                "verdict": str(item.get("verdict") or "").strip(),
                "reportability": str(item.get("reportability") or "insufficient").strip(),
                "quality_band": str(item.get("quality_band") or "").strip(),
                "objective_score": item.get("objective_score", 0.0),
                "grounding_score": item.get("grounding_score", 0.0),
                "freshness_score": item.get("freshness_score", 0.0),
                "contradiction_score": item.get("contradiction_score", 0.0),
                "risk_flags": [str(flag).strip() for flag in item.get("risk_flags", []) or [] if str(flag).strip()],
                "suggested_actions": [
                    str(action).strip()
                    for action in item.get("suggested_actions", []) or []
                    if str(action).strip()
                ],
                "needs_manual_review": bool(item.get("needs_manual_review", False)),
                "blocking_issues": list(item.get("blocking_issues") or []),
                "advisory_issues": list(item.get("advisory_issues") or []),
                "follow_up_queries": list(item.get("follow_up_queries") or []),
                "notes": str(item.get("notes") or "").strip(),
            }
        )
    return reviews


def _normalize_public_section_certifications(items: Any) -> list[dict[str, Any]]:
    certifications: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        certifications.append(
            {
                "id": item.get("id"),
                "section_id": item.get("section_id"),
                "certified": bool(item.get("certified", False)),
                "reportability": str(item.get("reportability") or "").strip(),
                "quality_band": str(item.get("quality_band") or "").strip(),
                "key_claims_grounded_ratio": item.get("key_claims_grounded_ratio", 0.0),
                "objective_met": bool(item.get("objective_met", False)),
                "has_primary_sources": bool(item.get("has_primary_sources", False)),
                "freshness_warning": str(item.get("freshness_warning") or "").strip(),
                "risk_flags": [str(flag).strip() for flag in item.get("risk_flags", []) or [] if str(flag).strip()],
                "suggested_actions": [
                    str(action).strip()
                    for action in item.get("suggested_actions", []) or []
                    if str(action).strip()
                ],
                "needs_manual_review": bool(item.get("needs_manual_review", False)),
                "limitations": list(item.get("limitations") or []),
                "blocking_issue_count": int(item.get("blocking_issue_count", 0) or 0),
                "advisory_issue_count": int(item.get("advisory_issue_count", 0) or 0),
            }
        )
    return certifications


def _normalize_validation_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    summary: dict[str, Any] = {}
    integer_keys = (
        "passed_branch_count",
        "retry_branch_count",
        "failed_branch_count",
        "advisory_gap_count",
        "reportable_section_count",
        "high_confidence_section_count",
        "limited_evidence_section_count",
        "review_needed_section_count",
        "coverage_target_count",
        "covered_question_count",
        "required_section_count",
        "certified_section_count",
        "pending_section_count",
        "blocked_section_count",
        "advisory_issue_count",
        "blocking_issue_count",
    )
    for key in integer_keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            summary[key] = int(value)
        except (TypeError, ValueError):
            continue

    for key in ("coverage_score",):
        value = payload.get(key)
        if value is None:
            continue
        try:
            summary[key] = float(value)
        except (TypeError, ValueError):
            continue

    if "coverage_ready" in payload:
        summary["coverage_ready"] = bool(payload.get("coverage_ready"))
    elif "outline_ready" in payload:
        summary["coverage_ready"] = bool(payload.get("outline_ready"))
    if "report_ready" in payload:
        summary["report_ready"] = bool(payload.get("report_ready"))
    if "preferred_ready" in payload:
        summary["preferred_ready"] = bool(payload.get("preferred_ready"))
    if "certified_section_count" in summary and "passed_branch_count" not in summary:
        summary["passed_branch_count"] = int(summary.get("certified_section_count") or 0)
    if "pending_section_count" in summary and "retry_branch_count" not in summary:
        summary["retry_branch_count"] = int(summary.get("pending_section_count") or 0)
    if "blocked_section_count" in summary and "failed_branch_count" not in summary:
        summary["failed_branch_count"] = int(summary.get("blocked_section_count") or 0)

    for key in ("status_reason", "notes"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            summary[key] = value.strip()

    for key in ("uncovered_questions", "recommended_gap_queries"):
        value = payload.get(key)
        if isinstance(value, list):
            summary[key] = [str(item).strip() for item in value if str(item).strip()]

    raw_coverage = payload.get("coverage_by_question")
    if isinstance(raw_coverage, list):
        summary["coverage_by_question"] = [
            {
                "question": str(item.get("question") or "").strip(),
                "status": str(item.get("status") or "").strip(),
                "task_ids": [str(task_id).strip() for task_id in item.get("task_ids", []) or [] if str(task_id).strip()],
                "suggested_queries": [
                    str(query).strip()
                    for query in item.get("suggested_queries", []) or []
                    if str(query).strip()
                ],
            }
            for item in raw_coverage
            if isinstance(item, dict) and str(item.get("question") or "").strip()
        ]

    raw_summaries = payload.get("summaries")
    if isinstance(raw_summaries, list):
        summary["summaries"] = [
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "branch_id": item.get("branch_id"),
                "status": str(item.get("status") or "pending").strip(),
                "score": item.get("score", 0.0),
                "missing_aspects": list(item.get("missing_aspects") or []),
                "retry_queries": list(item.get("retry_queries") or []),
                "notes": str(item.get("notes") or "").strip(),
                "coverage_hits": [str(hit).strip() for hit in item.get("coverage_hits", []) or [] if str(hit).strip()],
                "coverage_misses": [str(hit).strip() for hit in item.get("coverage_misses", []) or [] if str(hit).strip()],
                "coverage_confidence": item.get("coverage_confidence", 0.0),
                "suggested_follow_up_queries": [
                    str(query).strip()
                    for query in item.get("suggested_follow_up_queries", []) or []
                    if str(query).strip()
                ],
            }
            for item in raw_summaries
            if isinstance(item, dict)
        ]
    return summary


def _normalize_lightweight_branch_results(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    items = artifact_store.get("section_drafts", []) if isinstance(artifact_store, dict) else []
    if not isinstance(items, list):
        items = []
    results = _normalize_public_section_drafts(items)
    return [
        {
            "id": item.get("id"),
            "task_id": item.get("task_id"),
            "branch_id": item.get("branch_id"),
            "title": item.get("title"),
            "objective": item.get("objective"),
            "summary": item.get("summary"),
            "key_findings": item.get("key_findings", []),
            "open_questions": item.get("open_questions", []),
            "confidence_note": item.get("confidence_note", ""),
            "source_urls": item.get("source_urls", []),
            "validation_status": "passed" if item.get("certified") else item.get("review_status", "pending"),
        }
        for item in results
    ]


def _normalize_lightweight_validation(artifact_store: dict[str, Any]) -> dict[str, Any]:
    review_items = artifact_store.get("section_reviews", []) if isinstance(artifact_store, dict) else []
    certification_items = artifact_store.get("section_certifications", []) if isinstance(artifact_store, dict) else []
    if not isinstance(review_items, list):
        review_items = []
    reviews = _normalize_public_section_reviews(review_items)
    certifications = _normalize_public_section_certifications(certification_items)
    strong_ids = {
        str(item.get("section_id") or "").strip()
        for item in reviews
        if str(item.get("reportability") or "").strip() == "high"
    }
    supportive_ids = {
        str(item.get("section_id") or "").strip()
        for item in reviews
        if str(item.get("reportability") or "").strip() in {"high", "medium"}
    }
    reportable_ids = {
        str(item.get("section_id") or "").strip()
        for item in reviews
        if str(item.get("reportability") or "").strip() in {"high", "medium", "low"}
    }
    certified_ids = {
        str(item.get("section_id") or "").strip()
        for item in certifications
        if bool(item.get("certified"))
    }
    required_ids = {
        str(item.get("section_id") or "").strip()
        for item in reviews
        if str(item.get("section_id") or "").strip()
    } | certified_ids
    return {
        "passed_branch_count": len(strong_ids or certified_ids),
        "retry_branch_count": sum(1 for item in reviews if str(item.get("verdict") or "") == "request_research"),
        "failed_branch_count": sum(1 for item in reviews if str(item.get("verdict") or "") == "block_section"),
        "reportable_section_count": len(reportable_ids),
        "high_confidence_section_count": len(strong_ids),
        "limited_evidence_section_count": sum(
            1 for item in reviews if str(item.get("reportability") or "").strip() in {"medium", "low"}
        ),
        "review_needed_section_count": sum(1 for item in reviews if bool(item.get("needs_manual_review"))),
        "preferred_ready": bool(required_ids) and supportive_ids.issuperset(required_ids),
        "report_ready": bool(reportable_ids),
        "coverage_ready": bool(required_ids) and supportive_ids.issuperset(required_ids),
        "summaries": [
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "section_id": item.get("section_id"),
                "branch_id": item.get("branch_id"),
                "status": str(item.get("verdict") or "pending"),
                "score": item.get("grounding_score", 0.0),
                "reportability": item.get("reportability", "insufficient"),
                "quality_band": item.get("quality_band", ""),
                "risk_flags": list(item.get("risk_flags") or []),
                "needs_manual_review": bool(item.get("needs_manual_review", False)),
                "notes": item.get("notes", ""),
                "retry_queries": list(item.get("follow_up_queries") or []),
            }
            for item in reviews
        ],
    }


__all__ = [
    "_normalize_lightweight_branch_results",
    "_normalize_lightweight_validation",
    "_normalize_public_branch_results",
    "_normalize_public_section_certifications",
    "_normalize_public_section_drafts",
    "_normalize_public_section_reviews",
    "_normalize_validation_summary",
]
