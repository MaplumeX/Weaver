"""
Lightweight LangGraph-backed Deep Research runtime.

This module keeps the public entrypoints stable while dramatically reducing the
number of persisted runtime artifacts. The loop is intentionally compact:

clarify -> scope -> scope_review -> research_brief -> supervisor_plan
-> dispatch -> researcher -> merge -> verify -> supervisor_decide
-> outline_gate -> report -> finalize
"""

from __future__ import annotations

import copy
import logging
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Command, Send, interrupt

from agent.contracts.events import ToolEventType, get_emitter_sync
from agent.core.llm_factory import create_chat_model
from agent.core.state import build_deep_runtime_snapshot
from agent.runtime.deep.artifacts.public_artifacts import build_public_deep_research_artifacts
from agent.runtime.deep.config import resolve_max_searches, resolve_parallel_workers
from agent.runtime.deep.roles.clarify import DeepResearchClarifyAgent
from agent.runtime.deep.roles.reporter import (
    ReportContext,
    ReportSectionContext,
    ReportSource,
    ResearchReporter,
)
from agent.runtime.deep.roles.researcher import ResearchAgent
from agent.runtime.deep.roles.scope import DeepResearchScopeAgent
from agent.runtime.deep.roles.supervisor import (
    ResearchSupervisor,
    SupervisorAction,
    SupervisorDecision,
)
from agent.runtime.deep.schema import (
    AgentRunRecord,
    BranchResult,
    EvidenceBundle,
    FinalReportArtifact,
    ResearchPlanArtifact,
    ResearchTask,
    ScopeDraft,
    ValidationSummary,
    _now_iso,
)
from agent.runtime.deep.services.knowledge_gap import GapAnalysisResult, KnowledgeGapAnalyzer
from agent.runtime.deep.state import read_deep_runtime_snapshot
from agent.runtime.deep.store import ResearchTaskQueue
from agent.runtime.deep.support.graph_helpers import (
    MultiAgentGraphState,
    build_clarify_transcript as _build_clarify_transcript,
    build_scope_draft as _build_scope_draft,
    extract_interrupt_text as _extract_interrupt_text,
    format_scope_draft_markdown as _format_scope_draft_markdown,
    restore_worker_result as _restore_worker_result,
    scope_draft_from_payload as _scope_draft_from_payload,
    split_findings as _split_findings,
)
import agent.runtime.deep.support.runtime_support as support
from common.cancellation import check_cancellation as _check_cancel_token
from common.config import settings

logger = logging.getLogger(__name__)


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


def _dedupe_texts(values: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values or []:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _coverage_tokens(text: str) -> list[str]:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return []
    tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", normalized)
    return [token for token in tokens if len(token) >= 2]


def _score_acceptance_match(task: ResearchTask, summary: str) -> float:
    criteria = list(task.acceptance_criteria or [])
    if not criteria:
        return 0.0
    summary_tokens = set(_coverage_tokens(summary))
    if not summary_tokens:
        return 0.0
    matched = 0
    for criterion in criteria:
        tokens = set(_coverage_tokens(criterion))
        if not tokens:
            continue
        overlap = len(summary_tokens & tokens)
        if overlap >= min(2, len(tokens)):
            matched += 1
    return matched / max(1, len(criteria))


def _branch_title(task: ResearchTask) -> str:
    return task.title or task.objective or task.goal or task.query


def _branch_summary_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": result.get("id"),
        "task_id": result.get("task_id"),
        "branch_id": result.get("branch_id"),
        "title": result.get("title"),
        "summary": result.get("summary"),
        "validation_status": result.get("validation_status", "pending"),
        "source_urls": list(result.get("source_urls") or []),
    }


def _normalize_source_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(item.get("title") or item.get("url") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "provider": str(item.get("provider") or "").strip(),
        "published_date": item.get("published_date"),
    }


