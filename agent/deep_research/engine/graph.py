"""
Lightweight LangGraph-backed Deep Research runtime.

This module keeps the public entrypoints stable while dramatically reducing the
number of persisted runtime artifacts. The loop is intentionally compact:

clarify -> scope -> scope_review -> research_brief -> outline_plan
-> dispatch -> researcher/revisor -> merge -> reviewer -> supervisor_decide
-> outline_gate -> report -> finalize
"""

from __future__ import annotations

import copy
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.types import Send, interrupt

import agent.deep_research.branch_research.budgets as budgets
import agent.deep_research.branch_research.search_runtime as search_runtime
from agent.contracts.events import ToolEventType
from agent.contracts.events import get_emitter_sync as get_emitter_sync
from agent.deep_research.agents import (
    DeepResearchClarifyAgent as DeepResearchClarifyAgent,
)
from agent.deep_research.agents import (
    DeepResearchScopeAgent as DeepResearchScopeAgent,
)
from agent.deep_research.agents import (
    ResearchAgent as ResearchAgent,
)
from agent.deep_research.agents import (
    ResearchReporter as ResearchReporter,
)
from agent.deep_research.agents import (
    ResearchSupervisor as ResearchSupervisor,
)
from agent.deep_research.agents.reporter import (
    ReportSectionContext,
)
from agent.deep_research.config import resolve_max_searches, resolve_parallel_workers
from agent.deep_research.engine import (
    completion_flow,
    intake_flow,
    merge_flow,
    planning,
    planning_flow,
    review_cycle,
    run_tracking,
    runtime_artifacts,
    runtime_context,
    section_review,
    worker_flow,
)
from agent.deep_research.engine.artifact_store import LightweightArtifactStore
from agent.deep_research.engine.text_analysis import _dedupe_texts
from agent.deep_research.engine.workflow_state import (
    MultiAgentGraphState,
)
from agent.deep_research.ids import _new_id
from agent.deep_research.intake.scope_draft import (
    build_clarify_transcript as _build_clarify_transcript,
)
from agent.deep_research.intake.scope_draft import (
    build_scope_draft as _build_scope_draft,
)
from agent.deep_research.intake.scope_draft import (
    extract_interrupt_text as _extract_interrupt_text,
)
from agent.deep_research.intake.scope_draft import (
    format_scope_draft_markdown as _format_scope_draft_markdown,
)
from agent.deep_research.intake.scope_draft import (
    scope_draft_from_payload as _scope_draft_from_payload,
)
from agent.deep_research.schema import ResearchTask, _now_iso
from agent.deep_research.state import read_deep_runtime_snapshot
from agent.deep_research.store import ResearchTaskQueue
from agent.foundation.llm_factory import create_chat_model as create_chat_model
from common.cancellation import check_cancellation as _check_cancel_token
from common.config import settings

