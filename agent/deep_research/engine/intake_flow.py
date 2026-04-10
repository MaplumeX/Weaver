"""Intake-flow helpers for the Deep Research engine."""

from __future__ import annotations

import copy
from typing import Any


def run_clarify_step(
    *,
    parts: Any,
    record: dict[str, Any],
    topic: str,
    graph_run_id: str,
    graph_attempt: int,
    allow_interrupts: bool,
    clarifier: Any,
    build_clarify_transcript_fn: Any,
    extract_interrupt_text_fn: Any,
    interrupt_fn: Any,
    emit_decision_fn: Any,
    finish_agent_run_fn: Any,
    patch_fn: Any,
) -> dict[str, Any]:
    clarify_answers = list(parts.runtime_state.get("clarify_answer_history") or [])
    clarify_history = build_clarify_transcript_fn(
        list(parts.runtime_state.get("clarify_question_history") or []),
        clarify_answers,
    )
    result = clarifier.assess_intake(
        topic,
        clarify_answers=clarify_answers,
        clarify_history=clarify_history,
    )
    clarification_state = copy.deepcopy(result or {})
    status = str(clarification_state.get("status") or "ready_for_scope").strip().lower()
    question = str(clarification_state.get("follow_up_question") or "").strip()
    parts.runtime_state["clarification_state"] = clarification_state

    if status == "needs_user_input" and question and allow_interrupts and not clarify_answers:
        prompt = {
            "checkpoint": "deep_research_clarify",
            "message": question,
            "question": question,
            "graph_run_id": graph_run_id,
            "graph_attempt": graph_attempt,
        }
        emit_decision_fn("clarify_required", question, iteration=max(1, parts.current_iteration or 1))
        finish_agent_run_fn(parts, record, status="completed", summary=question)
        updated = interrupt_fn(prompt)
        answer = extract_interrupt_text_fn(updated, keys=("clarify_answer", "answer", "content"))
        if not answer:
            raise ValueError("deep_research clarify resume requires non-empty clarify_answer")
        parts.runtime_state["clarify_question_history"] = [
            *list(parts.runtime_state.get("clarify_question_history") or []),
            question,
        ]
        parts.runtime_state["clarify_answer_history"] = [
            *list(parts.runtime_state.get("clarify_answer_history") or []),
            answer,
        ]
        parts.runtime_state["clarify_question"] = question
        parts.runtime_state["intake_status"] = "pending"
        return patch_fn(parts, next_step="clarify")

    if status == "needs_user_input":
        clarification_state["status"] = "ready_for_scope"
        clarification_state["follow_up_question"] = ""
        clarification_state["blocking_slot"] = "none"
        parts.runtime_state["clarification_state"] = clarification_state

    parts.runtime_state["clarify_question"] = ""
    parts.runtime_state["intake_status"] = "ready_for_scope"
    reason = (
        "clarify complete; remaining ambiguity delegated to scope"
        if status == "needs_user_input"
        else "clarify ready"
    )
    emit_decision_fn("scope_ready", reason, iteration=max(1, parts.current_iteration or 1))
    finish_agent_run_fn(parts, record, status="completed", summary=reason)
    return patch_fn(parts, next_step="scope")


def run_scope_step(
    *,
    parts: Any,
    record: dict[str, Any],
    topic: str,
    scope_agent: Any,
    build_clarify_transcript_fn: Any,
    scope_draft_from_payload_fn: Any,
    build_scope_draft_fn: Any,
    format_scope_draft_markdown_fn: Any,
    emit_decision_fn: Any,
    emit_artifact_update_fn: Any,
    finish_agent_run_fn: Any,
    patch_fn: Any,
) -> dict[str, Any]:
    clarification_state = copy.deepcopy(parts.runtime_state.get("clarification_state") or {})
    current_scope_payload = copy.deepcopy(parts.runtime_state.get("current_scope_draft") or {})
    pending_feedback = ""
    feedback_history = list(parts.runtime_state.get("scope_feedback_history") or [])
    if feedback_history:
        pending_feedback = str(feedback_history[-1].get("feedback") or "").strip()

    scope_payload = scope_agent.create_scope(
        topic,
        clarification_state=clarification_state,
        previous_scope=current_scope_payload if pending_feedback else {},
        scope_feedback=pending_feedback,
        clarify_transcript=build_clarify_transcript_fn(
            list(parts.runtime_state.get("clarify_question_history") or []),
            list(parts.runtime_state.get("clarify_answer_history") or []),
        ),
    )
    existing_scope = scope_draft_from_payload_fn(current_scope_payload)
    next_version = existing_scope.version + 1 if existing_scope and pending_feedback else 1
    scope_draft = build_scope_draft_fn(
        topic=topic,
        version=next_version,
        draft_payload=scope_payload,
        clarification_context=clarification_state,
        feedback=pending_feedback,
        agent_id=record.get("agent_id", "scope"),
        previous=current_scope_payload if pending_feedback else None,
    )
    parts.runtime_state["current_scope_draft"] = scope_draft.to_dict()
    parts.runtime_state["intake_status"] = "awaiting_scope_review"
    parts.runtime_state["scope_revision_count"] = max(0, scope_draft.version - 1)
    emit_decision_fn(
        "scope_revision_requested" if pending_feedback else "scope_ready",
        pending_feedback or "scope ready for review",
        iteration=max(1, parts.current_iteration or 1),
        extra={"scope_version": scope_draft.version},
    )
    emit_artifact_update_fn(
        artifact_id=scope_draft.id,
        artifact_type="scope_draft",
        summary=scope_draft.research_goal,
        status=scope_draft.status,
        iteration=max(1, parts.current_iteration or 1),
        extra={"content": format_scope_draft_markdown_fn(scope_draft)},
    )
    finish_agent_run_fn(parts, record, status="completed", summary=scope_draft.research_goal)
    return patch_fn(parts, next_step="scope_review")


