"""Review-cycle helpers for the Deep Research engine."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from agent.deep_research.engine.artifact_store import LightweightArtifactStore
from agent.deep_research.engine.text_analysis import _dedupe_texts
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import ResearchTask
from agent.deep_research.store import ResearchTaskQueue

BuildRetryTaskFn = Callable[..., ResearchTask]
BuildRevisionTaskFn = Callable[..., ResearchTask]
EmitArtifactUpdateFn = Callable[..., None]
EmitDecisionFn = Callable[..., None]
EmitTaskUpdateFn = Callable[..., None]
FallbackDecisionFn = Callable[..., dict[str, Any]]
ReviewSectionDraftFn = Callable[..., tuple[dict[str, Any], dict[str, Any] | None]]


def review_section_drafts(
    *,
    task_queue: ResearchTaskQueue,
    artifact_store: LightweightArtifactStore,
    runtime_state: dict[str, Any],
    section_map: dict[str, dict[str, Any]],
    task_retry_limit: int,
    current_iteration: int,
    review_section_draft_fn: ReviewSectionDraftFn,
    build_revision_task_fn: BuildRevisionTaskFn,
    build_research_retry_task_fn: BuildRetryTaskFn,
    emit_task_update: EmitTaskUpdateFn,
    emit_artifact_update: EmitArtifactUpdateFn,
) -> None:
    active_task_keys = {
        (str(task.section_id or "").strip(), str(task.task_kind or "").strip())
        for task in task_queue.all_tasks()
        if task.status in {"ready", "in_progress"}
    }
    pending_replans: list[dict[str, Any]] = []
    for draft in artifact_store.section_drafts():
        section_id = str(draft.get("section_id") or "").strip()
        if not section_id:
            continue
        certification = artifact_store.section_certification(section_id)
        if bool(certification.get("certified")):
            continue
        review = artifact_store.section_review(section_id)
        if review and str(review.get("task_id") or "") == str(draft.get("task_id") or "") and str(draft.get("review_status") or "").strip() != "pending":
            continue
        section = section_map.get(section_id, {})
        bundle = artifact_store.evidence_bundle(str(draft.get("task_id") or ""))
        revision_count = int((runtime_state.get("section_revision_counts") or {}).get(section_id, 0) or 0)
        research_retry_count = int((runtime_state.get("section_research_retry_counts") or {}).get(section_id, 0) or 0)
        review, certification = review_section_draft_fn(
            section=section,
            draft=draft,
            bundle=bundle,
            revision_count=revision_count,
        )
        draft["review_artifact_id"] = review.get("id")
        draft["review_status"] = review.get("verdict")
        artifact_store.set_section_review(review)
        emit_artifact_update(
            artifact_id=str(review.get("id") or _new_id("section_review")),
            artifact_type="section_review",
            summary=str(review.get("notes") or review.get("verdict") or ""),
            task_id=str(draft.get("task_id") or ""),
            section_id=section_id,
            branch_id=draft.get("branch_id"),
            iteration=max(1, current_iteration or 1),
            extra={
                "review_verdict": review.get("verdict"),
                "blocking_issue_count": len(review.get("blocking_issues") or []),
                "advisory_issue_count": len(review.get("advisory_issues") or []),
            },
        )
        verdict = str(review.get("verdict") or "").strip()
        if certification:
            draft["certification_artifact_id"] = certification.get("id")
            draft["limitations"] = _dedupe_texts(
                [*list(draft.get("limitations") or []), *list(certification.get("limitations") or [])]
            )
            artifact_store.set_section_certification(certification)
            emit_artifact_update(
                artifact_id=str(certification.get("id") or _new_id("section_certification")),
                artifact_type="section_certification",
                summary="section certified",
                task_id=str(draft.get("task_id") or ""),
                section_id=section_id,
                branch_id=draft.get("branch_id"),
                iteration=max(1, current_iteration or 1),
                extra={
                    "certified": bool(certification.get("certified")),
                    "reportability": certification.get("reportability"),
                    "quality_band": certification.get("quality_band"),
                    "limitations": list(certification.get("limitations") or []),
                },
            )
        if verdict == "accept_section" and certification:
            draft["certified"] = bool(certification.get("certified"))
            _set_section_status(
                runtime_state,
                section_id,
                "certified" if bool(certification.get("certified")) else "reviewed_with_limitations",
            )
        elif verdict == "revise_section":
            draft["certified"] = False
            _set_section_status(runtime_state, section_id, "revising")
            if (section_id, "section_revision") not in active_task_keys:
                pending_replans.append(
                    _build_pending_replan(
                        section=section,
                        draft=draft,
                        review=review,
                        preferred_action=verdict,
                    )
                )
        elif verdict == "request_research":
            draft["certified"] = False
            if research_retry_count < task_retry_limit and not runtime_state.get("budget_stop_reason"):
                _set_section_status(runtime_state, section_id, "research_retry")
                if (section_id, "section_research") not in active_task_keys:
                    pending_replans.append(
                        _build_pending_replan(
                            section=section,
                            draft=draft,
                            review=review,
                            preferred_action=verdict,
                        )
                    )
            else:
                _set_section_status(runtime_state, section_id, "blocked")
        elif verdict == "block_section":
            draft["certified"] = False
            _set_section_status(runtime_state, section_id, "blocked")
        artifact_store.set_section_draft(draft)
    runtime_state["pending_replans"] = pending_replans


def decide_supervisor_next_step(
    *,
    task_queue: ResearchTaskQueue,
    outline: dict[str, Any],
    runtime_state: dict[str, Any],
    aggregate: dict[str, Any],
    reportable_sections: list[Any],
    budget_stop_reason: str,
    current_iteration: int,
    max_epochs: int,
    supervisor: Any,
    fallback_section_decision_fn: FallbackDecisionFn,
    emit_decision: EmitDecisionFn,
) -> tuple[str, dict[str, Any]]:
    previous_budget_stop_reason = str(runtime_state.get("budget_stop_reason") or "")
    pending_replans = [
        item
        for item in list(runtime_state.get("pending_replans") or [])
        if isinstance(item, dict) and str(item.get("section_id") or "").strip()
    ]
    if pending_replans and current_iteration >= max_epochs and not budget_stop_reason:
        budget_stop_reason = "max_epochs_exhausted"
    runtime_state["budget_stop_reason"] = budget_stop_reason
    if budget_stop_reason and budget_stop_reason != previous_budget_stop_reason:
        emit_decision("budget_stop", budget_stop_reason, iteration=max(1, current_iteration or 1))
    if not pending_replans and task_queue.ready_count() > 0 and current_iteration < max_epochs and not budget_stop_reason:
        return "dispatch", {}
    if hasattr(supervisor, "decide_section_action"):
        decision = supervisor.decide_section_action(
            outline=outline,
            section_status_map=dict(runtime_state.get("section_status_map") or {}),
            budget_stop_reason=budget_stop_reason,
            aggregate_summary=aggregate,
            reportable_section_count=len(reportable_sections),
            pending_replans=pending_replans,
        )
        raw_action = getattr(decision, "action", "")
        decision_action = str(getattr(raw_action, "value", raw_action) or "").strip().lower()
        decision_reason = str(getattr(decision, "reasoning", "") or "").strip()
        task_specs = copy.deepcopy(getattr(decision, "task_specs", []) or [])
    else:
        decision = fallback_section_decision_fn(
            outline=outline,
            section_status_map=dict(runtime_state.get("section_status_map") or {}),
            budget_stop_reason=budget_stop_reason,
            aggregate_summary=aggregate,
            reportable_section_count=len(reportable_sections),
        )
        decision_action = str(decision.get("action") or "").strip().lower()
        decision_reason = str(decision.get("reasoning") or "").strip()
        task_specs = copy.deepcopy(decision.get("task_specs") or [])
    if decision_action == "replan" and task_specs and not budget_stop_reason:
        _clear_terminal_state(runtime_state)
        emit_decision(
            "supervisor_replan",
            decision_reason or "planning another research pass",
            iteration=max(1, current_iteration or 1),
            extra={
                **aggregate,
                "replan_count": len(pending_replans),
                "task_count": len(task_specs),
            },
        )
        return "dispatch", {
            "action": decision_action,
            "reasoning": decision_reason,
            "task_specs": task_specs,
        }
    if decision_action == "report" and bool(aggregate.get("outline_ready")):
        _clear_terminal_state(runtime_state)
        emit_decision("report", decision_reason, iteration=max(1, current_iteration or 1), extra=aggregate)
        return "outline_gate", {}
    if decision_action == "report" and bool(aggregate.get("report_ready")):
        _clear_terminal_state(runtime_state)
        emit_decision(
            "report_partial",
            decision_reason or "supported sections are available for reporting",
            iteration=max(1, current_iteration or 1),
            extra=aggregate,
        )
        return "outline_gate", {}
    if reportable_sections:
        _clear_terminal_state(runtime_state)
        emit_decision(
            "report_partial",
            decision_reason or budget_stop_reason or "using admitted section drafts only",
            iteration=max(1, current_iteration or 1),
            extra={
                **aggregate,
                "reportable_section_count": len(reportable_sections),
            },
        )
        return "outline_gate", {}
    runtime_state["terminal_status"] = "blocked"
    if budget_stop_reason:
        runtime_state["terminal_reason"] = budget_stop_reason
    elif aggregate.get("blocked_section_count"):
        runtime_state["terminal_reason"] = "required sections remain blocked"
    elif aggregate.get("pending_section_count"):
        runtime_state["terminal_reason"] = "required sections are not yet certified"
    else:
        runtime_state["terminal_reason"] = decision_reason or "no admitted sections available"
    emit_decision("stop", runtime_state["terminal_reason"], iteration=max(1, current_iteration or 1))
    return "finalize", {}


def decide_outline_gate_next_step(
    *,
    runtime_state: dict[str, Any],
    aggregate: dict[str, Any],
    reportable_sections: list[Any],
    current_iteration: int,
    emit_decision: EmitDecisionFn,
) -> str:
    if not bool(aggregate.get("outline_ready")):
        if reportable_sections:
            _clear_terminal_state(runtime_state)
            emit_decision(
                "outline_partial",
                "required sections are incomplete; generating a report from admitted sections",
                iteration=max(1, current_iteration or 1),
                extra={
                    **aggregate,
                    "reportable_section_count": len(reportable_sections),
                },
            )
            return "report"
        runtime_state["terminal_status"] = "blocked"
        runtime_state["terminal_reason"] = "required sections produced no reportable content"
        return "finalize"
    _clear_terminal_state(runtime_state)
    emit_decision(
        "outline_ready",
        "preferred-quality sections ready for final report",
        iteration=max(1, current_iteration or 1),
        extra=aggregate,
    )
    return "report"


def _set_section_status(runtime_state: dict[str, Any], section_id: str, status: str) -> None:
    runtime_state["section_status_map"] = {
        **dict(runtime_state.get("section_status_map") or {}),
        str(section_id): status,
    }


def _build_pending_replan(
    *,
    section: dict[str, Any],
    draft: dict[str, Any],
    review: dict[str, Any],
    preferred_action: str,
) -> dict[str, Any]:
    coverage_summary = draft.get("coverage_summary") if isinstance(draft.get("coverage_summary"), dict) else {}
    contradiction_summary = (
        draft.get("contradiction_summary")
        if isinstance(draft.get("contradiction_summary"), dict)
        else {}
    )
    issue_ids = _dedupe_texts(
        [
            str(item.get("id") or "").strip()
            for item in [*(review.get("blocking_issues") or []), *(review.get("advisory_issues") or [])]
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
    )
    issue_types = _dedupe_texts(
        [
            str(item.get("issue_type") or "").strip()
            for item in [*(review.get("blocking_issues") or []), *(review.get("advisory_issues") or [])]
            if isinstance(item, dict) and str(item.get("issue_type") or "").strip()
        ]
    )
    follow_up_queries = _dedupe_texts(
        [
            *list(review.get("follow_up_queries") or []),
            *list(coverage_summary.get("missing_topics") or []),
            *list(draft.get("open_questions") or []),
            str(section.get("core_question") or "").strip(),
            str(section.get("objective") or draft.get("objective") or "").strip(),
        ]
    )
    return {
        "section_id": str(draft.get("section_id") or section.get("id") or "").strip(),
        "section_order": int(section.get("section_order", draft.get("section_order", 0)) or 0),
        "task_id": str(draft.get("task_id") or "").strip(),
        "draft_id": str(draft.get("id") or "").strip(),
        "review_id": str(review.get("id") or "").strip(),
        "preferred_action": preferred_action,
        "reason": str(review.get("notes") or review.get("verdict") or "").strip(),
        "issue_types": issue_types,
        "issue_ids": issue_ids,
        "follow_up_queries": follow_up_queries,
        "open_questions": list(draft.get("open_questions") or []),
        "missing_topics": list(coverage_summary.get("missing_topics") or []),
        "needs_counterevidence_query": bool(
            contradiction_summary.get("needs_counterevidence_query")
        ),
        "objective": str(section.get("objective") or draft.get("objective") or "").strip(),
        "core_question": str(section.get("core_question") or draft.get("core_question") or "").strip(),
        "reportability": str(review.get("reportability") or "").strip(),
        "quality_band": str(review.get("quality_band") or "").strip(),
    }


def _clear_terminal_state(runtime_state: dict[str, Any]) -> None:
    runtime_state["terminal_status"] = ""
    runtime_state["terminal_reason"] = ""
