"""Worker-node helpers for the Deep Research engine."""

from __future__ import annotations

import copy
from typing import Any

import agent.deep_research.branch_research.budgets as budgets
from agent.deep_research.engine.section_logic import _branch_title
from agent.deep_research.engine.text_analysis import _dedupe_texts
from agent.deep_research.ids import _new_id


def run_researcher_step(
    *,
    parts: Any,
    task: Any,
    section: dict[str, Any],
    record: dict[str, Any],
    topic: str,
    researcher: Any,
    results_per_query: int,
    emit_task_update_fn: Any,
    build_evidence_bundle_fn: Any,
    build_section_draft_fn: Any,
    finish_agent_run_fn: Any,
) -> dict[str, Any]:
    try:
        task.stage = "search"
        emit_task_update_fn(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="search")
        outcome = researcher.research_branch(
            task,
            topic=topic,
            existing_summary="\n".join(parts.shared_state.get("summary_notes", [])[:6]),
            max_results_per_query=results_per_query,
        )
        results = list(outcome.get("search_results") or [])
        if not results:
            raise RuntimeError("section researcher returned no evidence")
        task.stage = "read"
        emit_task_update_fn(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="read")
        task.stage = "extract"
        emit_task_update_fn(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="extract")
        task.stage = "synthesize"
        emit_task_update_fn(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="synthesize")
        summary = str(outcome.get("summary") or "").strip() or f"未能为 {_branch_title(task)} 形成有效章节摘要。"
        bundle = build_evidence_bundle_fn(task, outcome, str(record.get("agent_id") or "researcher"))
        section_draft = build_section_draft_fn(
            task,
            section,
            bundle,
            outcome,
            str(record.get("agent_id") or "researcher"),
        )
        finish_agent_run_fn(parts, record, status="completed", summary=summary, stage="synthesize")
        return {
            "worker_results": [
                {
                    "task": task.to_dict(),
                    "result_status": "completed",
                    "section_draft": section_draft,
                    "evidence_bundle": bundle,
                    "branch_artifacts": copy.deepcopy(outcome.get("branch_artifacts") or {}),
                    "raw_results": copy.deepcopy(results),
                    "tokens_used": (
                        budgets._estimate_tokens_from_results(results)
                        + sum(
                            budgets._estimate_tokens_from_text(str(item.get("content") or "")[:800])
                            for item in bundle.get("documents", [])[:3]
                            if isinstance(item, dict)
                        )
                        + budgets._estimate_tokens_from_text(summary)
                    ),
                    "searches_used": len(outcome.get("queries") or task.query_hints or [task.query]),
                    "agent_run": copy.deepcopy(record),
                }
            ]
        }
    except Exception as exc:
        finish_agent_run_fn(parts, record, status="failed", summary=str(exc), stage=task.stage or "search")
        return {
            "worker_results": [
                {
                    "task": task.to_dict(),
                    "result_status": "failed",
                    "error": str(exc),
                    "raw_results": [],
                    "tokens_used": 0,
                    "searches_used": 0,
                    "agent_run": copy.deepcopy(record),
                }
            ]
        }


def run_revisor_step(
    *,
    parts: Any,
    task: Any,
    section: dict[str, Any],
    current_draft: dict[str, Any],
    review: dict[str, Any],
    record: dict[str, Any],
    emit_task_update_fn: Any,
    finish_agent_run_fn: Any,
) -> dict[str, Any]:
    try:
        if not current_draft:
            raise RuntimeError("section revision requires an existing draft")
        claim_units = [
            item
            for item in current_draft.get("claim_units", []) or []
            if isinstance(item, dict)
        ]
        retained_claims = [
            item
            for item in claim_units
            if str(item.get("importance") or "").strip().lower() == "primary" or bool(item.get("grounded"))
        ] or claim_units[:1]
        revised_findings = [
            str(item.get("text") or "").strip()
            for item in retained_claims
            if str(item.get("text") or "").strip()
        ]
        revised_summary = (
            revised_findings[0]
            if revised_findings
            else str(current_draft.get("summary") or task.objective or task.goal).strip()
        )
        advisory_messages = [
            str(item.get("message") or "").strip()
            for item in review.get("advisory_issues", []) or []
            if str(item.get("message") or "").strip()
        ]
        revised_draft = copy.deepcopy(current_draft)
        revised_draft["id"] = _new_id("section_draft")
        revised_draft["task_id"] = task.id
        revised_draft["summary"] = revised_summary
        revised_draft["key_findings"] = _dedupe_texts(revised_findings or current_draft.get("key_findings") or [])
        revised_draft["claim_units"] = retained_claims
        revised_draft["limitations"] = _dedupe_texts(
            [*list(current_draft.get("limitations") or []), *advisory_messages]
        )
        revised_draft["review_status"] = "pending"
        revised_draft["certified"] = False
        revised_draft["section_order"] = int(section.get("section_order", current_draft.get("section_order", 0)) or 0)
        task.stage = "revision"
        emit_task_update_fn(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="revision")
        finish_agent_run_fn(parts, record, status="completed", summary=revised_summary, stage="revision")
        return {
            "worker_results": [
                {
                    "task": task.to_dict(),
                    "result_status": "completed",
                    "section_draft": revised_draft,
                    "raw_results": [],
                    "tokens_used": budgets._estimate_tokens_from_text(revised_summary),
                    "searches_used": 0,
                    "agent_run": copy.deepcopy(record),
                }
            ]
        }
    except Exception as exc:
        finish_agent_run_fn(parts, record, status="failed", summary=str(exc), stage=task.stage or "revision")
        return {
            "worker_results": [
                {
                    "task": task.to_dict(),
                    "result_status": "failed",
                    "error": str(exc),
                    "raw_results": [],
                    "tokens_used": 0,
                    "searches_used": 0,
                    "agent_run": copy.deepcopy(record),
                }
            ]
        }