def run_scope_review_step(
    *,
    parts: Any,
    graph_run_id: str,
    graph_attempt: int,
    allow_interrupts: bool,
    scope_draft_from_payload_fn: Any,
    format_scope_draft_markdown_fn: Any,
    extract_interrupt_text_fn: Any,
    interrupt_fn: Any,
    emit_decision_fn: Any,
    patch_fn: Any,
    now_iso_fn: Any,
) -> dict[str, Any]:
    scope_draft = scope_draft_from_payload_fn(parts.runtime_state.get("current_scope_draft"))
    if not scope_draft:
        return patch_fn(parts, next_step="scope")

    if not allow_interrupts:
        approved_payload = scope_draft.to_dict()
        approved_payload["status"] = "approved"
        parts.runtime_state["approved_scope_draft"] = approved_payload
        parts.runtime_state["intake_status"] = "scope_approved"
        emit_decision_fn("scope_approved", "interrupts disabled; auto approve", iteration=max(1, parts.current_iteration or 1))
        return patch_fn(parts, next_step="research_brief")

    prompt = {
        "checkpoint": "deep_research_scope_review",
        "message": "Review the proposed Deep Research scope.",
        "graph_run_id": graph_run_id,
        "graph_attempt": graph_attempt,
        "scope_draft": scope_draft.to_dict(),
        "scope_version": scope_draft.version,
        "scope_revision_count": int(parts.runtime_state.get("scope_revision_count", 0) or 0),
        "content": format_scope_draft_markdown_fn(scope_draft),
        "available_actions": ["approve_scope", "revise_scope"],
    }
    updated = interrupt_fn(prompt)
    action = str((updated or {}).get("action") or "").strip().lower() if isinstance(updated, dict) else ""
    if not action:
        action = (
            "revise_scope"
            if extract_interrupt_text_fn(updated, keys=("scope_feedback", "feedback", "content"))
            else "approve_scope"
        )
    if action == "approve_scope":
        approved_payload = scope_draft.to_dict()
        approved_payload["status"] = "approved"
        parts.runtime_state["approved_scope_draft"] = approved_payload
        parts.runtime_state["intake_status"] = "scope_approved"
        emit_decision_fn("scope_approved", "user approved the current scope draft", iteration=max(1, parts.current_iteration or 1))
        return patch_fn(parts, next_step="research_brief")

    feedback = extract_interrupt_text_fn(updated, keys=("scope_feedback", "feedback", "content"))
    if not feedback:
        raise ValueError("revise_scope requires non-empty scope_feedback")
    history = list(parts.runtime_state.get("scope_feedback_history") or [])
    history.append({"scope_version": scope_draft.version, "feedback": feedback, "at": now_iso_fn()})
    parts.runtime_state["scope_feedback_history"] = history
    parts.runtime_state["intake_status"] = "scope_revision_requested"
    emit_decision_fn("scope_revision_requested", feedback, iteration=max(1, parts.current_iteration or 1))
    return patch_fn(parts, next_step="scope")


def run_research_brief_step(
    *,
    parts: Any,
    topic: str,
    dedupe_texts_fn: Any,
    emit_artifact_update_fn: Any,
    emit_decision_fn: Any,
    patch_fn: Any,
    new_id_fn: Any,
) -> dict[str, Any]:
    approved_scope = copy.deepcopy(parts.runtime_state.get("approved_scope_draft") or {})
    if not approved_scope:
        return patch_fn(parts, next_step="scope_review")
    scope = approved_scope
    if "coverage_dimensions" not in scope:
        scope["coverage_dimensions"] = dedupe_texts_fn(scope.get("core_questions") or scope.get("in_scope") or [])
    if "deliverable_constraints" not in scope:
        scope["deliverable_constraints"] = dedupe_texts_fn(
            scope.get("deliverable_preferences") or scope.get("constraints") or []
        )
    if not scope.get("time_boundary"):
        for item in scope.get("constraints", []) or []:
            text = str(item or "").strip()
            if text.lower().startswith("time range:"):
                scope["time_boundary"] = text.split(":", 1)[1].strip()
                break
    scope["status"] = "approved"
    parts.artifact_store.set_scope(scope)
    parts.runtime_state["active_agent"] = "scope"
    parts.runtime_state["scope_id"] = str(scope.get("id") or "")
    emit_artifact_update_fn(
        artifact_id=str(scope.get("id") or new_id_fn("scope")),
        artifact_type="scope",
        summary=str(scope.get("research_goal") or topic),
        status="completed",
        iteration=max(1, parts.current_iteration or 1),
    )
    emit_decision_fn(
        "research_brief_ready",
        "approved scope normalized into runtime scope",
        iteration=max(1, parts.current_iteration or 1),
    )
    return patch_fn(parts, next_step="outline_plan")
