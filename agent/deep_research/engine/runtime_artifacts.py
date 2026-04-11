"""Runtime artifact aggregation helpers for Deep Research."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import agent.deep_research.branch_research.budgets as budgets
from agent.deep_research.engine.artifact_store import LightweightArtifactStore
from agent.deep_research.engine.section_logic import (
    _resolved_section_reportability,
    _section_admitted_for_report,
)
from agent.deep_research.engine.text_analysis import _dedupe_texts
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import EvidenceBundle, ResearchPlanArtifact, ResearchTask
from agent.deep_research.store import ResearchTaskQueue


def aggregate_sections(
    queue: ResearchTaskQueue,
    store: LightweightArtifactStore,
    runtime_state: dict[str, Any],
    *,
    outline_sections_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> dict[str, Any]:
    outline = store.outline()
    required_section_ids = [
        str(item).strip()
        for item in outline.get("required_section_ids", []) or []
        if str(item).strip()
    ]
    if not required_section_ids:
        required_section_ids = [
            str(item.get("id") or "").strip()
            for item in outline_sections_fn(outline)
            if str(item.get("id") or "").strip()
        ]
    certifications = {
        str(item.get("section_id") or "").strip(): item
        for item in store.section_certifications()
        if str(item.get("section_id") or "").strip()
    }
    if not required_section_ids and certifications:
        required_section_ids = list(certifications.keys())
    reviews = {
        str(item.get("section_id") or "").strip(): item
        for item in store.section_reviews()
        if str(item.get("section_id") or "").strip()
    }
    drafts = store.section_drafts()
    draft_by_section = {
        str(item.get("section_id") or "").strip(): item
        for item in drafts
        if str(item.get("section_id") or "").strip()
    }
    reportable_section_ids = [
        str(item.get("section_id") or "").strip()
        for item in drafts
        if str(item.get("section_id") or "").strip()
        and _section_admitted_for_report(
            item,
            reviews.get(str(item.get("section_id") or "").strip(), {}),
            certifications.get(str(item.get("section_id") or "").strip(), {}),
        )
    ]
    if not required_section_ids and reviews:
        required_section_ids = list(reviews.keys())
    if not required_section_ids:
        required_section_ids = [
            str(section_id).strip()
            for section_id in dict(runtime_state.get("section_status_map") or {}).keys()
            if str(section_id).strip()
        ]
    if not required_section_ids:
        required_section_ids = [
            str(item.get("section_id") or "").strip()
            for item in store.section_drafts()
            if str(item.get("section_id") or "").strip()
        ]
    status_map = {
        str(section_id): str((runtime_state.get("section_status_map") or {}).get(section_id) or "planned").strip()
        for section_id in required_section_ids
    }
    certified_section_ids = [
        section_id
        for section_id in required_section_ids
        if bool(certifications.get(section_id, {}).get("certified"))
    ]
    supportive_section_ids = [
        section_id
        for section_id in required_section_ids
        if _section_admitted_for_report(
            draft_by_section.get(section_id, {}),
            reviews.get(section_id, {}),
            certifications.get(section_id, {}),
        )
    ]
    high_confidence_section_ids = [
        section_id
        for section_id in required_section_ids
        if _section_admitted_for_report(
            draft_by_section.get(section_id, {}),
            reviews.get(section_id, {}),
            certifications.get(section_id, {}),
        )
        and _resolved_section_reportability(
            draft_by_section.get(section_id, {}),
            reviews.get(section_id, {}),
            certifications.get(section_id, {}),
        )
        == "high"
    ]
    review_needed_section_ids = [
        section_id
        for section_id in required_section_ids
        if bool(reviews.get(section_id, {}).get("needs_manual_review"))
    ]
    blocked_section_ids = [
        section_id
        for section_id in required_section_ids
        if status_map.get(section_id) == "blocked"
    ]
    pending_section_ids = [
        section_id
        for section_id in required_section_ids
        if section_id not in certified_section_ids and section_id not in blocked_section_ids
    ]
    advisory_issue_count = sum(
        len(item.get("advisory_issues") or [])
        for item in reviews.values()
        if isinstance(item, dict)
    )
    blocking_issue_count = sum(
        len(item.get("blocking_issues") or [])
        for item in reviews.values()
        if isinstance(item, dict)
    )
    preferred_ready = bool(required_section_ids) and supportive_section_ids == required_section_ids and not blocked_section_ids
    report_ready = bool(reportable_section_ids)
    return {
        "required_section_count": len(required_section_ids),
        "certified_section_count": len(certified_section_ids),
        "reportable_section_count": len(reportable_section_ids),
        "high_confidence_section_count": len(high_confidence_section_ids),
        "limited_evidence_section_count": sum(
            1
            for section_id in required_section_ids
            if section_id in reportable_section_ids and section_id not in high_confidence_section_ids
        ),
        "review_needed_section_count": len(review_needed_section_ids),
        "pending_section_count": len(pending_section_ids),
        "blocked_section_count": len(blocked_section_ids),
        "required_section_ids": required_section_ids,
        "certified_section_ids": certified_section_ids,
        "reportable_section_ids": reportable_section_ids,
        "missing_section_ids": pending_section_ids,
        "blocked_section_ids": blocked_section_ids,
        "advisory_issue_count": advisory_issue_count,
        "blocking_issue_count": blocking_issue_count,
        "preferred_ready": preferred_ready,
        "report_ready": report_ready,
        "outline_ready": preferred_ready,
        "ready_task_count": queue.ready_count(),
        "source_count": len(store.all_sources()),
    }


def build_plan_artifact(
    scope: dict[str, Any],
    tasks: list[ResearchTask],
    *,
    coverage_targets: list[str] | None = None,
    coverage_target_source: str = "",
) -> dict[str, Any]:
    artifact = ResearchPlanArtifact(
        id=_new_id("plan"),
        scope_id=str(scope.get("id") or "") or None,
        tasks=[
            {
                "task_id": task.id,
                "section_id": task.section_id,
                "title": task.title,
                "objective": task.objective,
                "query": task.query,
                "priority": task.priority,
            }
            for task in tasks
        ],
    )
    payload = artifact.to_dict()
    if coverage_targets:
        payload["coverage_targets"] = _dedupe_texts(coverage_targets)
    if coverage_target_source:
        payload["coverage_target_source"] = coverage_target_source
    return payload


def build_evidence_bundle(
    task: ResearchTask,
    outcome: dict[str, Any],
    created_by: str,
    *,
    results_per_query: int,
) -> dict[str, Any]:
    sources = [
        item
        for item in copy.deepcopy(outcome.get("sources") or [])
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    ]
    if not sources:
        sources = budgets._compact_sources(
            list(outcome.get("search_results") or []),
            limit=max(3, results_per_query),
        )
    documents = [
        item
        for item in copy.deepcopy(outcome.get("documents") or [])
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    ]
    passages = [
        item
        for item in copy.deepcopy(outcome.get("passages") or [])
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    ]
    bundle = EvidenceBundle(
        id=_new_id("bundle"),
        task_id=task.id,
        section_id=task.section_id,
        branch_id=task.branch_id,
        sources=sources,
        documents=documents,
        passages=passages,
        source_count=len(sources),
        created_by=created_by,
    )
    return bundle.to_dict()


def quality_summary(
    queue: ResearchTaskQueue,
    store: LightweightArtifactStore,
    runtime_state: dict[str, Any],
    *,
    outline_sections_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> dict[str, Any]:
    aggregate = aggregate_sections(
        queue,
        store,
        runtime_state,
        outline_sections_fn=outline_sections_fn,
    )
    certified_section_count = int(aggregate.get("certified_section_count") or 0)
    required_section_count = int(aggregate.get("required_section_count") or 0)
    source_count = int(aggregate.get("source_count") or 0)
    coverage_score = (
        round(certified_section_count / max(1, required_section_count), 3)
        if required_section_count
        else 0.0
    )
    missing_section_ids = _dedupe_texts(aggregate.get("missing_section_ids") or [])
    return {
        "section_count": required_section_count,
        "certified_section_count": certified_section_count,
        "reportable_section_count": int(aggregate.get("reportable_section_count") or 0),
        "high_confidence_section_count": int(aggregate.get("high_confidence_section_count") or 0),
        "limited_evidence_section_count": int(aggregate.get("limited_evidence_section_count") or 0),
        "review_needed_section_count": int(aggregate.get("review_needed_section_count") or 0),
        "pending_section_count": int(aggregate.get("pending_section_count") or 0),
        "blocked_section_count": int(aggregate.get("blocked_section_count") or 0),
        "preferred_ready": bool(aggregate.get("preferred_ready")),
        "report_ready": bool(aggregate.get("report_ready")),
        "advisory_issue_count": int(aggregate.get("advisory_issue_count") or 0),
        "blocking_issue_count": int(aggregate.get("blocking_issue_count") or 0),
        "coverage_ready": bool(aggregate.get("preferred_ready", aggregate.get("outline_ready"))),
        "missing_section_ids": missing_section_ids,
        "coverage_summary": {
            "ready": bool(aggregate.get("preferred_ready", aggregate.get("outline_ready"))),
            "score": coverage_score,
            "covered_count": certified_section_count,
            "target_count": required_section_count,
            "target_source": "outline_required_sections",
        },
        "source_count": source_count,
        "query_coverage_score": coverage_score,
        "query_coverage": {
            "score": coverage_score,
            "covered": certified_section_count,
            "total": required_section_count,
        },
        "citation_coverage": round(min(1.0, source_count / max(1, certified_section_count)), 3),
        "uncovered_questions_count": len(missing_section_ids),
        "budget_stop_reason": str(runtime_state.get("budget_stop_reason") or ""),
    }


def research_topology_snapshot(
    *,
    topic: str,
    graph_run_id: str,
    queue: ResearchTaskQueue,
    store: LightweightArtifactStore,
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    certifications_by_section = {
        str(item.get("section_id") or ""): item
        for item in store.section_certifications()
        if str(item.get("section_id") or "")
    }
    return {
        "id": "deep_research",
        "topic": topic,
        "engine": "multi_agent",
        "graph_run_id": graph_run_id,
        "phase": str(runtime_state.get("phase") or ""),
        "active_agent": str(runtime_state.get("active_agent") or ""),
        "children": [
            {
                "id": task.id,
                "section_id": task.section_id,
                "title": task.title or task.objective or task.goal,
                "query": task.query,
                "status": task.status,
                "stage": task.stage,
                "attempts": task.attempts,
                "validation_status": (
                    "certified"
                    if bool(certifications_by_section.get(str(task.section_id or ""), {}).get("certified"))
                    else str(
                        (runtime_state.get("section_status_map") or {}).get(str(task.section_id or "")) or "pending"
                    )
                ),
            }
            for task in queue.all_tasks()
        ],
    }


def initial_next_step(
    task_queue_snapshot: dict[str, Any],
    artifact_store_snapshot: dict[str, Any],
    runtime_state_snapshot: dict[str, Any],
    *,
    outline_sections_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> str:
    existing = str(runtime_state_snapshot.get("next_step") or "").strip().lower()
    if existing == "completed":
        return "finalize"
    if existing == "final_claim_gate":
        # Legacy checkpoints may still point at the removed stage.
        return "finalize"
    if existing:
        return existing
    final_report = artifact_store_snapshot.get("final_report")
    if isinstance(final_report, dict) and final_report.get("report_markdown"):
        return "finalize"
    approved_scope = runtime_state_snapshot.get("approved_scope_draft")
    current_scope = runtime_state_snapshot.get("current_scope_draft")
    intake_status = str(runtime_state_snapshot.get("intake_status") or "pending").strip().lower()
    if not approved_scope:
        if current_scope:
            return "scope_review"
        if intake_status in {"ready_for_scope", "scope_revision_requested"}:
            return "scope"
        return "clarify"
    scope = artifact_store_snapshot.get("scope")
    if not isinstance(scope, dict) or not scope:
        return "research_brief"
    outline = artifact_store_snapshot.get("outline")
    if not isinstance(outline, dict) or not outline:
        return "outline_plan"
    stats = task_queue_snapshot.get("stats", {}) if isinstance(task_queue_snapshot, dict) else {}
    if int(stats.get("total", 0) or 0) == 0:
        return "outline_plan"
    if int(stats.get("ready", 0) or 0) > 0 or int(stats.get("in_progress", 0) or 0) > 0:
        return "dispatch"
    section_drafts = artifact_store_snapshot.get("section_drafts")
    if isinstance(section_drafts, list) and section_drafts:
        certifications = artifact_store_snapshot.get("section_certifications")
        certified_ids = {
            str(item.get("section_id") or "").strip()
            for item in certifications
            if isinstance(certifications, list) and isinstance(item, dict)
        }
        for draft in section_drafts:
            if not isinstance(draft, dict):
                continue
            section_id = str(draft.get("section_id") or "").strip()
            if section_id and section_id not in certified_ids:
                return "reviewer"
    outline_gate_summary = runtime_state_snapshot.get("outline_gate_summary")
    if isinstance(outline_gate_summary, dict) and bool(
        outline_gate_summary.get("report_ready") or outline_gate_summary.get("outline_ready")
    ):
        return "report"
    return "supervisor_decide"


__all__ = [
    "aggregate_sections",
    "build_evidence_bundle",
    "build_plan_artifact",
    "initial_next_step",
    "quality_summary",
    "research_topology_snapshot",
]