class LightweightArtifactStore:
    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        self._scope = dict(snapshot.get("scope") or {})
        self._plan = dict(snapshot.get("plan") or {})
        self._evidence_bundles = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("evidence_bundles", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        self._branch_results = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("branch_results", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        self._validation_summaries = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("validation_summaries", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        self._final_report = dict(snapshot.get("final_report") or {})

    def scope(self) -> dict[str, Any]:
        return copy.deepcopy(self._scope)

    def set_scope(self, scope: dict[str, Any]) -> None:
        self._scope = copy.deepcopy(scope)

    def plan(self) -> dict[str, Any]:
        return copy.deepcopy(self._plan)

    def set_plan(self, plan: dict[str, Any]) -> None:
        self._plan = copy.deepcopy(plan)

    def evidence_bundles(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(self._evidence_bundles.values(), key=lambda value: str(value.get("task_id") or ""))
        ]

    def set_evidence_bundle(self, bundle: dict[str, Any]) -> None:
        key = str(bundle.get("task_id") or bundle.get("id") or "").strip()
        if key:
            self._evidence_bundles[key] = copy.deepcopy(bundle)

    def branch_results(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(self._branch_results.values(), key=lambda value: str(value.get("task_id") or ""))
        ]

    def set_branch_result(self, result: dict[str, Any]) -> None:
        key = str(result.get("task_id") or result.get("id") or "").strip()
        if key:
            self._branch_results[key] = copy.deepcopy(result)

    def branch_result(self, task_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._branch_results.get(task_id, {}))

    def validation_summaries(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(
                self._validation_summaries.values(),
                key=lambda value: str(value.get("task_id") or ""),
            )
        ]

    def set_validation_summary(self, summary: dict[str, Any]) -> None:
        key = str(summary.get("task_id") or summary.get("id") or "").strip()
        if key:
            self._validation_summaries[key] = copy.deepcopy(summary)

    def validation_summary(self, task_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._validation_summaries.get(task_id, {}))

    def clear_validation_summary(self, task_id: str) -> None:
        key = str(task_id or "").strip()
        if key:
            self._validation_summaries.pop(key, None)

    def final_report(self) -> dict[str, Any]:
        return copy.deepcopy(self._final_report)

    def set_final_report(self, report: dict[str, Any]) -> None:
        self._final_report = copy.deepcopy(report)

    def passed_branch_results(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.branch_results()
            if str(item.get("validation_status") or "").strip().lower() == "passed"
        ]

    def all_sources(self) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        seen: set[str] = set()
        for bundle in self.evidence_bundles():
            for source in bundle.get("sources", []) or []:
                if not isinstance(source, dict):
                    continue
                normalized = _normalize_source_item(source)
                url = normalized["url"]
                if not url or url in seen:
                    continue
                seen.add(url)
                sources.append(normalized)
        return sources

    def snapshot(self) -> dict[str, Any]:
        return {
            "scope": copy.deepcopy(self._scope),
            "plan": copy.deepcopy(self._plan),
            "evidence_bundles": self.evidence_bundles(),
            "branch_results": self.branch_results(),
            "validation_summaries": self.validation_summaries(),
            "final_report": copy.deepcopy(self._final_report),
        }


@dataclass
class _RuntimeParts:
    shared_state: dict[str, Any]
    task_queue: ResearchTaskQueue
    artifact_store: LightweightArtifactStore
    runtime_state: dict[str, Any]
    agent_runs: list[dict[str, Any]]
    current_iteration: int


class MultiAgentDeepResearchRuntime:
    def __init__(self, state: dict[str, Any], config: dict[str, Any], *, _deps: Any = None):
        self._deps = _resolve_deps(_deps)
        self.state = state if isinstance(state, dict) else {}
        self.config = config if isinstance(config, dict) else {}
        self.cfg = self.config.get("configurable") or {}
        self.topic = str(self.state.get("input") or "").strip() or "Deep Research"
        self.thread_id = str(self.cfg.get("thread_id") or self.state.get("cancel_token_id") or "").strip()
        self.resumed_from_checkpoint = bool(self.cfg.get("resumed_from_checkpoint"))
        snapshot = read_deep_runtime_snapshot(self.state, default_engine="multi_agent")
        snapshot_runtime_state = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}

        self.graph_run_id = str(snapshot_runtime_state.get("graph_run_id") or support._new_id("graph_run"))
        self.graph_attempt = int(snapshot_runtime_state.get("graph_attempt") or 1)
        self.root_branch_id = str(snapshot_runtime_state.get("root_branch_id") or "root").strip() or "root"
        self.start_ts = float(snapshot_runtime_state.get("started_at_ts") or time.time())
        self.parallel_workers = max(1, resolve_parallel_workers(self.config))
        self.max_epochs = max(
            1,
            support._configurable_int(self.config, "deep_research_max_epochs", settings.deep_research_max_epochs),
        )
        self.query_num = max(
            1,
            support._configurable_int(self.config, "deep_research_query_num", settings.deep_research_query_num),
        )
        self.results_per_query = max(
            1,
            support._configurable_int(
                self.config,
                "deep_research_results_per_query",
                settings.deep_research_results_per_query,
            ),
        )
        self.max_seconds = max(
            0.0,
            support._configurable_float(self.config, "deep_research_max_seconds", settings.deep_research_max_seconds),
        )
        self.max_tokens = max(
            0,
            support._configurable_int(self.config, "deep_research_max_tokens", settings.deep_research_max_tokens),
        )
        self.max_searches = max(0, resolve_max_searches(self.config))
        self.task_retry_limit = max(
            1,
            support._configurable_int(self.config, "deep_research_task_retry_limit", 2),
        )
        self.max_clarify_rounds = max(
            1,
            support._configurable_int(self.config, "deep_research_clarify_round_limit", 2),
        )
        self.pause_before_merge = bool(self.cfg.get("deep_research_pause_before_merge"))
        self.allow_interrupts = bool(self.cfg.get("allow_interrupts", False))
        self.provider_profile = support._resolve_provider_profile(self.state)
        self.emitter = None
        if self.thread_id:
            try:
                self.emitter = self._deps.get_emitter_sync(self.thread_id)
            except Exception:
                self.emitter = None

        supervisor_model = support._model_for_task("planning", self.config)
        researcher_model = support._model_for_task("research", self.config)
        reporter_model = support._model_for_task("writing", self.config)
        verifier_model = support._model_for_task("gap_analysis", self.config)

        self.clarifier = self._deps.DeepResearchClarifyAgent(
            self._deps.create_chat_model(supervisor_model, temperature=0),
            self.config,
        )
        self.scope_agent = self._deps.DeepResearchScopeAgent(
            self._deps.create_chat_model(supervisor_model, temperature=0),
            self.config,
        )
        self.supervisor = self._deps.ResearchSupervisor(
            self._deps.create_chat_model(supervisor_model, temperature=0),
            self.config,
        )
        self.researcher = self._deps.ResearchAgent(
            self._deps.create_chat_model(researcher_model, temperature=0),
            self._search_with_tracking,
            self.config,
        )
        self.verifier = self._deps.KnowledgeGapAnalyzer(
            self._deps.create_chat_model(verifier_model, temperature=0),
            self.config,
        )
        self.reporter = self._deps.ResearchReporter(
            self._deps.create_chat_model(reporter_model, temperature=0),
            self.config,
        )

    def _search_with_tracking(self, payload: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(payload.get("query") or "").strip()
        max_results = int(payload.get("max_results") or self.results_per_query)
        results = support._search_query(query, max_results, config, self.provider_profile)
        if query:
            self._emit(
                ToolEventType.SEARCH,
                {
                    "query": query,
                    "provider": "multi_search",
                    "results": support._compact_sources(results, limit=min(len(results), 5)),
                    "count": len(results),
                    "engine": "multi_agent",
                },
            )
        return results

    def _emit(self, event_type: ToolEventType | str, payload: dict[str, Any]) -> None:
        if not self.emitter:
            return
        base_payload = {
            "engine": "multi_agent",
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "resumed_from_checkpoint": self.resumed_from_checkpoint,
        }
        try:
            self.emitter.emit_sync(event_type, {**base_payload, **payload})
        except Exception as exc:
            logger.debug("[deep-runtime] failed to emit %s: %s", event_type, exc)

    def _initial_shared_state(self) -> dict[str, Any]:
        return {
            "scraped_content": copy.deepcopy(self.state.get("scraped_content") or []),
            "summary_notes": list(self.state.get("summary_notes") or []),
            "sources": copy.deepcopy(self.state.get("sources") or []),
            "errors": list(self.state.get("errors") or []),
            "sub_agent_contexts": copy.deepcopy(self.state.get("sub_agent_contexts") or {}),
        }

    def _default_runtime_state(self) -> dict[str, Any]:
        return {
            "engine": "multi_agent",
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "root_branch_id": self.root_branch_id,
            "started_at_ts": self.start_ts,
            "phase": "",
            "next_step": "",
            "active_agent": "clarify",
            "intake_status": "pending",
            "clarify_question": "",
            "clarify_question_history": [],
            "clarify_answer_history": [],
            "clarification_state": {},
            "current_scope_draft": {},
            "approved_scope_draft": {},
            "scope_revision_count": 0,
            "scope_feedback_history": [],
            "last_validation_summary": {},
            "last_verification_summary": {},
            "searches_used": 0,
            "tokens_used": 0,
            "budget_stop_reason": "",
            "terminal_status": "",
            "terminal_reason": "",
        }

    def _unpack(self, graph_state: MultiAgentGraphState) -> _RuntimeParts:
        shared_state = copy.deepcopy(graph_state.get("shared_state") or self._initial_shared_state())
        task_queue = ResearchTaskQueue.from_snapshot(graph_state.get("task_queue"))
        artifact_store = LightweightArtifactStore(graph_state.get("artifact_store"))
        runtime_state = self._default_runtime_state()
        runtime_state.update(copy.deepcopy(graph_state.get("runtime_state") or {}))
        current_iteration = int(
            graph_state.get("current_iteration")
            or runtime_state.get("current_iteration")
            or 0
        )
        runtime_state["current_iteration"] = current_iteration
        agent_runs = copy.deepcopy(graph_state.get("agent_runs") or [])
        return _RuntimeParts(
            shared_state=shared_state,
            task_queue=task_queue,
            artifact_store=artifact_store,
            runtime_state=runtime_state,
            agent_runs=agent_runs,
            current_iteration=current_iteration,
        )

    def _patch(
        self,
        parts: _RuntimeParts,
        *,
        next_step: str,
        pending_worker_tasks: list[dict[str, Any]] | None = None,
        worker_results: list[dict[str, Any]] | None = None,
        final_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parts.runtime_state["phase"] = next_step if next_step != "completed" else "finalize"
        parts.runtime_state["next_step"] = next_step
        return {
            "shared_state": copy.deepcopy(parts.shared_state),
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "root_branch_id": self.root_branch_id,
            "task_queue": parts.task_queue.snapshot(),
            "artifact_store": parts.artifact_store.snapshot(),
            "runtime_state": copy.deepcopy(parts.runtime_state),
            "agent_runs": copy.deepcopy(parts.agent_runs),
            "current_iteration": parts.current_iteration,
            "next_step": next_step,
            "pending_worker_tasks": list(pending_worker_tasks or []),
            "worker_results": list(worker_results or []),
            "final_result": copy.deepcopy(final_result or {}),
        }

    def _next_agent_id(self, role: str, runtime_state: dict[str, Any]) -> str:
        counters = copy.deepcopy(runtime_state.get("role_counters") or {})
        counters[role] = int(counters.get(role, 0) or 0) + 1
        runtime_state["role_counters"] = counters
        return f"{role}-{counters[role]}"

    def _start_agent_run(
        self,
        parts: _RuntimeParts,
        *,
        role: str,
        phase: str,
        task_id: str | None = None,
        branch_id: str | None = None,
        stage: str = "",
        objective_summary: str = "",
        attempt: int = 1,
    ) -> dict[str, Any]:
        agent_id = self._next_agent_id(role, parts.runtime_state)
        record = AgentRunRecord(
            id=support._new_id("agent_run"),
            role=role,  # type: ignore[arg-type]
            phase=phase,
            status="running",
            agent_id=agent_id,
            graph_run_id=self.graph_run_id,
            node_id=phase,
            task_id=task_id,
            branch_id=branch_id,
            stage=stage,
            objective_summary=objective_summary,
            attempt=attempt,
        ).to_dict()
        self._emit(
            ToolEventType.RESEARCH_AGENT_START,
            {
                "agent_id": agent_id,
                "role": role,
                "phase": phase,
                "task_id": task_id,
                "branch_id": branch_id,
                "iteration": max(1, parts.current_iteration or 1),
                "attempt": attempt,
                "stage": stage,
                "objective_summary": objective_summary,
            },
        )
        return record

    def _finish_agent_run(
        self,
        parts: _RuntimeParts,
        record: dict[str, Any],
        *,
        status: str,
        summary: str,
        stage: str = "",
    ) -> None:
        record["status"] = status
        record["ended_at"] = _now_iso()
        record["summary"] = summary[:240]
        if stage:
            record["stage"] = stage
        parts.agent_runs.append(copy.deepcopy(record))
        self._emit(
            ToolEventType.RESEARCH_AGENT_COMPLETE,
            {
                "agent_id": record.get("agent_id"),
                "role": record.get("role"),
                "phase": record.get("phase"),
                "task_id": record.get("task_id"),
                "branch_id": record.get("branch_id"),
                "iteration": max(1, parts.current_iteration or 1),
                "attempt": record.get("attempt", 1),
                "status": status,
                "summary": summary[:240],
                "stage": stage or record.get("stage") or "",
            },
        )

    def _emit_task_update(self, task: ResearchTask, status: str, *, iteration: int, reason: str = "") -> None:
        payload = {
            "task_id": task.id,
            "status": status,
            "title": _branch_title(task),
            "objective_summary": task.objective or task.goal,
            "task_kind": task.task_kind,
            "stage": task.stage,
            "query": task.query,
            "query_hints": list(task.query_hints or []),
            "branch_id": task.branch_id,
            "priority": task.priority,
            "iteration": max(1, iteration),
            "attempt": task.attempts,
        }
        if reason:
            payload["reason"] = reason
        self._emit(ToolEventType.RESEARCH_TASK_UPDATE, payload)
        self._emit(
            ToolEventType.TASK_UPDATE,
            {"id": task.id, "status": status, "title": _branch_title(task)},
        )

    def _emit_artifact_update(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        summary: str,
        status: str = "completed",
        task_id: str | None = None,
        branch_id: str | None = None,
        iteration: int = 1,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "status": status,
            "task_id": task_id,
            "branch_id": branch_id,
            "summary": summary[:180],
            "iteration": max(1, iteration),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        self._emit(ToolEventType.RESEARCH_ARTIFACT_UPDATE, payload)

    def _emit_decision(self, decision_type: str, reason: str, *, iteration: int, extra: dict[str, Any] | None = None):
        payload = {
            "decision_type": decision_type,
            "reason": reason,
            "iteration": max(1, iteration),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        self._emit(ToolEventType.RESEARCH_DECISION, payload)

    def _budget_stop_reason(self, runtime_state: dict[str, Any]) -> str:
        reason = support._budget_stop_reason(
            start_ts=self.start_ts,
            searches_used=int(runtime_state.get("searches_used") or 0),
            tokens_used=int(runtime_state.get("tokens_used") or 0),
            max_seconds=self.max_seconds,
            max_tokens=self.max_tokens,
            max_searches=self.max_searches,
        )
        return str(reason or "")

    def _plan_items_to_tasks(
        self,
        *,
        plan_items: list[dict[str, Any]],
        scope: dict[str, Any],
    ) -> list[ResearchTask]:
        tasks: list[ResearchTask] = []
        for index, item in enumerate(plan_items[: self.query_num], 1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or f"{self.topic} branch {index}").strip()
            objective = str(item.get("objective") or title).strip()
            query_hints = _dedupe_texts(item.get("query_hints") or [objective, self.topic])
            query = str(item.get("query") or (query_hints[0] if query_hints else objective)).strip() or objective
            task = ResearchTask(
                id=support._new_id("task"),
                goal=objective,
                query=query,
                priority=max(1, int(item.get("priority", index) or index)),
                objective=objective,
                task_kind=str(item.get("task_kind") or "branch_research"),
                acceptance_criteria=_dedupe_texts(item.get("acceptance_criteria") or []),
                allowed_tools=_dedupe_texts(item.get("allowed_tools") or ["search", "read", "extract", "synthesize"]),
                input_artifact_ids=[str(scope.get("id") or "")] if scope.get("id") else [],
                query_hints=query_hints,
                title=title,
                aspect=str(item.get("aspect") or f"aspect {index}"),
                branch_id=support._new_id("branch"),
            )
            tasks.append(task)
        return tasks

    def _build_scope_payload(self, draft: ScopeDraft) -> dict[str, Any]:
        return {
            "id": draft.id,
            "version": draft.version,
            "topic": draft.topic,
            "research_goal": draft.research_goal,
            "research_steps": list(draft.research_steps),
            "core_questions": list(draft.core_questions),
            "in_scope": list(draft.in_scope),
            "out_of_scope": list(draft.out_of_scope),
            "constraints": list(draft.constraints),
            "source_preferences": list(draft.source_preferences),
            "deliverable_preferences": list(draft.deliverable_preferences),
            "status": "approved",
            "created_by": draft.created_by,
            "created_at": draft.created_at,
            "updated_at": _now_iso(),
        }

    def _build_plan_artifact(self, scope: dict[str, Any], tasks: list[ResearchTask]) -> dict[str, Any]:
        artifact = ResearchPlanArtifact(
            id=support._new_id("plan"),
            scope_id=str(scope.get("id") or "") or None,
            tasks=[
                {
                    "task_id": task.id,
                    "title": task.title,
                    "objective": task.objective,
                    "query": task.query,
                    "priority": task.priority,
                }
                for task in tasks
            ],
        )
        return artifact.to_dict()

    def _build_evidence_bundle(self, task: ResearchTask, results: list[dict[str, Any]], created_by: str) -> dict[str, Any]:
        sources = support._compact_sources(results, limit=max(3, self.results_per_query))
        documents = []
        passages = []
        for index, item in enumerate(results[: self.results_per_query], 1):
            content = str(
                item.get("raw_excerpt")
                or item.get("summary")
                or item.get("snippet")
                or item.get("content")
                or ""
            ).strip()
            documents.append(
                {
                    "id": support._new_id("document"),
                    "url": str(item.get("url") or "").strip(),
                    "title": str(item.get("title") or item.get("url") or "").strip(),
                    "content": content[:2400],
                    "excerpt": content[:700],
                }
            )
            passages.append(
                {
                    "id": support._new_id("passage"),
                    "url": str(item.get("url") or "").strip(),
                    "text": content[:900],
                    "quote": content[:240],
                    "source_title": str(item.get("title") or item.get("url") or "").strip(),
                    "snippet_hash": f"{task.id}-{index}-{task.attempts}",
                }
            )
        bundle = EvidenceBundle(
            id=support._new_id("bundle"),
            task_id=task.id,
            branch_id=task.branch_id,
            sources=sources,
            documents=documents,
            passages=passages,
            source_count=len(sources),
            created_by=created_by,
        )
        return bundle.to_dict()

    def _build_branch_result(
        self,
        task: ResearchTask,
        bundle: dict[str, Any],
        summary: str,
        created_by: str,
    ) -> dict[str, Any]:
        result = BranchResult(
            id=support._new_id("branch_result"),
            task_id=task.id,
            branch_id=task.branch_id,
            title=_branch_title(task),
            objective=task.objective or task.goal,
            summary=summary,
            key_findings=_split_findings(summary) or [summary],
            source_urls=[str(item.get("url") or "").strip() for item in bundle.get("sources", []) if item.get("url")],
            evidence_bundle_id=str(bundle.get("id") or "") or None,
            created_by=created_by,
        )
        return result.to_dict()

    def _build_validation_summary(
        self,
        task: ResearchTask,
        branch_result: dict[str, Any],
        gap_result: GapAnalysisResult,
    ) -> dict[str, Any]:
        acceptance_score = _score_acceptance_match(task, str(branch_result.get("summary") or ""))
        advisory_only = acceptance_score >= 1.0
        if gap_result.overall_coverage >= 0.6 or advisory_only:
            status = "passed"
        elif task.attempts < self.task_retry_limit and self.max_epochs > 1:
            status = "retry"
        else:
            status = "failed"
        missing_aspects = [gap.aspect for gap in gap_result.gaps]
        notes = gap_result.analysis or ""
        if advisory_only and missing_aspects:
            notes = f"{notes}；acceptance criteria 已满足，缺口作为 advisory hints 记录".strip("；")
        summary = ValidationSummary(
            id=support._new_id("validation"),
            task_id=task.id,
            branch_id=task.branch_id,
            status=status,
            score=float(gap_result.overall_coverage),
            missing_aspects=missing_aspects,
            retry_queries=_dedupe_texts(gap_result.suggested_queries or [task.query]),
            notes=notes,
            status_reason="advisory_only" if advisory_only and missing_aspects else "",
        )
        return summary.to_dict()

    def _aggregate_validation(self, queue: ResearchTaskQueue, store: LightweightArtifactStore) -> dict[str, Any]:
        validations = store.validation_summaries()
        passed = [item for item in validations if item.get("status") == "passed"]
        retry = [item for item in validations if item.get("status") == "retry"]
        failed = [item for item in validations if item.get("status") == "failed"]
        advisory = [
            item
            for item in validations
            if item.get("status") == "passed" and item.get("status_reason") == "advisory_only"
        ]
        return {
            "branch_count": len(store.branch_results()),
            "passed_branch_count": len(passed),
            "retry_branch_count": len(retry),
            "failed_branch_count": len(failed),
            "advisory_gap_count": len(advisory),
            "retry_task_ids": [item.get("task_id") for item in retry if item.get("task_id")],
            "passed_task_ids": [item.get("task_id") for item in passed if item.get("task_id")],
            "validation_summary_ids": [item.get("id") for item in validations if item.get("id")],
            "ready_task_count": queue.ready_count(),
            "source_count": len(store.all_sources()),
        }

    def _quality_summary(self, queue: ResearchTaskQueue, store: LightweightArtifactStore, runtime_state: dict[str, Any]) -> dict[str, Any]:
        aggregate = self._aggregate_validation(queue, store)
        total_tasks = max(1, len(queue.all_tasks()))
        passed_branch_count = int(aggregate.get("passed_branch_count") or 0)
        source_count = len(store.all_sources())
        return {
            "branch_count": int(aggregate.get("branch_count") or 0),
            "passed_branch_count": passed_branch_count,
            "retry_branch_count": int(aggregate.get("retry_branch_count") or 0),
            "failed_branch_count": int(aggregate.get("failed_branch_count") or 0),
            "advisory_gap_count": int(aggregate.get("advisory_gap_count") or 0),
            "source_count": source_count,
            "query_coverage_score": round(passed_branch_count / total_tasks, 3),
            "citation_coverage": round(min(1.0, source_count / max(1, passed_branch_count)), 3),
            "budget_stop_reason": str(runtime_state.get("budget_stop_reason") or ""),
        }

    def _research_topology_snapshot(
        self,
        queue: ResearchTaskQueue,
        store: LightweightArtifactStore,
        runtime_state: dict[str, Any],
    ) -> dict[str, Any]:
        validations_by_task = {
            str(item.get("task_id") or ""): item
            for item in store.validation_summaries()
            if str(item.get("task_id") or "")
        }
        return {
            "id": "deep_research",
            "topic": self.topic,
            "engine": "multi_agent",
            "graph_run_id": self.graph_run_id,
            "phase": str(runtime_state.get("phase") or ""),
            "active_agent": str(runtime_state.get("active_agent") or ""),
            "children": [
                {
                    "id": task.id,
                    "title": _branch_title(task),
                    "query": task.query,
                    "status": task.status,
                    "stage": task.stage,
                    "attempts": task.attempts,
                    "branch_id": task.branch_id,
                    "validation_status": str(
                        validations_by_task.get(task.id, {}).get("status") or "pending"
                    ),
                }
                for task in queue.all_tasks()
            ],
        }

    def _initial_next_step(
        self,
        task_queue_snapshot: dict[str, Any],
        artifact_store_snapshot: dict[str, Any],
        runtime_state_snapshot: dict[str, Any],
    ) -> str:
        existing = str(runtime_state_snapshot.get("next_step") or "").strip().lower()
        if existing == "completed":
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
        stats = task_queue_snapshot.get("stats", {}) if isinstance(task_queue_snapshot, dict) else {}
        if int(stats.get("total", 0) or 0) == 0:
            return "supervisor_plan"
        if int(stats.get("ready", 0) or 0) > 0 or int(stats.get("in_progress", 0) or 0) > 0:
            return "dispatch"
        validations = artifact_store_snapshot.get("validation_summaries", [])
        if not validations:
            return "verify"
        passed = [
            item
            for item in validations
            if isinstance(item, dict) and str(item.get("status") or "") == "passed"
        ]
        if passed:
            return "report"
        return "supervisor_decide"

    def build_initial_graph_state(self) -> MultiAgentGraphState:
        snapshot = read_deep_runtime_snapshot(self.state, default_engine="multi_agent")
        runtime_state = self._default_runtime_state()
        runtime_state.update(copy.deepcopy(snapshot.get("runtime_state") or {}))
        task_queue_snapshot = snapshot.get("task_queue") if isinstance(snapshot.get("task_queue"), dict) else {}
        artifact_store_snapshot = snapshot.get("artifact_store") if isinstance(snapshot.get("artifact_store"), dict) else {}
        next_step = self._initial_next_step(task_queue_snapshot, artifact_store_snapshot, runtime_state)
        return {
            "shared_state": self._initial_shared_state(),
            "topic": self.topic,
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "root_branch_id": self.root_branch_id,
            "task_queue": task_queue_snapshot,
            "artifact_store": artifact_store_snapshot,
            "runtime_state": runtime_state,
            "agent_runs": list(snapshot.get("agent_runs") or []),
            "current_iteration": int(runtime_state.get("current_iteration") or 0),
            "planning_mode": "",
            "next_step": next_step,
            "latest_gap_result": {},
            "latest_decision": {},
            "latest_verification_summary": copy.deepcopy(runtime_state.get("last_validation_summary") or {}),
            "pending_worker_tasks": [],
            "worker_results": [],
            "final_result": {},
        }

    def _bootstrap_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        token_id = self.state.get("cancel_token_id")
        if token_id:
            _check_cancel_token(token_id)
        for task in parts.task_queue.requeue_in_progress(reason="checkpoint_resume"):
            self._emit_task_update(task, task.status, iteration=max(1, parts.current_iteration or 1), reason="checkpoint_resume")
        next_step = self._initial_next_step(
            parts.task_queue.snapshot(),
            parts.artifact_store.snapshot(),
            parts.runtime_state,
        )
        return self._patch(parts, next_step=next_step)

    def _route_after_bootstrap(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "clarify").strip().lower()
        if next_step in {
            "clarify",
            "scope",
            "scope_review",
            "research_brief",
            "supervisor_plan",
            "dispatch",
            "verify",
            "supervisor_decide",
            "outline_gate",
            "report",
            "finalize",
        }:
            return next_step
        return "clarify"

    def _clarify_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "clarify"
        record = self._start_agent_run(parts, role="clarify", phase="clarify", attempt=self.graph_attempt)
        clarify_answers = list(parts.runtime_state.get("clarify_answer_history") or [])
        clarify_history = _build_clarify_transcript(
            list(parts.runtime_state.get("clarify_question_history") or []),
            clarify_answers,
        )
        result = self.clarifier.assess_intake(
            self.topic,
            clarify_answers=clarify_answers,
            clarify_history=clarify_history,
        )
        clarification_state = copy.deepcopy(result or {})
        status = str(clarification_state.get("status") or "ready_for_scope").strip().lower()
        question = str(clarification_state.get("follow_up_question") or "").strip()
        parts.runtime_state["clarification_state"] = clarification_state

        if status == "needs_user_input" and question and self.allow_interrupts and not clarify_answers:
            prompt = {
                "checkpoint": "deep_research_clarify",
                "message": question,
                "question": question,
                "graph_run_id": self.graph_run_id,
                "graph_attempt": self.graph_attempt,
            }
            self._emit_decision("clarify_required", question, iteration=max(1, parts.current_iteration or 1))
            self._finish_agent_run(parts, record, status="completed", summary=question)
            updated = interrupt(prompt)
            answer = _extract_interrupt_text(updated, keys=("clarify_answer", "answer", "content"))
            if not answer:
                raise ValueError("deep_research clarify resume requires non-empty clarify_answer")
            parts.runtime_state["clarify_question_history"] = list(parts.runtime_state.get("clarify_question_history") or []) + [question]
            parts.runtime_state["clarify_answer_history"] = list(parts.runtime_state.get("clarify_answer_history") or []) + [answer]
            parts.runtime_state["clarify_question"] = question
            parts.runtime_state["intake_status"] = "pending"
            return self._patch(parts, next_step="clarify")

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
        self._emit_decision("scope_ready", reason, iteration=max(1, parts.current_iteration or 1))
        self._finish_agent_run(parts, record, status="completed", summary=reason)
        return self._patch(parts, next_step="scope")

    def _route_after_clarify(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "scope").strip().lower()
        if next_step in {"clarify", "scope"}:
            return next_step
        return "scope"

    def _scope_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "scope"
        record = self._start_agent_run(parts, role="scope", phase="scope", attempt=self.graph_attempt)
        clarification_state = copy.deepcopy(parts.runtime_state.get("clarification_state") or {})
        current_scope_payload = copy.deepcopy(parts.runtime_state.get("current_scope_draft") or {})
        pending_feedback = ""
        feedback_history = list(parts.runtime_state.get("scope_feedback_history") or [])
        if feedback_history:
            pending_feedback = str(feedback_history[-1].get("feedback") or "").strip()

        scope_payload = self.scope_agent.create_scope(
            self.topic,
            clarification_state=clarification_state,
            previous_scope=current_scope_payload if pending_feedback else {},
            scope_feedback=pending_feedback,
            clarify_transcript=_build_clarify_transcript(
                list(parts.runtime_state.get("clarify_question_history") or []),
                list(parts.runtime_state.get("clarify_answer_history") or []),
            ),
        )
        existing_scope = _scope_draft_from_payload(current_scope_payload)
        next_version = existing_scope.version + 1 if existing_scope and pending_feedback else 1
        scope_draft = _build_scope_draft(
            topic=self.topic,
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
        self._emit_decision(
            "scope_revision_requested" if pending_feedback else "scope_ready",
            pending_feedback or "scope ready for review",
            iteration=max(1, parts.current_iteration or 1),
            extra={"scope_version": scope_draft.version},
        )
        self._emit_artifact_update(
            artifact_id=scope_draft.id,
            artifact_type="scope_draft",
            summary=scope_draft.research_goal,
            status=scope_draft.status,
            iteration=max(1, parts.current_iteration or 1),
            extra={"content": _format_scope_draft_markdown(scope_draft)},
        )
        self._finish_agent_run(parts, record, status="completed", summary=scope_draft.research_goal)
        return self._patch(parts, next_step="scope_review")

    def _scope_review_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "scope"
        scope_draft = _scope_draft_from_payload(parts.runtime_state.get("current_scope_draft"))
        if not scope_draft:
            return self._patch(parts, next_step="scope")

        if not self.allow_interrupts:
            approved_payload = scope_draft.to_dict()
            approved_payload["status"] = "approved"
            parts.runtime_state["approved_scope_draft"] = approved_payload
            parts.runtime_state["intake_status"] = "scope_approved"
            self._emit_decision("scope_approved", "interrupts disabled; auto approve", iteration=max(1, parts.current_iteration or 1))
            return self._patch(parts, next_step="research_brief")

        prompt = {
            "checkpoint": "deep_research_scope_review",
            "message": "Review the proposed Deep Research scope.",
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "scope_draft": scope_draft.to_dict(),
            "scope_version": scope_draft.version,
            "scope_revision_count": int(parts.runtime_state.get("scope_revision_count", 0) or 0),
            "content": _format_scope_draft_markdown(scope_draft),
            "available_actions": ["approve_scope", "revise_scope"],
        }
        updated = interrupt(prompt)
        action = str((updated or {}).get("action") or "").strip().lower() if isinstance(updated, dict) else ""
        if not action:
            action = (
                "revise_scope"
                if _extract_interrupt_text(updated, keys=("scope_feedback", "feedback", "content"))
                else "approve_scope"
            )
        if action == "approve_scope":
            approved_payload = scope_draft.to_dict()
            approved_payload["status"] = "approved"
            parts.runtime_state["approved_scope_draft"] = approved_payload
            parts.runtime_state["intake_status"] = "scope_approved"
            self._emit_decision("scope_approved", "user approved the current scope draft", iteration=max(1, parts.current_iteration or 1))
            return self._patch(parts, next_step="research_brief")

        feedback = _extract_interrupt_text(updated, keys=("scope_feedback", "feedback", "content"))
        if not feedback:
            raise ValueError("revise_scope requires non-empty scope_feedback")
        history = list(parts.runtime_state.get("scope_feedback_history") or [])
        history.append({"scope_version": scope_draft.version, "feedback": feedback, "at": _now_iso()})
        parts.runtime_state["scope_feedback_history"] = history
        parts.runtime_state["intake_status"] = "scope_revision_requested"
        self._emit_decision("scope_revision_requested", feedback, iteration=max(1, parts.current_iteration or 1))
        return self._patch(parts, next_step="scope")

    def _route_after_scope_review(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "research_brief").strip().lower()
        if next_step in {"scope", "research_brief"}:
            return next_step
        return "research_brief"

    def _research_brief_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        approved_scope = copy.deepcopy(parts.runtime_state.get("approved_scope_draft") or {})
        if not approved_scope:
            return self._patch(parts, next_step="scope_review")
        scope = approved_scope
        scope["status"] = "approved"
        parts.artifact_store.set_scope(scope)
        parts.runtime_state["active_agent"] = "scope"
        parts.runtime_state["scope_id"] = str(scope.get("id") or "")
        self._emit_artifact_update(
            artifact_id=str(scope.get("id") or support._new_id("scope")),
            artifact_type="scope",
            summary=str(scope.get("research_goal") or self.topic),
            status="completed",
            iteration=max(1, parts.current_iteration or 1),
        )
        self._emit_decision("research_brief_ready", "approved scope normalized into runtime scope", iteration=max(1, parts.current_iteration or 1))
        return self._patch(parts, next_step="supervisor_plan")

    def _supervisor_plan_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        approved_scope = copy.deepcopy(parts.runtime_state.get("approved_scope_draft") or {})
        if not approved_scope:
            return self._patch(parts, next_step="scope_review")
        scope = parts.artifact_store.scope()
        if not scope:
            return self._patch(parts, next_step="research_brief")
        if parts.task_queue.snapshot().get("stats", {}).get("total", 0):
            if parts.task_queue.ready_count() > 0:
                return self._patch(parts, next_step="dispatch")
            return self._patch(parts, next_step="verify")

        parts.runtime_state["active_agent"] = "supervisor"
        record = self._start_agent_run(parts, role="supervisor", phase="supervisor_plan", attempt=self.graph_attempt)
        plan_items = self.supervisor.create_plan(
            self.topic,
            num_queries=self.query_num,
            existing_knowledge="\n".join(parts.shared_state.get("summary_notes", [])),
            existing_queries=[],
            approved_scope=scope,
        )
        tasks = self._plan_items_to_tasks(plan_items=plan_items, scope=scope)
        if not tasks:
            parts.runtime_state["terminal_status"] = "blocked"
            parts.runtime_state["terminal_reason"] = "research plan produced no executable tasks"
            self._finish_agent_run(parts, record, status="completed", summary=parts.runtime_state["terminal_reason"])
            return self._patch(parts, next_step="finalize")

        parts.task_queue.enqueue(tasks)
        plan_artifact = self._build_plan_artifact(scope, tasks)
        parts.artifact_store.set_plan(plan_artifact)
        parts.runtime_state["plan_id"] = str(plan_artifact.get("id") or "")
        parts.runtime_state["supervisor_phase"] = "initial_plan"
        self._emit_artifact_update(
            artifact_id=str(plan_artifact.get("id") or support._new_id("plan")),
            artifact_type="plan",
            summary=f"generated {len(tasks)} branch tasks",
            iteration=max(1, parts.current_iteration or 1),
        )
        for task in tasks:
            self._emit_task_update(task, task.status, iteration=max(1, parts.current_iteration or 1))
        self._emit_decision("supervisor_plan", f"generated {len(tasks)} branch tasks", iteration=max(1, parts.current_iteration or 1))
        self._finish_agent_run(parts, record, status="completed", summary=f"generated {len(tasks)} tasks")
        return self._patch(parts, next_step="dispatch")

    def _route_after_supervisor_plan(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "dispatch").strip().lower()
        if next_step in {"scope_review", "research_brief", "dispatch", "finalize", "verify"}:
            return next_step
        return "dispatch"

    def _dispatch_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        budget_stop_reason = self._budget_stop_reason(parts.runtime_state)
        if budget_stop_reason:
            parts.runtime_state["budget_stop_reason"] = budget_stop_reason
            self._emit_decision("budget_stop", budget_stop_reason, iteration=max(1, parts.current_iteration or 1))
            return self._patch(parts, next_step="verify")

        if parts.task_queue.ready_count() == 0:
            return self._patch(parts, next_step="verify")

        parts.current_iteration += 1
        parts.runtime_state["current_iteration"] = parts.current_iteration
        claimed = parts.task_queue.claim_ready_tasks(
            limit=self.parallel_workers,
            agent_ids=[self._next_agent_id("researcher", parts.runtime_state) for _ in range(self.parallel_workers)],
        )
        for task in claimed:
            self._emit_task_update(task, "in_progress", iteration=parts.current_iteration)
        self._emit_decision("research", "dispatch ready branch tasks", iteration=parts.current_iteration)
        return self._patch(
            parts,
            next_step="verify",
            pending_worker_tasks=[task.to_dict() for task in claimed],
            worker_results=[{"__reset__": True}],
        )

    def _route_after_dispatch(self, graph_state: MultiAgentGraphState) -> list[Send] | str:
        payloads = graph_state.get("pending_worker_tasks") or []
        if not payloads:
            return "verify"
        return [Send("researcher", {"worker_task": payload}) for payload in payloads]

    def _researcher_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        payload = graph_state.get("worker_task") or {}
        task_payload = payload.get("task") if isinstance(payload, dict) else None
        task = ResearchTask(**task_payload) if isinstance(task_payload, dict) else ResearchTask(**payload)
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        record = self._start_agent_run(
            parts,
            role="researcher",
            phase="researcher",
            task_id=task.id,
            branch_id=task.branch_id,
            stage="search",
            objective_summary=task.objective or task.goal,
            attempt=max(1, task.attempts),
        )
        try:
            self._emit_task_update(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="search")
            queries = _dedupe_texts(task.query_hints or [task.query])
            results = self.researcher.execute_queries(queries, max_results_per_query=self.results_per_query)
            if not results:
                raise RuntimeError("branch agent returned no evidence")
            self._emit_task_update(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="synthesize")
            summary = self.researcher.summarize_findings(
                self.topic,
                results,
                existing_summary="\n".join(parts.shared_state.get("summary_notes", [])[:6]),
            ).strip() or f"未能为 {_branch_title(task)} 形成有效摘要。"
            bundle = self._build_evidence_bundle(task, results, str(record.get("agent_id") or "researcher"))
            branch_result = self._build_branch_result(task, bundle, summary, str(record.get("agent_id") or "researcher"))
            self._finish_agent_run(parts, record, status="completed", summary=summary, stage="synthesize")
            return {
                "worker_results": [
                    {
                        "task": task.to_dict(),
                        "result_status": "completed",
                        "branch_result": branch_result,
                        "evidence_bundle": bundle,
                        "raw_results": copy.deepcopy(results),
                        "tokens_used": support._estimate_tokens_from_results(results) + support._estimate_tokens_from_text(summary),
                        "searches_used": len(queries),
                        "agent_run": copy.deepcopy(record),
                    }
                ]
            }
        except Exception as exc:
            self._finish_agent_run(parts, record, status="failed", summary=str(exc), stage=task.stage or "search")
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

    def _merge_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        payloads = [item for item in graph_state.get("worker_results") or [] if isinstance(item, dict) and not item.get("__reset__")]
        if self.pause_before_merge and payloads:
            interrupt(
                {
                    "checkpoint": "deep_research_merge",
                    "graph_run_id": self.graph_run_id,
                    "iteration": parts.current_iteration,
                    "pending_workers": len(payloads),
                }
            )
        for payload in payloads:
            agent_run = payload.get("agent_run")
            if isinstance(agent_run, dict):
                parts.agent_runs.append(copy.deepcopy(agent_run))
            parts.runtime_state["searches_used"] = int(parts.runtime_state.get("searches_used") or 0) + int(payload.get("searches_used") or 0)
            parts.runtime_state["tokens_used"] = int(parts.runtime_state.get("tokens_used") or 0) + int(payload.get("tokens_used") or 0)
            task = ResearchTask(**payload["task"])
            if payload.get("result_status") == "completed":
                bundle = copy.deepcopy(payload.get("evidence_bundle") or {})
                branch_result = copy.deepcopy(payload.get("branch_result") or {})
                parts.artifact_store.set_evidence_bundle(bundle)
                parts.artifact_store.set_branch_result(branch_result)
                updated_task = parts.task_queue.update_status(task.id, "completed")
                if updated_task:
                    self._emit_task_update(updated_task, "completed", iteration=max(1, parts.current_iteration or 1))
                parts.shared_state["summary_notes"] = list(parts.shared_state.get("summary_notes") or []) + [str(branch_result.get("summary") or "")]
                parts.shared_state["sources"] = list(parts.shared_state.get("sources") or []) + list(bundle.get("sources") or [])
                parts.shared_state["scraped_content"] = list(parts.shared_state.get("scraped_content") or []) + [
                    {
                        "task_id": task.id,
                        "query": task.query,
                        "results": copy.deepcopy(payload.get("raw_results") or []),
                        "summary": branch_result.get("summary"),
                    }
                ]
                self._emit_artifact_update(
                    artifact_id=str(bundle.get("id") or support._new_id("bundle")),
                    artifact_type="evidence_bundle",
                    summary=f"{len(bundle.get('sources', []))} sources",
                    task_id=task.id,
                    branch_id=task.branch_id,
                    iteration=max(1, parts.current_iteration or 1),
                )
                self._emit_artifact_update(
                    artifact_id=str(branch_result.get("id") or support._new_id("branch_result")),
                    artifact_type="branch_result",
                    summary=str(branch_result.get("summary") or ""),
                    task_id=task.id,
                    branch_id=task.branch_id,
                    iteration=max(1, parts.current_iteration or 1),
                )
            else:
                reason = str(payload.get("error") or "researcher returned no results")
                failed_task = parts.task_queue.update_stage(task.id, task.stage or "search", status="failed", reason=reason)
                if failed_task:
                    self._emit_task_update(failed_task, "failed", iteration=max(1, parts.current_iteration or 1), reason=reason)
                if task.attempts < self.task_retry_limit and not parts.runtime_state.get("budget_stop_reason"):
                    retry_task = parts.task_queue.update_stage(task.id, "planned", status="ready", reason=reason)
                    if retry_task:
                        self._emit_task_update(retry_task, "ready", iteration=max(1, parts.current_iteration or 1), reason=reason)
                parts.shared_state["errors"] = list(parts.shared_state.get("errors") or []) + [reason]
        return self._patch(
            parts,
            next_step="verify",
            pending_worker_tasks=[],
            worker_results=[{"__reset__": True}],
        )

    def _verify_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        record = self._start_agent_run(parts, role="verifier", phase="verify", attempt=self.graph_attempt)
        task_map = {task.id: task for task in parts.task_queue.all_tasks()}
        for result in parts.artifact_store.branch_results():
            task_id = str(result.get("task_id") or "")
            if not task_id or parts.artifact_store.validation_summary(task_id):
                continue
            task = task_map.get(task_id)
            if task is None:
                continue
            gap_result = self.verifier.analyze(
                topic=task.objective or self.topic,
                executed_queries=_dedupe_texts(task.query_hints or [task.query]),
                collected_knowledge=str(result.get("summary") or ""),
            )
            validation_summary = self._build_validation_summary(task, result, gap_result)
            parts.artifact_store.set_validation_summary(validation_summary)
            result["validation_summary_id"] = validation_summary.get("id")
            result["validation_status"] = validation_summary.get("status")
            parts.artifact_store.set_branch_result(result)
            self._emit_artifact_update(
                artifact_id=str(validation_summary.get("id") or support._new_id("validation")),
                artifact_type="validation_summary",
                summary=str(validation_summary.get("notes") or validation_summary.get("status") or ""),
                task_id=task.id,
                branch_id=task.branch_id,
                iteration=max(1, parts.current_iteration or 1),
                extra={
                    "validation_status": validation_summary.get("status"),
                    "retry_queries": list(validation_summary.get("retry_queries") or []),
                },
            )
        aggregate = self._aggregate_validation(parts.task_queue, parts.artifact_store)
        parts.runtime_state["last_validation_summary"] = aggregate
        parts.runtime_state["last_verification_summary"] = copy.deepcopy(aggregate)
        decision_type = "verification_passed" if aggregate["passed_branch_count"] else "verification_retry_requested"
        self._emit_decision(decision_type, "validation updated", iteration=max(1, parts.current_iteration or 1), extra=aggregate)
        self._emit(ToolEventType.QUALITY_UPDATE, self._quality_summary(parts.task_queue, parts.artifact_store, parts.runtime_state))
        self._finish_agent_run(parts, record, status="completed", summary="validation updated")
        return self._patch(parts, next_step="supervisor_decide")

    def _supervisor_decide_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        aggregate = copy.deepcopy(parts.runtime_state.get("last_validation_summary") or {})
        retry_task_ids = _dedupe_texts(aggregate.get("retry_task_ids") or [])
        passed_branch_count = int(aggregate.get("passed_branch_count") or 0)
        budget_stop_reason = self._budget_stop_reason(parts.runtime_state)
        previous_budget_stop_reason = str(parts.runtime_state.get("budget_stop_reason") or "")
        parts.runtime_state["budget_stop_reason"] = budget_stop_reason
        if budget_stop_reason and budget_stop_reason != previous_budget_stop_reason:
            self._emit_decision("budget_stop", budget_stop_reason, iteration=max(1, parts.current_iteration or 1))

        if retry_task_ids and parts.current_iteration < self.max_epochs and not budget_stop_reason:
            for task_id in retry_task_ids:
                task = parts.task_queue.get(task_id)
                if task is None:
                    continue
                validation = parts.artifact_store.validation_summary(task_id)
                parts.artifact_store.clear_validation_summary(task_id)
                retry_queries = _dedupe_texts(validation.get("retry_queries") or [])
                if retry_queries:
                    task.query_hints = retry_queries
                    task.query = retry_queries[0]
                parts.task_queue.enqueue([task])
                updated = parts.task_queue.update_stage(task.id, "planned", status="ready", reason=str(validation.get("notes") or "retry requested"))
                if updated:
                    self._emit_task_update(updated, "ready", iteration=max(1, parts.current_iteration or 1), reason="validation retry")
            self._emit_decision("retry_branch", "retry requested by validation", iteration=max(1, parts.current_iteration or 1), extra={"retry_task_ids": retry_task_ids})
            return self._patch(parts, next_step="dispatch")

        if parts.task_queue.ready_count() > 0 and parts.current_iteration < self.max_epochs and not budget_stop_reason:
            return self._patch(parts, next_step="dispatch")

        if passed_branch_count > 0:
            self._emit_decision("report", "validated branch results are sufficient", iteration=max(1, parts.current_iteration or 1))
            return self._patch(parts, next_step="outline_gate")

        parts.runtime_state["terminal_status"] = "blocked"
        parts.runtime_state["terminal_reason"] = budget_stop_reason or "no validated branch results available"
        self._emit_decision("stop", parts.runtime_state["terminal_reason"], iteration=max(1, parts.current_iteration or 1))
        return self._patch(parts, next_step="finalize")

    def _route_after_supervisor_decide(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "report").strip().lower()
        if next_step in {"dispatch", "outline_gate", "report", "finalize"}:
            return next_step
        return "report"

    def _outline_gate_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        passed = parts.artifact_store.passed_branch_results()
        if not passed:
            parts.runtime_state["terminal_status"] = "blocked"
            parts.runtime_state["terminal_reason"] = "no passed branch results available for report"
            return self._patch(parts, next_step="finalize")
        self._emit_decision("outline_ready", "branch results ready for final report", iteration=max(1, parts.current_iteration or 1))
        return self._patch(parts, next_step="report")

    def _report_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        record = self._start_agent_run(parts, role="reporter", phase="report", attempt=self.graph_attempt)
        passed_results = parts.artifact_store.passed_branch_results()
        if not passed_results:
            self._finish_agent_run(parts, record, status="failed", summary="no passed branch results")
            return self._patch(parts, next_step="finalize")

        sources = [
            ReportSource(
                url=str(item.get("url") or ""),
                title=str(item.get("title") or item.get("url") or ""),
                provider=str(item.get("provider") or ""),
                published_date=item.get("published_date"),
            )
            for item in parts.artifact_store.all_sources()
            if str(item.get("url") or "").strip()
        ]
        sections = [
            ReportSectionContext(
                title=str(item.get("title") or "研究分支"),
                summary=str(item.get("summary") or ""),
                findings=list(item.get("key_findings") or []),
                citation_urls=list(item.get("source_urls") or []),
            )
            for item in passed_results
        ]
        report_context = ReportContext(topic=self.topic, sections=sections, sources=sources)
        report_markdown = self.reporter.generate_report(report_context)
        normalized_report, citation_urls = self.reporter.normalize_report(report_markdown, sources, title=self.topic)
        executive_summary = self.reporter.generate_executive_summary(normalized_report, self.topic)
        final_report = FinalReportArtifact(
            id=support._new_id("final_report"),
            report_markdown=normalized_report,
            executive_summary=executive_summary,
            citation_urls=citation_urls,
            created_by=str(record.get("agent_id") or "reporter"),
        ).to_dict()
        parts.artifact_store.set_final_report(final_report)
        self._emit_artifact_update(
            artifact_id=final_report["id"],
            artifact_type="final_report",
            summary=executive_summary or normalized_report[:180],
            iteration=max(1, parts.current_iteration or 1),
        )
        self._finish_agent_run(parts, record, status="completed", summary=executive_summary or "final report ready")
        return self._patch(parts, next_step="finalize")

    def _finalize_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        final_artifact = parts.artifact_store.final_report()
        final_report = str(final_artifact.get("report_markdown") or "")
        if not final_report and parts.runtime_state.get("terminal_reason"):
            final_report = f"Deep Research 未能完成：{parts.runtime_state['terminal_reason']}"
        quality_summary = self._quality_summary(parts.task_queue, parts.artifact_store, parts.runtime_state)
        research_topology = self._research_topology_snapshot(parts.task_queue, parts.artifact_store, parts.runtime_state)
        deep_research_artifacts = build_public_deep_research_artifacts(
            task_queue=parts.task_queue.snapshot(),
            artifact_store=parts.artifact_store.snapshot(),
            research_topology=research_topology,
            quality_summary=quality_summary,
            runtime_state=parts.runtime_state,
            mode="multi_agent",
            engine="multi_agent",
        )
        self._emit(
            ToolEventType.RESEARCH_NODE_COMPLETE,
            {
                "node_id": "deep_research_multi_agent",
                "summary": str(final_artifact.get("executive_summary") or final_report[:1200]),
                "sources": deep_research_artifacts.get("sources", []),
                "quality": quality_summary,
                "branch_id": self.root_branch_id,
                "iteration": parts.current_iteration,
            },
        )
        parts.runtime_state["next_step"] = "completed"
        result = {
            "deep_runtime": build_deep_runtime_snapshot(
                engine="multi_agent",
                task_queue=parts.task_queue.snapshot(),
                artifact_store=parts.artifact_store.snapshot(),
                runtime_state=parts.runtime_state,
                agent_runs=parts.agent_runs,
            ),
            "research_plan": [task.query for task in parts.task_queue.all_tasks()],
            "scraped_content": copy.deepcopy(parts.shared_state.get("scraped_content") or []),
            "draft_report": final_report,
            "final_report": final_report,
            "quality_summary": quality_summary,
            "sources": copy.deepcopy(deep_research_artifacts.get("sources") or []),
            "deep_research_artifacts": deep_research_artifacts,
            "research_topology": research_topology,
            "messages": [AIMessage(content=final_report)] if final_report else [],
            "is_complete": True,
            "budget_stop_reason": parts.runtime_state.get("budget_stop_reason", ""),
            "terminal_status": parts.runtime_state.get("terminal_status", ""),
            "terminal_reason": parts.runtime_state.get("terminal_reason", ""),
            "errors": list(parts.shared_state.get("errors") or []),
            "sub_agent_contexts": copy.deepcopy(parts.shared_state.get("sub_agent_contexts") or {}),
        }
        return self._patch(parts, next_step="completed", final_result=result)

    def build_graph(self, *, checkpointer: Any = None, interrupt_before: Any = None):
        workflow = StateGraph(MultiAgentGraphState)
        workflow.add_node("bootstrap", self._bootstrap_node)
        workflow.add_node("clarify", self._clarify_node)
        workflow.add_node("scope", self._scope_node)
        workflow.add_node("scope_review", self._scope_review_node)
        workflow.add_node("research_brief", self._research_brief_node)
        workflow.add_node("supervisor_plan", self._supervisor_plan_node)
        workflow.add_node("dispatch", self._dispatch_node)
        workflow.add_node("researcher", self._researcher_node)
        workflow.add_node("merge", self._merge_node)
        workflow.add_node("verify", self._verify_node)
        workflow.add_node("supervisor_decide", self._supervisor_decide_node)
        workflow.add_node("outline_gate", self._outline_gate_node)
        workflow.add_node("report", self._report_node)
        workflow.add_node("finalize", self._finalize_node)

        workflow.set_entry_point("bootstrap")
        workflow.add_conditional_edges(
            "bootstrap",
            self._route_after_bootstrap,
            [
                "clarify",
                "scope",
                "scope_review",
                "research_brief",
                "supervisor_plan",
                "dispatch",
                "verify",
                "supervisor_decide",
                "outline_gate",
                "report",
                "finalize",
            ],
        )
        workflow.add_conditional_edges("clarify", self._route_after_clarify, ["clarify", "scope"])
        workflow.add_edge("scope", "scope_review")
        workflow.add_conditional_edges("scope_review", self._route_after_scope_review, ["scope", "research_brief"])
        workflow.add_edge("research_brief", "supervisor_plan")
        workflow.add_conditional_edges(
            "supervisor_plan",
            self._route_after_supervisor_plan,
            ["scope_review", "research_brief", "dispatch", "verify", "finalize"],
        )
        workflow.add_conditional_edges("dispatch", self._route_after_dispatch, ["researcher", "verify"])
        workflow.add_edge("researcher", "merge")
        workflow.add_edge("merge", "verify")
        workflow.add_edge("verify", "supervisor_decide")
        workflow.add_conditional_edges(
            "supervisor_decide",
            self._route_after_supervisor_decide,
            ["dispatch", "outline_gate", "report", "finalize"],
        )
        workflow.add_edge("outline_gate", "report")
        workflow.add_edge("report", "finalize")
        workflow.add_edge("finalize", END)
        return workflow.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)

    def run(self) -> dict[str, Any]:
        graph = self.build_graph()
        output = graph.invoke(self.build_initial_graph_state(), self.config)
        if isinstance(output, dict) and isinstance(output.get("final_result"), dict):
            return output["final_result"]
        return output if isinstance(output, dict) else {}


def create_multi_agent_deep_research_graph(
    state: dict[str, Any],
    config: dict[str, Any],
    *,
    checkpointer: Any = None,
    interrupt_before: Any = None,
):
    runtime = MultiAgentDeepResearchRuntime(state, config)
    return runtime.build_graph(checkpointer=checkpointer, interrupt_before=interrupt_before)


def run_multi_agent_deep_research(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    runtime = MultiAgentDeepResearchRuntime(state, config)
    return runtime.run()


__all__ = [
    "GapAnalysisResult",
    "MultiAgentDeepResearchRuntime",
    "_format_scope_draft_markdown",
    "_restore_worker_result",
    "create_multi_agent_deep_research_graph",
    "run_multi_agent_deep_research",
]
