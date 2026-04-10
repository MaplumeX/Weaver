"""Worker-result merge helpers for the Deep Research engine."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from agent.deep_research.engine.artifact_store import LightweightArtifactStore
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import ResearchTask
from agent.deep_research.store import ResearchTaskQueue

EmitArtifactUpdateFn = Callable[..., None]
EmitTaskUpdateFn = Callable[..., None]


def merge_worker_results(
    *,
    payloads: list[dict[str, Any]],
    shared_state: dict[str, Any],
    task_queue: ResearchTaskQueue,
    artifact_store: LightweightArtifactStore,
    runtime_state: dict[str, Any],
    agent_runs: list[dict[str, Any]],
    current_iteration: int,
    task_retry_limit: int,
    emit_task_update: EmitTaskUpdateFn,
    emit_artifact_update: EmitArtifactUpdateFn,
) -> None:
    for payload in payloads:
        _merge_agent_run(payload, agent_runs, runtime_state)
        runtime_state["searches_used"] = int(runtime_state.get("searches_used") or 0) + int(payload.get("searches_used") or 0)
        runtime_state["tokens_used"] = int(runtime_state.get("tokens_used") or 0) + int(payload.get("tokens_used") or 0)
        task = ResearchTask(**payload["task"])
        if payload.get("result_status") == "completed":
            _merge_completed_payload(
                payload=payload,
                task=task,
                shared_state=shared_state,
                task_queue=task_queue,
                artifact_store=artifact_store,
                runtime_state=runtime_state,
                current_iteration=current_iteration,
                emit_task_update=emit_task_update,
                emit_artifact_update=emit_artifact_update,
            )
            continue
        _merge_failed_payload(
            payload=payload,
            task=task,
            shared_state=shared_state,
            task_queue=task_queue,
            runtime_state=runtime_state,
            current_iteration=current_iteration,
            task_retry_limit=task_retry_limit,
            emit_task_update=emit_task_update,
        )


def _merge_agent_run(
    payload: dict[str, Any],
    agent_runs: list[dict[str, Any]],
    runtime_state: dict[str, Any],
) -> None:
    agent_run = payload.get("agent_run")
    if not isinstance(agent_run, dict):
        return
    agent_runs.append(copy.deepcopy(agent_run))
    role = str(agent_run.get("role") or "").strip()
    if not role:
        return
    role_tool_policies = dict(runtime_state.get("role_tool_policies") or {})
    role_tool_policies[role] = {
        "role": role,
        "requested_tools": list(agent_run.get("requested_tools") or []),
        "allowed_tool_names": list(agent_run.get("resolved_tools") or []),
    }
    runtime_state["role_tool_policies"] = role_tool_policies


def _merge_completed_payload(
    *,
    payload: dict[str, Any],
    task: ResearchTask,
    shared_state: dict[str, Any],
    task_queue: ResearchTaskQueue,
    artifact_store: LightweightArtifactStore,
    runtime_state: dict[str, Any],
    current_iteration: int,
    emit_task_update: EmitTaskUpdateFn,
    emit_artifact_update: EmitArtifactUpdateFn,
) -> None:
    bundle = copy.deepcopy(payload.get("evidence_bundle") or {})
    section_draft = copy.deepcopy(payload.get("section_draft") or {})
    branch_artifacts = copy.deepcopy(payload.get("branch_artifacts") or {})
    if bundle:
        artifact_store.set_evidence_bundle(bundle)
    if section_draft:
        artifact_store.set_section_draft(section_draft)
    if isinstance(branch_artifacts.get("query_rounds"), list):
        artifact_store.set_branch_query_rounds(task.id, branch_artifacts.get("query_rounds") or [])
    if isinstance(branch_artifacts.get("coverage"), dict):
        artifact_store.set_branch_coverage(branch_artifacts.get("coverage") or {})
    if isinstance(branch_artifacts.get("quality"), dict):
        artifact_store.set_branch_quality(branch_artifacts.get("quality") or {})
    if isinstance(branch_artifacts.get("contradiction"), dict):
        artifact_store.set_branch_contradiction(branch_artifacts.get("contradiction") or {})
    if isinstance(branch_artifacts.get("grounding"), dict):
        artifact_store.set_branch_grounding(branch_artifacts.get("grounding") or {})
    if isinstance(branch_artifacts.get("decisions"), list):
        artifact_store.set_branch_decisions(task.id, branch_artifacts.get("decisions") or [])

    updated_task = task_queue.update_status(task.id, "completed")
    if updated_task:
        emit_task_update(updated_task, "completed", iteration=max(1, current_iteration or 1))
    if task.section_id:
        _set_section_status(runtime_state, str(task.section_id), "drafted")

    shared_state["summary_notes"] = [
        *(shared_state.get("summary_notes") or []),
        str(section_draft.get("summary") or ""),
    ]
    if bundle:
        shared_state["sources"] = [
            *(shared_state.get("sources") or []),
            *(bundle.get("sources") or []),
        ]
    shared_state["scraped_content"] = [
        *(shared_state.get("scraped_content") or []),
        {
            "task_id": task.id,
            "section_id": task.section_id,
            "query": task.query,
            "results": copy.deepcopy(payload.get("raw_results") or []),
            "summary": section_draft.get("summary"),
        },
    ]
    _emit_completed_artifact_updates(
        bundle=bundle,
        section_draft=section_draft,
        branch_artifacts=branch_artifacts,
        task=task,
        current_iteration=current_iteration,
        emit_artifact_update=emit_artifact_update,
    )


def _emit_completed_artifact_updates(
    *,
    bundle: dict[str, Any],
    section_draft: dict[str, Any],
    branch_artifacts: dict[str, Any],
    task: ResearchTask,
    current_iteration: int,
    emit_artifact_update: EmitArtifactUpdateFn,
) -> None:
    if bundle:
        emit_artifact_update(
            artifact_id=str(bundle.get("id") or _new_id("bundle")),
            artifact_type="evidence_bundle",
            summary=f"{len(bundle.get('sources', []))} sources",
            task_id=task.id,
            section_id=task.section_id,
            branch_id=task.branch_id,
            iteration=max(1, current_iteration or 1),
            extra={
                "source_count": len(bundle.get("sources", []) or []),
                "document_count": len(bundle.get("documents", []) or []),
                "passage_count": len(bundle.get("passages", []) or []),
                "source_urls": [
                    str(item.get("url") or "").strip()
                    for item in bundle.get("sources", []) or []
                    if str(item.get("url") or "").strip()
                ],
            },
        )
    if section_draft:
        emit_artifact_update(
            artifact_id=str(section_draft.get("id") or _new_id("section_draft")),
            artifact_type="section_draft",
            summary=str(section_draft.get("summary") or ""),
            task_id=task.id,
            section_id=task.section_id,
            branch_id=task.branch_id,
            iteration=max(1, current_iteration or 1),
            extra={
                "title": str(section_draft.get("title") or ""),
                "source_urls": list(section_draft.get("source_urls") or []),
                "finding_count": len(section_draft.get("key_findings") or []),
            },
        )
    if isinstance(branch_artifacts.get("coverage"), dict):
        coverage = branch_artifacts.get("coverage") or {}
        emit_artifact_update(
            artifact_id=str(coverage.get("id") or _new_id("branch_coverage")),
            artifact_type="branch_coverage",
            summary=f"covered {coverage.get('covered_count', 0)} / {max(1, int(coverage.get('covered_count', 0) or 0) + int(coverage.get('partial_count', 0) or 0) + int(coverage.get('missing_count', 0) or 0))}",
            task_id=task.id,
            section_id=task.section_id,
            branch_id=task.branch_id,
            iteration=max(1, current_iteration or 1),
        )
    if isinstance(branch_artifacts.get("quality"), dict):
        quality = branch_artifacts.get("quality") or {}
        emit_artifact_update(
            artifact_id=str(quality.get("id") or _new_id("branch_quality")),
            artifact_type="branch_quality",
            summary=str(quality.get("notes") or "branch quality updated"),
            task_id=task.id,
            section_id=task.section_id,
            branch_id=task.branch_id,
            iteration=max(1, current_iteration or 1),
        )
    if isinstance(branch_artifacts.get("grounding"), dict):
        grounding = branch_artifacts.get("grounding") or {}
        emit_artifact_update(
            artifact_id=str(grounding.get("id") or _new_id("branch_grounding")),
            artifact_type="branch_grounding",
            summary=f"primary grounding {grounding.get('primary_grounding_ratio', 0.0)}",
            task_id=task.id,
            section_id=task.section_id,
            branch_id=task.branch_id,
            iteration=max(1, current_iteration or 1),
        )


def _merge_failed_payload(
    *,
    payload: dict[str, Any],
    task: ResearchTask,
    shared_state: dict[str, Any],
    task_queue: ResearchTaskQueue,
    runtime_state: dict[str, Any],
    current_iteration: int,
    task_retry_limit: int,
    emit_task_update: EmitTaskUpdateFn,
) -> None:
    reason = str(payload.get("error") or "researcher returned no results")
    failed_task = task_queue.update_stage(task.id, task.stage or "search", status="failed", reason=reason)
    if failed_task:
        emit_task_update(failed_task, "failed", iteration=max(1, current_iteration or 1), reason=reason)
    if task.task_kind == "section_revision":
        if task.section_id:
            _set_section_status(runtime_state, str(task.section_id), "drafted")
    elif task.attempts < task_retry_limit and not runtime_state.get("budget_stop_reason"):
        retry_task = task_queue.update_stage(task.id, "planned", status="ready", reason=reason)
        if retry_task:
            emit_task_update(retry_task, "ready", iteration=max(1, current_iteration or 1), reason=reason)
    shared_state["errors"] = [
        *(shared_state.get("errors") or []),
        reason,
    ]


def _set_section_status(runtime_state: dict[str, Any], section_id: str, status: str) -> None:
    if not str(section_id or "").strip():
        return
    runtime_state["section_status_map"] = {
        **dict(runtime_state.get("section_status_map") or {}),
        str(section_id): status,
    }
