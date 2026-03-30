"""
Worker dispatch and task orchestration helpers for the multi-agent runtime.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from typing import Any, Dict, List

from agent.core.context import build_research_worker_context, merge_research_worker_context
from agent.runtime.deep.multi_agent import support
from agent.runtime.deep.multi_agent.schema import (
    AgentRunRecord,
    EvidenceCard,
    ReportSectionDraft,
    ResearchTask,
    WorkerExecutionResult,
    _now_iso,
)


def build_tasks_from_plan(runtime: Any, plan_items: List[Dict[str, Any]], *, context_id: str) -> List[ResearchTask]:
    tasks: List[ResearchTask] = []
    for item in plan_items or []:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if not query:
            continue
        aspect = str(item.get("aspect") or "").strip()
        priority = int(item.get("priority") or len(tasks) + 1)
        title = aspect or query
        tasks.append(
            ResearchTask(
                id=support._new_id("task"),
                goal=title,
                query=query,
                priority=priority,
                title=title,
                aspect=aspect,
                parent_context_id=context_id,
            )
        )
    return tasks


def dispatch_ready_tasks(runtime: Any, current_iteration: int) -> List[WorkerExecutionResult]:
    runtime.budget_stop_reason = support._budget_stop_reason(
        start_ts=runtime.start_ts,
        searches_used=runtime.searches_used,
        tokens_used=runtime.tokens_used,
        max_seconds=runtime.max_seconds,
        max_tokens=runtime.max_tokens,
        max_searches=runtime.max_searches,
    )
    if runtime.budget_stop_reason:
        return []

    remaining_search_slots = runtime.parallel_workers
    if runtime.max_searches > 0:
        remaining_search_slots = min(
            remaining_search_slots,
            max(0, runtime.max_searches - runtime.searches_used),
        )
    if remaining_search_slots <= 0:
        runtime.budget_stop_reason = "search_budget_exceeded"
        return []

    agent_ids = [runtime._next_agent_id("researcher") for _ in range(remaining_search_slots)]
    claimed = runtime.task_queue.claim_ready_tasks(limit=remaining_search_slots, agent_ids=agent_ids)
    if not claimed:
        return []

    for task in claimed:
        runtime._emit_task_update(task=task, status=task.status)

    results: List[WorkerExecutionResult] = []
    with ThreadPoolExecutor(max_workers=min(len(claimed), runtime.parallel_workers)) as executor:
        futures = {
            executor.submit(run_worker_task, runtime, task, current_iteration): task
            for task in claimed
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def run_worker_task(runtime: Any, task: ResearchTask, current_iteration: int) -> WorkerExecutionResult:
    agent_id = task.assigned_agent_id or runtime._next_agent_id("researcher")
    record = AgentRunRecord(
        id=support._new_id("agent_run"),
        role="researcher",
        phase="research",
        status="running",
        agent_id=agent_id,
        task_id=task.id,
    )
    with runtime._agent_run_lock:
        runtime.agent_runs.append(record)
    runtime._emit_agent_start(
        agent_id=agent_id,
        role="researcher",
        phase="research",
        task_id=task.id,
        iteration=current_iteration,
    )

    worker_context = build_research_worker_context(
        runtime.state,
        task_id=task.id,
        agent_id=agent_id,
        query=task.query,
        topic=runtime.topic,
        brief={
            "topic": runtime.topic,
            "goal": task.goal,
            "aspect": task.aspect,
            "iteration": current_iteration,
        },
        related_artifacts=runtime.artifact_store.get_related_artifacts(task.id),
    )

    try:
        runtime._check_cancel()
        results = runtime.researcher.execute_queries(
            [task.query],
            max_results_per_query=runtime.results_per_query,
        )
        summary = runtime.researcher.summarize_findings(
            runtime.topic,
            results,
            existing_summary=runtime._knowledge_summary(),
        )
        evidence_cards: List[EvidenceCard] = []
        for item in results[: min(3, len(results))]:
            evidence_cards.append(
                EvidenceCard(
                    id=support._new_id("evidence"),
                    task_id=task.id,
                    source_title=str(item.get("title") or item.get("url") or "Untitled"),
                    source_url=str(item.get("url") or ""),
                    summary=str(item.get("summary") or item.get("snippet") or summary[:280]),
                    excerpt=str(item.get("raw_excerpt") or item.get("summary") or "")[:700],
                    source_provider=str(item.get("provider") or ""),
                    published_date=item.get("published_date"),
                    created_by=agent_id,
                    metadata={"query": task.query},
                )
            )

        section_draft = ReportSectionDraft(
            id=support._new_id("section"),
            task_id=task.id,
            title=task.title or task.goal,
            summary=summary or f"未能从“{task.query}”提取到足够结论。",
            evidence_ids=[card.id for card in evidence_cards],
            created_by=agent_id,
        )

        worker_context.summary_notes.append(section_draft.summary)
        worker_context.scraped_content.append(
            {
                "query": task.query,
                "results": results,
                "timestamp": _now_iso(),
                "task_id": task.id,
                "agent_id": agent_id,
            }
        )
        worker_context.sources.extend(support._compact_sources(results, limit=10))
        worker_context.artifacts_created.extend(
            [asdict(card) for card in evidence_cards] + [asdict(section_draft)]
        )
        worker_context.is_complete = True

        record.status = "completed"
        record.summary = section_draft.summary[:240]
        record.ended_at = _now_iso()
        runtime._emit_agent_complete(
            agent_id=agent_id,
            role="researcher",
            phase="research",
            status="completed",
            task_id=task.id,
            iteration=current_iteration,
            summary=record.summary,
        )

        return WorkerExecutionResult(
            task=task,
            context=worker_context,
            evidence_cards=evidence_cards,
            section_draft=section_draft,
            raw_results=results,
            tokens_used=support._estimate_tokens_from_results(results)
            + support._estimate_tokens_from_text(summary),
        )
    except Exception as exc:
        worker_context.errors.append(str(exc))
        worker_context.is_complete = True
        record.status = "failed"
        record.summary = str(exc)
        record.ended_at = _now_iso()
        runtime._emit_agent_complete(
            agent_id=agent_id,
            role="researcher",
            phase="research",
            status="failed",
            task_id=task.id,
            iteration=current_iteration,
            summary=str(exc),
        )
        return WorkerExecutionResult(
            task=task,
            context=worker_context,
            evidence_cards=[],
            section_draft=None,
            raw_results=[],
            tokens_used=0,
        )


def merge_worker_result(runtime: Any, result: WorkerExecutionResult) -> None:
    updates = merge_research_worker_context(runtime.state, result.context)
    runtime.state.update(updates)
    runtime.searches_used += 1
    runtime.tokens_used += max(0, result.tokens_used)

    if result.evidence_cards:
        runtime.artifact_store.add_evidence(result.evidence_cards)
        for card in result.evidence_cards:
            runtime._emit_artifact_update(
                artifact_id=card.id,
                artifact_type="evidence_card",
                status=card.status,
                task_id=card.task_id,
                agent_id=card.created_by,
                summary=card.summary[:180],
                source_url=card.source_url,
            )

    if result.section_draft:
        runtime.artifact_store.add_section_draft(result.section_draft)
        runtime._emit_artifact_update(
            artifact_id=result.section_draft.id,
            artifact_type="report_section_draft",
            status=result.section_draft.status,
            task_id=result.section_draft.task_id,
            agent_id=result.section_draft.created_by,
            summary=result.section_draft.summary[:180],
        )

    if result.raw_results:
        updated_task = runtime.task_queue.update_status(result.task.id, "completed")
    else:
        updated_task = runtime.task_queue.update_status(
            result.task.id,
            "failed",
            reason="researcher returned no results",
        )
    if updated_task:
        runtime._emit_task_update(task=updated_task, status=updated_task.status)

    runtime._emit_research_tree_update()


__all__ = [
    "build_tasks_from_plan",
    "dispatch_ready_tasks",
    "merge_worker_result",
    "run_worker_task",
]