logger = logging.getLogger(__name__)


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]

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

        self.graph_run_id = str(snapshot_runtime_state.get("graph_run_id") or _new_id("graph_run"))
        self.graph_attempt = int(snapshot_runtime_state.get("graph_attempt") or 1)
        self.root_branch_id = str(snapshot_runtime_state.get("root_branch_id") or "root").strip() or "root"
        self.start_ts = float(snapshot_runtime_state.get("started_at_ts") or time.time())
        self.parallel_workers = max(1, resolve_parallel_workers(self.config))
        self.max_epochs = max(
            1,
            runtime_context._configurable_int(
                self.config,
                "deep_research_max_epochs",
                settings.deep_research_max_epochs,
            ),
        )
        self.results_per_query = max(
            1,
            runtime_context._configurable_int(
                self.config,
                "deep_research_results_per_query",
                settings.deep_research_results_per_query,
            ),
        )
        self.max_seconds = max(
            0.0,
            runtime_context._configurable_float(
                self.config,
                "deep_research_max_seconds",
                settings.deep_research_max_seconds,
            ),
        )
        self.max_tokens = max(
            0,
            runtime_context._configurable_int(
                self.config,
                "deep_research_max_tokens",
                settings.deep_research_max_tokens,
            ),
        )
        self.max_searches = max(0, resolve_max_searches(self.config))
        self.task_retry_limit = max(
            1,
            runtime_context._configurable_int(self.config, "deep_research_task_retry_limit", 2),
        )
        self.pause_before_merge = bool(self.cfg.get("deep_research_pause_before_merge"))
        self.allow_interrupts = bool(self.cfg.get("allow_interrupts", False))
        self.provider_profile = search_runtime._resolve_provider_profile(self.state)
        self.emitter = None
        if self.thread_id:
            try:
                self.emitter = self._deps.get_emitter_sync(self.thread_id)
            except Exception:
                self.emitter = None

        supervisor_model = runtime_context._model_for_task("planning", self.config)
        researcher_model = runtime_context._model_for_task("research", self.config)
        reporter_model = runtime_context._model_for_task("writing", self.config)

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
        self.reporter = self._deps.ResearchReporter(
            self._deps.create_chat_model(reporter_model, temperature=0),
            self.config,
        )
        self.section_revision_limit = max(
            1,
            runtime_context._configurable_int(self.config, "deep_research_section_revision_limit", 1),
        )

    def _search_with_tracking(self, payload: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(payload.get("query") or "").strip()
        max_results = int(payload.get("max_results") or self.results_per_query)
        results = search_runtime._search_query(query, max_results, config, self.provider_profile)
        if query:
            self._emit(
                ToolEventType.SEARCH,
                {
                    "query": query,
                    "provider": "web_search",
                    "results": budgets._compact_sources(results, limit=min(len(results), 5)),
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
            "outline_gate_summary": {},
            "last_review_summary": {},
            "readiness_summary": {},
            "pending_replans": [],
            "section_status_map": {},
            "section_revision_counts": {},
            "section_research_retry_counts": {},
            "searches_used": 0,
            "tokens_used": 0,
            "budget_stop_reason": "",
            "terminal_status": "",
            "terminal_reason": "",
            "tool_runtime_context": runtime_context._tool_runtime_context_snapshot(self.config),
            "role_tool_policies": {},
        }

    def _unpack(self, graph_state: MultiAgentGraphState) -> _RuntimeParts:
        shared_state = copy.deepcopy(graph_state.get("shared_state") or self._initial_shared_state())
        task_queue = ResearchTaskQueue.from_snapshot(graph_state.get("task_queue"))
        artifact_store = LightweightArtifactStore(graph_state.get("artifact_store"))
        runtime_state = self._default_runtime_state()
        runtime_state.update(copy.deepcopy(graph_state.get("runtime_state") or {}))
        # Normalize legacy checkpoint fields from the removed final claim gate.
        runtime_state.pop("final_claim_gate_summary", None)
        if str(runtime_state.get("next_step") or "").strip().lower() == "final_claim_gate":
            runtime_state["next_step"] = "finalize"
        if str(runtime_state.get("active_agent") or "").strip().lower() == "verifier":
            runtime_state["active_agent"] = "reporter"
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
        return run_tracking.next_agent_id(role, runtime_state)

    def _start_agent_run(
        self,
        parts: _RuntimeParts,
        *,
        role: str,
        phase: str,
        task_id: str | None = None,
        section_id: str | None = None,
        branch_id: str | None = None,
        stage: str = "",
        objective_summary: str = "",
        attempt: int = 1,
        requested_tools: list[str] | None = None,
    ) -> dict[str, Any]:
        return run_tracking.start_agent_run(
            runtime_state=parts.runtime_state,
            current_iteration=parts.current_iteration,
            graph_run_id=self.graph_run_id,
            emit=self._emit,
            role=role,
            phase=phase,
            task_id=task_id,
            section_id=section_id,
            branch_id=branch_id,
            stage=stage,
            objective_summary=objective_summary,
            attempt=attempt,
            requested_tools=requested_tools,
        )

    def _finish_agent_run(
        self,
        parts: _RuntimeParts,
        record: dict[str, Any],
        *,
        status: str,
        summary: str,
        stage: str = "",
    ) -> None:
        run_tracking.finish_agent_run(
            agent_runs=parts.agent_runs,
            current_iteration=parts.current_iteration,
            record=record,
            status=status,
            summary=summary,
            emit=self._emit,
            stage=stage,
        )

    def _emit_task_update(self, task: ResearchTask, status: str, *, iteration: int, reason: str = "") -> None:
        run_tracking.emit_task_update(
            task=task,
            status=status,
            iteration=iteration,
            emit=self._emit,
            reason=reason,
        )

    def _emit_artifact_update(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        summary: str,
        status: str = "completed",
        task_id: str | None = None,
        section_id: str | None = None,
        branch_id: str | None = None,
        iteration: int = 1,
        extra: dict[str, Any] | None = None,
    ) -> None:
        run_tracking.emit_artifact_update(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            summary=summary,
            emit=self._emit,
            status=status,
            task_id=task_id,
            section_id=section_id,
            branch_id=branch_id,
            iteration=iteration,
            extra=extra,
        )

    def _emit_decision(self, decision_type: str, reason: str, *, iteration: int, extra: dict[str, Any] | None = None):
        run_tracking.emit_decision(
            decision_type=decision_type,
            reason=reason,
            iteration=iteration,
            emit=self._emit,
            extra=extra,
        )

    def _budget_stop_reason(self, runtime_state: dict[str, Any]) -> str:
        reason = budgets._budget_stop_reason(
            start_ts=self.start_ts,
            searches_used=int(runtime_state.get("searches_used") or 0),
            tokens_used=int(runtime_state.get("tokens_used") or 0),
            max_seconds=self.max_seconds,
            max_tokens=self.max_tokens,
            max_searches=self.max_searches,
        )
        return str(reason or "")

    def _outline_sections(self, outline: dict[str, Any]) -> list[dict[str, Any]]:
        return planning.outline_sections(outline)

    def _build_outline_tasks(
        self,
        *,
        outline: dict[str, Any],
        scope: dict[str, Any],
    ) -> list[ResearchTask]:
        return planning.build_outline_tasks(
            outline=outline,
            scope=scope,
            topic=self.topic,
            domain_config=self.state.get("domain_config") or {},
        )

    def _section_map(self, outline: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return planning.section_map(outline)

    def _build_section_draft(
        self,
        task: ResearchTask,
        section: dict[str, Any],
        bundle: dict[str, Any],
        outcome: dict[str, Any],
        created_by: str,
    ) -> dict[str, Any]:
        return section_review.build_section_draft(task, section, bundle, outcome, created_by)

    def _build_review_issue(self, issue_type: str, message: str, *, blocking: bool) -> dict[str, Any]:
        return section_review.build_review_issue(issue_type, message, blocking=blocking)

    def _review_section_draft(
        self,
        *,
        section: dict[str, Any],
        draft: dict[str, Any],
        bundle: dict[str, Any],
        revision_count: int,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        return section_review.review_section_draft(
            topic=self.topic,
            section_revision_limit=self.section_revision_limit,
            section=section,
            draft=draft,
            bundle=bundle,
            revision_count=revision_count,
        )

    def _build_revision_task(
        self,
        *,
        section: dict[str, Any],
        draft: dict[str, Any],
        review: dict[str, Any],
        scope: dict[str, Any],
        revision_count: int,
    ) -> ResearchTask:
        return planning.build_revision_task(
            section=section,
            draft=draft,
            review=review,
            scope=scope,
            revision_count=revision_count,
        )

    def _build_research_retry_task(
        self,
        *,
        section: dict[str, Any],
        draft: dict[str, Any],
        review: dict[str, Any],
        scope: dict[str, Any],
    ) -> ResearchTask:
        return planning.build_research_retry_task(
            section=section,
            draft=draft,
            review=review,
            scope=scope,
        )

    def _build_supervisor_replan_tasks(
        self,
        *,
        parts: _RuntimeParts,
        outline: dict[str, Any],
        task_specs: list[dict[str, Any]],
    ) -> list[ResearchTask]:
        tasks: list[ResearchTask] = []
        scope = parts.artifact_store.scope()
        section_map = self._section_map(outline)
        revision_counts = dict(parts.runtime_state.get("section_revision_counts") or {})
        research_retry_counts = dict(parts.runtime_state.get("section_research_retry_counts") or {})
        for spec in task_specs:
            if not isinstance(spec, dict):
                continue
            section_id = str(spec.get("section_id") or "").strip()
            if not section_id:
                continue
            section = section_map.get(section_id, {})
            if not section:
                continue
            draft = parts.artifact_store.section_draft(section_id)
            review = parts.artifact_store.section_review(section_id)
            task_kind = str(spec.get("task_kind") or "").strip()
            if task_kind == "section_revision":
                revision_count = int(revision_counts.get(section_id, 0) or 0)
                task = self._build_revision_task(
                    section=section,
                    draft=draft,
                    review=review,
                    scope=scope,
                    revision_count=revision_count,
                )
                revision_counts[section_id] = revision_count + 1
            elif task_kind == "section_research":
                research_retry_count = int(research_retry_counts.get(section_id, 0) or 0)
                task = self._build_research_retry_task(
                    section=section,
                    draft=draft,
                    review=review,
                    scope=scope,
                )
                research_retry_counts[section_id] = research_retry_count + 1
                follow_up_queries = [
                    str(item).strip()
                    for item in spec.get("follow_up_queries", []) or []
                    if str(item).strip()
                ]
                if follow_up_queries:
                    task.query = follow_up_queries[0]
                    task.query_hints = follow_up_queries
                replan_kind = str(spec.get("replan_kind") or "").strip()
                if replan_kind:
                    task.aspect = replan_kind
            else:
                continue
            task.target_issue_ids = [
                str(item).strip()
                for item in spec.get("issue_ids", []) or []
                if str(item).strip()
            ]
            task.title = (
                f"补充对比研究: {task.title}"
                if task_kind == "section_research" and str(spec.get("replan_kind") or "") == "counterevidence"
                else f"时效复核: {task.title}"
                if task_kind == "section_research" and str(spec.get("replan_kind") or "") == "freshness_recheck"
                else f"补充研究: {task.title}"
                if task_kind == "section_research"
                else task.title
            )
            if task_kind == "section_revision":
                task.revision_kind = str(spec.get("replan_kind") or "revision").strip()
            tasks.append(task)
        parts.runtime_state["section_revision_counts"] = revision_counts
        parts.runtime_state["section_research_retry_counts"] = research_retry_counts
        return tasks

    def _aggregate_sections(
        self,
        queue: ResearchTaskQueue,
        store: LightweightArtifactStore,
        runtime_state: dict[str, Any],
    ) -> dict[str, Any]:
        return runtime_artifacts.aggregate_sections(
            queue,
            store,
            runtime_state,
            outline_sections_fn=self._outline_sections,
        )

    def _build_report_sections(self, store: LightweightArtifactStore) -> list[ReportSectionContext]:
        return section_review.build_report_sections(store)

    def artifact_store_section_draft_by_task(self, store: LightweightArtifactStore, task_id: str) -> dict[str, Any]:
        return section_review.artifact_store_section_draft_by_task(store, task_id)

    def _build_plan_artifact(
        self,
        scope: dict[str, Any],
        tasks: list[ResearchTask],
        *,
        coverage_targets: list[str] | None = None,
        coverage_target_source: str = "",
    ) -> dict[str, Any]:
        return runtime_artifacts.build_plan_artifact(
            scope,
            tasks,
            coverage_targets=coverage_targets,
            coverage_target_source=coverage_target_source,
        )

    def _build_evidence_bundle(self, task: ResearchTask, outcome: dict[str, Any], created_by: str) -> dict[str, Any]:
        return runtime_artifacts.build_evidence_bundle(
            task,
            outcome,
            created_by,
            results_per_query=self.results_per_query,
        )

    def _quality_summary(self, queue: ResearchTaskQueue, store: LightweightArtifactStore, runtime_state: dict[str, Any]) -> dict[str, Any]:
        return runtime_artifacts.quality_summary(
            queue,
            store,
            runtime_state,
            outline_sections_fn=self._outline_sections,
        )

    def _research_topology_snapshot(
        self,
        queue: ResearchTaskQueue,
        store: LightweightArtifactStore,
        runtime_state: dict[str, Any],
    ) -> dict[str, Any]:
        return runtime_artifacts.research_topology_snapshot(
            topic=self.topic,
            graph_run_id=self.graph_run_id,
            queue=queue,
            store=store,
            runtime_state=runtime_state,
        )

    def _initial_next_step(
        self,
        task_queue_snapshot: dict[str, Any],
        artifact_store_snapshot: dict[str, Any],
        runtime_state_snapshot: dict[str, Any],
    ) -> str:
        return runtime_artifacts.initial_next_step(
            task_queue_snapshot,
            artifact_store_snapshot,
            runtime_state_snapshot,
            outline_sections_fn=self._outline_sections,
        )

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
            "latest_decision": {},
            "latest_verification_summary": copy.deepcopy(runtime_state.get("last_review_summary") or {}),
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
            "outline_plan",
            "dispatch",
            "reviewer",
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
        return intake_flow.run_clarify_step(
            parts=parts,
            record=record,
            topic=self.topic,
            graph_run_id=self.graph_run_id,
            graph_attempt=self.graph_attempt,
            allow_interrupts=self.allow_interrupts,
            clarifier=self.clarifier,
            build_clarify_transcript_fn=_build_clarify_transcript,
            extract_interrupt_text_fn=_extract_interrupt_text,
            interrupt_fn=interrupt,
            emit_decision_fn=self._emit_decision,
            finish_agent_run_fn=self._finish_agent_run,
            patch_fn=self._patch,
        )

    def _route_after_clarify(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "scope").strip().lower()
        if next_step in {"clarify", "scope"}:
            return next_step
        return "scope"

    def _scope_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "scope"
        record = self._start_agent_run(parts, role="scope", phase="scope", attempt=self.graph_attempt)
        return intake_flow.run_scope_step(
            parts=parts,
            record=record,
            topic=self.topic,
            scope_agent=self.scope_agent,
            build_clarify_transcript_fn=_build_clarify_transcript,
            scope_draft_from_payload_fn=_scope_draft_from_payload,
            build_scope_draft_fn=_build_scope_draft,
            format_scope_draft_markdown_fn=_format_scope_draft_markdown,
            emit_decision_fn=self._emit_decision,
            emit_artifact_update_fn=self._emit_artifact_update,
            finish_agent_run_fn=self._finish_agent_run,
            patch_fn=self._patch,
        )

    def _scope_review_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "scope"
        return intake_flow.run_scope_review_step(
            parts=parts,
            graph_run_id=self.graph_run_id,
            graph_attempt=self.graph_attempt,
            allow_interrupts=self.allow_interrupts,
            scope_draft_from_payload_fn=_scope_draft_from_payload,
            format_scope_draft_markdown_fn=_format_scope_draft_markdown,
            extract_interrupt_text_fn=_extract_interrupt_text,
            interrupt_fn=interrupt,
            emit_decision_fn=self._emit_decision,
            patch_fn=self._patch,
            now_iso_fn=_now_iso,
        )

    def _route_after_scope_review(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "research_brief").strip().lower()
        if next_step in {"scope", "research_brief"}:
            return next_step
        return "research_brief"

    def _research_brief_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        return intake_flow.run_research_brief_step(
            parts=parts,
            topic=self.topic,
            dedupe_texts_fn=_dedupe_texts,
            emit_artifact_update_fn=self._emit_artifact_update,
            emit_decision_fn=self._emit_decision,
            patch_fn=self._patch,
            new_id_fn=_new_id,
        )

    def _outline_plan_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        record = self._start_agent_run(parts, role="supervisor", phase="outline_plan", attempt=self.graph_attempt)
        return planning_flow.run_outline_plan_step(
            parts=parts,
            record=record,
            topic=self.topic,
            graph_attempt=self.graph_attempt,
            supervisor=self.supervisor,
            outline_sections_fn=self._outline_sections,
            build_outline_tasks_fn=self._build_outline_tasks,
            build_plan_artifact_fn=self._build_plan_artifact,
            emit_artifact_update_fn=self._emit_artifact_update,
            emit_task_update_fn=self._emit_task_update,
            emit_decision_fn=self._emit_decision,
            finish_agent_run_fn=self._finish_agent_run,
            patch_fn=self._patch,
            new_id_fn=_new_id,
        )

    def _route_after_supervisor_plan(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "dispatch").strip().lower()
        if next_step in {"scope_review", "research_brief", "dispatch", "reviewer", "finalize"}:
            return next_step
        return "dispatch"

    def _dispatch_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        return planning_flow.run_dispatch_step(
            parts=parts,
            parallel_workers=self.parallel_workers,
            budget_stop_reason_fn=self._budget_stop_reason,
            next_agent_id_fn=self._next_agent_id,
            emit_decision_fn=self._emit_decision,
            emit_task_update_fn=self._emit_task_update,
            patch_fn=self._patch,
        )

    def _route_after_dispatch(self, graph_state: MultiAgentGraphState) -> list[Send] | str:
        payloads = graph_state.get("pending_worker_tasks") or []
        if not payloads:
            return "reviewer"
        sends: list[Send] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            task_payload = payload.get("task") if isinstance(payload.get("task"), dict) else payload
            task_kind = str(task_payload.get("task_kind") or "").strip()
            target = "revisor" if task_kind == "section_revision" else "researcher"
            sends.append(Send(target, {"worker_task": payload}))
        return sends or "reviewer"

    def _researcher_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        payload = graph_state.get("worker_task") or {}
        task_payload = payload.get("task") if isinstance(payload, dict) else None
        task = ResearchTask(**task_payload) if isinstance(task_payload, dict) else ResearchTask(**payload)
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "researcher"
        outline = parts.artifact_store.outline()
        section = self._section_map(outline).get(str(task.section_id or ""), {})
        record = self._start_agent_run(
            parts,
            role="researcher",
            phase="researcher",
            task_id=task.id,
            section_id=task.section_id,
            branch_id=task.branch_id,
            stage="search",
            objective_summary=task.objective or task.goal,
            attempt=max(1, task.attempts),
            requested_tools=list(task.allowed_tools or []),
        )
        return worker_flow.run_researcher_step(
            parts=parts,
            task=task,
            section=section,
            record=record,
            topic=self.topic,
            researcher=self.researcher,
            results_per_query=self.results_per_query,
            emit_task_update_fn=self._emit_task_update,
            build_evidence_bundle_fn=self._build_evidence_bundle,
            build_section_draft_fn=self._build_section_draft,
            finish_agent_run_fn=self._finish_agent_run,
        )

    def _revisor_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        payload = graph_state.get("worker_task") or {}
        task_payload = payload.get("task") if isinstance(payload, dict) else None
        task = ResearchTask(**task_payload) if isinstance(task_payload, dict) else ResearchTask(**payload)
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "revisor"
        outline = parts.artifact_store.outline()
        section = self._section_map(outline).get(str(task.section_id or ""), {})
        current_draft = parts.artifact_store.section_draft(str(task.section_id or ""))
        review = parts.artifact_store.section_review(str(task.section_id or ""))
        record = self._start_agent_run(
            parts,
            role="revisor",
            phase="revisor",
            task_id=task.id,
            section_id=task.section_id,
            branch_id=task.branch_id,
            stage="revision",
            objective_summary=task.objective or task.goal,
            attempt=max(1, task.attempts),
            requested_tools=list(task.allowed_tools or []),
        )
        return worker_flow.run_revisor_step(
            parts=parts,
            task=task,
            section=section,
            current_draft=current_draft,
            review=review,
            record=record,
            emit_task_update_fn=self._emit_task_update,
            finish_agent_run_fn=self._finish_agent_run,
        )

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
        merge_flow.merge_worker_results(
            payloads=payloads,
            shared_state=parts.shared_state,
            task_queue=parts.task_queue,
            artifact_store=parts.artifact_store,
            runtime_state=parts.runtime_state,
            agent_runs=parts.agent_runs,
            current_iteration=parts.current_iteration,
            task_retry_limit=self.task_retry_limit,
            emit_task_update=self._emit_task_update,
            emit_artifact_update=self._emit_artifact_update,
        )
        return self._patch(
            parts,
            next_step="reviewer",
            pending_worker_tasks=[],
            worker_results=[{"__reset__": True}],
        )

    def _reviewer_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "reviewer"
        outline = parts.artifact_store.outline()
        section_map = self._section_map(outline)
        record = self._start_agent_run(parts, role="reviewer", phase="reviewer", attempt=self.graph_attempt)
        review_cycle.review_section_drafts(
            task_queue=parts.task_queue,
            artifact_store=parts.artifact_store,
            runtime_state=parts.runtime_state,
            section_map=section_map,
            task_retry_limit=self.task_retry_limit,
            current_iteration=parts.current_iteration,
            review_section_draft_fn=self._review_section_draft,
            build_revision_task_fn=self._build_revision_task,
            build_research_retry_task_fn=self._build_research_retry_task,
            emit_task_update=self._emit_task_update,
            emit_artifact_update=self._emit_artifact_update,
        )

        aggregate = self._aggregate_sections(parts.task_queue, parts.artifact_store, parts.runtime_state)
        runtime_artifacts.record_readiness_summary(parts.runtime_state, aggregate)
        pending_replans = [
            item
            for item in list(parts.runtime_state.get("pending_replans") or [])
            if isinstance(item, dict) and str(item.get("section_id") or "").strip()
        ]
        if pending_replans:
            self._emit_decision(
                "coverage_gap_detected",
                f"detected {len(pending_replans)} sections requiring more evidence or revision",
                iteration=max(1, parts.current_iteration or 1),
                extra={
                    **aggregate,
                    "replan_count": len(pending_replans),
                    "section_ids": [
                        str(item.get("section_id") or "").strip()
                        for item in pending_replans
                        if str(item.get("section_id") or "").strip()
                    ],
                },
            )
        decision_type = "review_passed" if aggregate.get("outline_ready") else "review_updated"
        self._emit_decision(decision_type, "section review updated", iteration=max(1, parts.current_iteration or 1), extra=aggregate)
        self._emit(ToolEventType.QUALITY_UPDATE, self._quality_summary(parts.task_queue, parts.artifact_store, parts.runtime_state))
        self._finish_agent_run(parts, record, status="completed", summary="section review updated")
        return self._patch(parts, next_step="supervisor_decide")

    def _supervisor_decide_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        aggregate = self._aggregate_sections(parts.task_queue, parts.artifact_store, parts.runtime_state)
        reportable_sections = self._build_report_sections(parts.artifact_store)
        budget_stop_reason = self._budget_stop_reason(parts.runtime_state)
        next_step, decision_payload = review_cycle.decide_supervisor_next_step(
            task_queue=parts.task_queue,
            outline=parts.artifact_store.outline(),
            runtime_state=parts.runtime_state,
            aggregate=aggregate,
            reportable_sections=reportable_sections,
            budget_stop_reason=budget_stop_reason,
            current_iteration=parts.current_iteration,
            max_epochs=self.max_epochs,
            supervisor=self.supervisor,
            emit_decision=self._emit_decision,
        )
        if str(decision_payload.get("action") or "").strip().lower() == "replan":
            tasks = self._build_supervisor_replan_tasks(
                parts=parts,
                outline=parts.artifact_store.outline(),
                task_specs=list(decision_payload.get("task_specs") or []),
            )
            if not tasks:
                parts.runtime_state["pending_replans"] = []
                parts.runtime_state["terminal_status"] = "blocked"
                parts.runtime_state["terminal_reason"] = "supervisor replan produced no executable tasks"
                self._emit_decision(
                    "stop",
                    parts.runtime_state["terminal_reason"],
                    iteration=max(1, parts.current_iteration or 1),
                )
                return self._patch(parts, next_step="finalize")
            parts.task_queue.enqueue(tasks)
            parts.runtime_state["pending_replans"] = []
            for task in tasks:
                self._emit_task_update(
                    task,
                    task.status,
                    iteration=max(1, parts.current_iteration or 1),
                    reason="supervisor_replan",
                )
        return self._patch(parts, next_step=next_step)

    def _route_after_supervisor_decide(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "report").strip().lower()
        if next_step in {"dispatch", "outline_gate", "report", "finalize"}:
            return next_step
        return "report"

    def _outline_gate_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        aggregate = self._aggregate_sections(parts.task_queue, parts.artifact_store, parts.runtime_state)
        runtime_artifacts.record_readiness_summary(parts.runtime_state, aggregate)
        reportable_sections = self._build_report_sections(parts.artifact_store)
        next_step = review_cycle.decide_outline_gate_next_step(
            runtime_state=parts.runtime_state,
            aggregate=aggregate,
            reportable_sections=reportable_sections,
            current_iteration=parts.current_iteration,
            emit_decision=self._emit_decision,
        )
        return self._patch(parts, next_step=next_step)

    def _report_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "reporter"
        record = self._start_agent_run(parts, role="reporter", phase="report", attempt=self.graph_attempt)
        report_sections = self._build_report_sections(parts.artifact_store)
        if not report_sections:
            self._finish_agent_run(parts, record, status="failed", summary="no reportable sections")
            return self._patch(parts, next_step="finalize")

        final_report = completion_flow.build_final_report_artifact(
            topic=self.topic,
            report_sections=report_sections,
            artifact_store=parts.artifact_store,
            reporter=self.reporter,
            created_by=str(record.get("agent_id") or "reporter"),
            final_report_id=_new_id("final_report"),
        )
        parts.artifact_store.set_final_report(final_report)
        self._emit_artifact_update(
            artifact_id=final_report["id"],
            artifact_type="final_report",
            summary=str(final_report.get("executive_summary") or final_report.get("report_markdown") or "")[:180],
            iteration=max(1, parts.current_iteration or 1),
        )
        self._finish_agent_run(
            parts,
            record,
            status="completed",
            summary=str(final_report.get("executive_summary") or "final report ready"),
        )
        return self._patch(parts, next_step="finalize")

    def _finalize_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        quality_summary = self._quality_summary(parts.task_queue, parts.artifact_store, parts.runtime_state)
        research_topology = self._research_topology_snapshot(parts.task_queue, parts.artifact_store, parts.runtime_state)
        node_complete_payload, result = completion_flow.build_finalize_outputs(
            root_branch_id=self.root_branch_id,
            current_iteration=parts.current_iteration,
            task_queue=parts.task_queue,
            artifact_store=parts.artifact_store,
            runtime_state=parts.runtime_state,
            agent_runs=parts.agent_runs,
            shared_state=parts.shared_state,
            quality_summary=quality_summary,
            research_topology=research_topology,
        )
        self._emit(
            ToolEventType.RESEARCH_NODE_COMPLETE,
            node_complete_payload,
        )
        parts.runtime_state["next_step"] = "completed"
        return self._patch(parts, next_step="completed", final_result=result)

    def build_graph(self, *, checkpointer: Any = None, interrupt_before: Any = None):
        workflow = StateGraph(MultiAgentGraphState)
        workflow.add_node("bootstrap", self._bootstrap_node)
        workflow.add_node("clarify", self._clarify_node)
        workflow.add_node("scope", self._scope_node)
        workflow.add_node("scope_review", self._scope_review_node)
        workflow.add_node("research_brief", self._research_brief_node)
        workflow.add_node("outline_plan", self._outline_plan_node)
        workflow.add_node("dispatch", self._dispatch_node)
        workflow.add_node("researcher", self._researcher_node)
        workflow.add_node("revisor", self._revisor_node)
        workflow.add_node("merge", self._merge_node)
        workflow.add_node("reviewer", self._reviewer_node)
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
                "outline_plan",
                "dispatch",
                "reviewer",
                "supervisor_decide",
                "outline_gate",
                "report",
                "finalize",
            ],
        )
        workflow.add_conditional_edges("clarify", self._route_after_clarify, ["clarify", "scope"])
        workflow.add_edge("scope", "scope_review")
        workflow.add_conditional_edges("scope_review", self._route_after_scope_review, ["scope", "research_brief"])
        workflow.add_edge("research_brief", "outline_plan")
        workflow.add_conditional_edges(
            "outline_plan",
            self._route_after_supervisor_plan,
            ["scope_review", "research_brief", "dispatch", "reviewer", "finalize"],
        )
        workflow.add_conditional_edges("dispatch", self._route_after_dispatch, ["researcher", "revisor", "reviewer"])
        workflow.add_edge("researcher", "merge")
        workflow.add_edge("revisor", "merge")
        workflow.add_edge("merge", "reviewer")
        workflow.add_edge("reviewer", "supervisor_decide")
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


def run_multi_agent_deep_research(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    runtime = MultiAgentDeepResearchRuntime(state, config)
    return runtime.run()


__all__ = [
    "MultiAgentDeepResearchRuntime",
    "_format_scope_draft_markdown",
    "run_multi_agent_deep_research",
]
