"""Payload assembly helpers for public Deep Research artifacts."""

from __future__ import annotations

from typing import Any

from agent.deep_research.artifacts.public_sections import (
    _normalize_lightweight_branch_results,
    _normalize_lightweight_validation,
    _normalize_public_branch_results,
    _normalize_public_section_certifications,
    _normalize_public_section_drafts,
    _normalize_public_section_reviews,
    _normalize_validation_summary,
)
from agent.deep_research.artifacts.public_sources import (
    _build_queries,
    _normalize_lightweight_fetched_pages,
    _normalize_lightweight_passages,
    _normalize_lightweight_sources,
    _normalize_public_fetched_pages,
    _normalize_public_passages,
    _normalize_public_sources,
    _sorted_tasks,
)

_PUBLIC_SIGNAL_KEYS = (
    "queries",
    "scope",
    "outline",
    "plan",
    "tasks",
    "research_topology",
    "sources",
    "section_drafts",
    "section_reviews",
    "section_certifications",
    "branch_query_rounds",
    "branch_coverages",
    "branch_qualities",
    "branch_contradictions",
    "branch_groundings",
    "branch_decisions",
    "outline_gate_summary",
    "branch_results",
    "validation_summary",
    "quality_summary",
    "final_report",
    "executive_summary",
    "runtime_state",
    "fetched_pages",
    "passages",
    "query_coverage",
    "freshness_summary",
    "coverage_summary",
    "uncovered_questions",
)


def _build_query_coverage(
    quality_summary: dict[str, Any],
    explicit_query_coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(explicit_query_coverage, dict) and explicit_query_coverage:
        return dict(explicit_query_coverage)
    score = quality_summary.get("query_coverage_score")
    if isinstance(score, (int, float)):
        return {"score": float(score)}
    nested = quality_summary.get("query_coverage")
    if isinstance(nested, dict):
        return dict(nested)
    return {}


def _normalize_control_plane(
    runtime_state: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    control_plane = dict(payload or {})
    latest_handoff = control_plane.get("latest_handoff")
    if not isinstance(latest_handoff, dict):
        runtime_handoff = runtime_state.get("handoff_envelope")
        latest_handoff = dict(runtime_handoff) if isinstance(runtime_handoff, dict) else {}

    handoff_history = control_plane.get("handoff_history")
    if not isinstance(handoff_history, list):
        raw_history = runtime_state.get("handoff_history")
        handoff_history = [item for item in raw_history if isinstance(item, dict)] if isinstance(raw_history, list) else []

    return {
        "active_agent": str(control_plane.get("active_agent") or runtime_state.get("active_agent") or ""),
        "latest_handoff": dict(latest_handoff),
        "handoff_history": list(handoff_history),
    }


def _build_public_payload(
    *,
    mode: str,
    engine: str,
    queries: list[str],
    scope: dict[str, Any],
    outline: dict[str, Any],
    plan: dict[str, Any],
    tasks: list[dict[str, Any]],
    research_topology: dict[str, Any],
    sources: list[dict[str, Any]],
    section_drafts: list[dict[str, Any]],
    section_reviews: list[dict[str, Any]],
    section_certifications: list[dict[str, Any]],
    branch_query_rounds: list[dict[str, Any]] | None = None,
    branch_coverages: list[dict[str, Any]] | None = None,
    branch_qualities: list[dict[str, Any]] | None = None,
    branch_contradictions: list[dict[str, Any]] | None = None,
    branch_groundings: list[dict[str, Any]] | None = None,
    branch_decisions: list[dict[str, Any]] | None = None,
    outline_gate_summary: dict[str, Any] | None = None,
    branch_results: list[dict[str, Any]] | None = None,
    validation_summary: dict[str, Any] | None = None,
    quality_summary: dict[str, Any] | None = None,
    final_report: str = "",
    executive_summary: str = "",
    runtime_state: dict[str, Any] | None = None,
    fetched_pages: list[dict[str, Any]] | None = None,
    passages: list[dict[str, Any]] | None = None,
    query_coverage: dict[str, Any] | None = None,
    freshness_summary: dict[str, Any] | None = None,
    control_plane: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation_summary = dict(validation_summary or {})
    quality_summary = dict(quality_summary or {})
    runtime_state = dict(runtime_state or {})
    outline_gate_summary = dict(outline_gate_summary or {})
    branch_results = list(branch_results or [])
    fetched_pages = list(fetched_pages or [])
    passages = list(passages or [])
    resolved_query_coverage = _build_query_coverage(quality_summary, query_coverage)
    resolved_freshness = (
        dict(freshness_summary)
        if isinstance(freshness_summary, dict)
        else dict(quality_summary.get("freshness_summary") or {})
    )
    coverage_summary = dict(quality_summary.get("coverage_summary") or {})
    if not coverage_summary:
        coverage_summary = {
            "ready": bool(validation_summary.get("coverage_ready", quality_summary.get("coverage_ready", False))),
            "score": validation_summary.get("coverage_score", resolved_query_coverage.get("score")),
            "covered_count": validation_summary.get("covered_question_count", resolved_query_coverage.get("covered")),
            "target_count": validation_summary.get("coverage_target_count", resolved_query_coverage.get("total")),
        }
    uncovered_questions = [
        str(item).strip()
        for item in (
            validation_summary.get("uncovered_questions")
            or quality_summary.get("missing_section_ids")
            or quality_summary.get("uncovered_questions")
            or []
        )
        if str(item).strip()
    ]
    return {
        "mode": mode,
        "engine": engine,
        "query": queries[0] if queries else "",
        "queries": queries,
        "scope": dict(scope),
        "outline": dict(outline),
        "plan": dict(plan),
        "tasks": list(tasks),
        "research_topology": dict(research_topology),
        "sources": list(sources),
        "section_drafts": list(section_drafts),
        "section_reviews": list(section_reviews),
        "section_certifications": list(section_certifications),
        "branch_query_rounds": list(branch_query_rounds or []),
        "branch_coverages": list(branch_coverages or []),
        "branch_qualities": list(branch_qualities or []),
        "branch_contradictions": list(branch_contradictions or []),
        "branch_groundings": list(branch_groundings or []),
        "branch_decisions": list(branch_decisions or []),
        "outline_gate_summary": dict(outline_gate_summary),
        "branch_results": list(branch_results),
        "validation_summary": dict(validation_summary),
        "quality_summary": dict(quality_summary),
        "final_report": final_report,
        "executive_summary": executive_summary,
        "runtime_state": dict(runtime_state),
        "terminal_status": str(runtime_state.get("terminal_status") or ""),
        "control_plane": _normalize_control_plane(runtime_state, control_plane),
        "fetched_pages": list(fetched_pages),
        "passages": list(passages),
        "query_coverage": resolved_query_coverage,
        "freshness_summary": resolved_freshness,
        "coverage_summary": coverage_summary,
        "uncovered_questions": uncovered_questions,
    }


def _build_lightweight_public_artifacts(
    *,
    queue_snapshot: dict[str, Any],
    store_snapshot: dict[str, Any],
    research_topology: dict[str, Any] | None,
    quality_summary: dict[str, Any] | None,
    runtime_state: dict[str, Any] | None,
    mode: str,
    engine: str,
) -> dict[str, Any]:
    queries = _build_queries(queue_snapshot)
    validation_summary = _normalize_lightweight_validation(store_snapshot)
    merged_quality = dict(quality_summary or {})
    runtime_snapshot = runtime_state if isinstance(runtime_state, dict) else {}
    runtime_validation = _normalize_validation_summary(
        runtime_snapshot.get("outline_gate_summary") or runtime_snapshot.get("last_review_summary")
    )
    if runtime_validation:
        validation_summary = {**validation_summary, **runtime_validation}
    if "query_coverage_score" not in merged_quality and queries:
        if validation_summary.get("coverage_score") is not None:
            merged_quality["query_coverage_score"] = float(validation_summary.get("coverage_score") or 0.0)
        else:
            passed = int(validation_summary.get("passed_branch_count") or 0)
            merged_quality["query_coverage_score"] = round(passed / max(1, len(queries)), 3)

    final_report = store_snapshot.get("final_report")
    final_report_payload = final_report if isinstance(final_report, dict) else {}
    return _build_public_payload(
        mode=mode,
        engine=engine,
        queries=queries,
        scope=dict(store_snapshot.get("scope")) if isinstance(store_snapshot.get("scope"), dict) else {},
        outline=dict(store_snapshot.get("outline")) if isinstance(store_snapshot.get("outline"), dict) else {},
        plan=dict(store_snapshot.get("plan")) if isinstance(store_snapshot.get("plan"), dict) else {},
        tasks=_sorted_tasks(queue_snapshot),
        research_topology=research_topology if isinstance(research_topology, dict) else {},
        sources=_normalize_lightweight_sources(store_snapshot),
        section_drafts=_normalize_public_section_drafts(store_snapshot.get("section_drafts")),
        section_reviews=_normalize_public_section_reviews(store_snapshot.get("section_reviews")),
        section_certifications=_normalize_public_section_certifications(store_snapshot.get("section_certifications")),
        branch_query_rounds=list(store_snapshot.get("branch_query_rounds") or []),
        branch_coverages=list(store_snapshot.get("branch_coverages") or []),
        branch_qualities=list(store_snapshot.get("branch_qualities") or []),
        branch_contradictions=list(store_snapshot.get("branch_contradictions") or []),
        branch_groundings=list(store_snapshot.get("branch_groundings") or []),
        branch_decisions=list(store_snapshot.get("branch_decisions") or []),
        outline_gate_summary=(
            dict(runtime_snapshot.get("outline_gate_summary"))
            if isinstance(runtime_snapshot.get("outline_gate_summary"), dict)
            else {}
        ),
        branch_results=_normalize_lightweight_branch_results(store_snapshot),
        validation_summary=validation_summary,
        quality_summary=merged_quality,
        final_report=str(final_report_payload.get("report_markdown") or ""),
        executive_summary=str(final_report_payload.get("executive_summary") or ""),
        runtime_state=runtime_snapshot,
        fetched_pages=_normalize_lightweight_fetched_pages(store_snapshot),
        passages=_normalize_lightweight_passages(store_snapshot),
    )


def _filter_public_artifacts(
    artifacts: dict[str, Any],
    *,
    default_mode: str,
    default_engine: str,
) -> dict[str, Any]:
    quality_summary = dict(artifacts.get("quality_summary") or {}) if isinstance(artifacts.get("quality_summary"), dict) else {}
    runtime_state = dict(artifacts.get("runtime_state") or {}) if isinstance(artifacts.get("runtime_state"), dict) else {}
    from agent.deep_research.artifacts.public_sources import _coerce_queries

    queries = _coerce_queries(artifacts.get("queries"))
    if not queries:
        queries = _coerce_queries(artifacts.get("query"))

    payload = _build_public_payload(
        mode=str(artifacts.get("mode") or default_mode or "multi_agent"),
        engine=str(artifacts.get("engine") or artifacts.get("mode") or default_engine or default_mode or "multi_agent"),
        queries=queries,
        scope=dict(artifacts.get("scope")) if isinstance(artifacts.get("scope"), dict) else {},
        outline=dict(artifacts.get("outline")) if isinstance(artifacts.get("outline"), dict) else {},
        plan=dict(artifacts.get("plan")) if isinstance(artifacts.get("plan"), dict) else {},
        tasks=_sorted_tasks({"tasks": artifacts.get("tasks")}) if isinstance(artifacts.get("tasks"), list) else [],
        research_topology=dict(artifacts.get("research_topology")) if isinstance(artifacts.get("research_topology"), dict) else {},
        sources=_normalize_public_sources(artifacts.get("sources")),
        section_drafts=_normalize_public_section_drafts(
            artifacts.get("section_drafts") if isinstance(artifacts.get("section_drafts"), list) else []
        ),
        section_reviews=_normalize_public_section_reviews(
            artifacts.get("section_reviews") if isinstance(artifacts.get("section_reviews"), list) else []
        ),
        section_certifications=_normalize_public_section_certifications(
            artifacts.get("section_certifications") if isinstance(artifacts.get("section_certifications"), list) else []
        ),
        branch_query_rounds=list(artifacts.get("branch_query_rounds") or []),
        branch_coverages=list(artifacts.get("branch_coverages") or []),
        branch_qualities=list(artifacts.get("branch_qualities") or []),
        branch_contradictions=list(artifacts.get("branch_contradictions") or []),
        branch_groundings=list(artifacts.get("branch_groundings") or []),
        branch_decisions=list(artifacts.get("branch_decisions") or []),
        outline_gate_summary=dict(artifacts.get("outline_gate_summary")) if isinstance(artifacts.get("outline_gate_summary"), dict) else {},
        branch_results=_normalize_public_branch_results(
            artifacts.get("branch_results") if isinstance(artifacts.get("branch_results"), list) else artifacts.get("section_drafts")
        ),
        validation_summary=_normalize_validation_summary(artifacts.get("validation_summary")),
        quality_summary=quality_summary,
        final_report=str(artifacts.get("final_report") or ""),
        executive_summary=str(artifacts.get("executive_summary") or ""),
        runtime_state=runtime_state,
        fetched_pages=_normalize_public_fetched_pages(artifacts.get("fetched_pages")),
        passages=_normalize_public_passages(artifacts.get("passages")),
        query_coverage=dict(artifacts.get("query_coverage")) if isinstance(artifacts.get("query_coverage"), dict) else None,
        freshness_summary=(
            dict(artifacts.get("freshness_summary"))
            if isinstance(artifacts.get("freshness_summary"), dict)
            else None
        ),
        control_plane=dict(artifacts.get("control_plane")) if isinstance(artifacts.get("control_plane"), dict) else None,
    )
    if any(payload.get(key) for key in _PUBLIC_SIGNAL_KEYS):
        return payload
    return {}


__all__ = [
    "_build_lightweight_public_artifacts",
    "_filter_public_artifacts",
]
