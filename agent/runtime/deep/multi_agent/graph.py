"""
LangGraph-backed multi-agent Deep Research runtime.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import sys
import time
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Send, interrupt

from agent.core.context import (
    ResearchWorkerContext,
    build_research_worker_context,
    merge_research_worker_context,
)
from agent.core.state import build_deep_runtime_snapshot
from agent.runtime.deep.multi_agent import dispatcher, events, support
from agent.runtime.deep.multi_agent.schema import (
    AgentRunRecord,
    BranchBrief,
    EvidenceCard,
    FinalReportArtifact,
    GraphScopeSnapshot,
    KnowledgeGap,
    ReportSectionDraft,
    ResearchTask,
    WorkerExecutionResult,
    WorkerScopeSnapshot,
    _now_iso,
)
from agent.runtime.deep.multi_agent.store import ArtifactStore, ResearchTaskQueue
from agent.workflows.agents.coordinator import CoordinatorAction
from agent.workflows.knowledge_gap import GapAnalysisResult
from common.cancellation import check_cancellation as _check_cancel_token
from common.config import settings

logger = logging.getLogger(__name__)


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.workflows.deepsearch_multi_agent")
    if compat is None:
        import agent.workflows.deepsearch_multi_agent as compat
    return compat


def _reduce_worker_payloads(
    existing: list[dict[str, Any]] | None,
    new: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    current = list(existing or [])
    if not new:
        return current

    reset = any(isinstance(item, dict) and item.get("__reset__") for item in new)
    payloads = [
        item
        for item in new
        if isinstance(item, dict) and not item.get("__reset__")
    ]
    if reset:
        return payloads
    return current + payloads


class MultiAgentGraphState(TypedDict, total=False):
    shared_state: dict[str, Any]
    topic: str
    graph_run_id: str
    graph_attempt: int
    root_branch_id: str
    task_queue: dict[str, Any]
    artifact_store: dict[str, Any]
    runtime_state: dict[str, Any]
    agent_runs: list[dict[str, Any]]
    current_iteration: int
    planning_mode: str
    next_step: str
    latest_gap_result: dict[str, Any]
    latest_decision: dict[str, Any]
    pending_worker_tasks: list[dict[str, Any]]
    worker_task: dict[str, Any]
    worker_results: Annotated[list[dict[str, Any]], _reduce_worker_payloads]
    final_result: dict[str, Any]


def _restore_agent_runs(items: list[dict[str, Any]]) -> list[AgentRunRecord]:
    restored: list[AgentRunRecord] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        restored.append(AgentRunRecord(**item))
    return restored


def _restore_worker_context(payload: dict[str, Any]) -> ResearchWorkerContext:
    return ResearchWorkerContext(**payload)


def _restore_worker_result(payload: dict[str, Any]) -> WorkerExecutionResult:
    task = ResearchTask(**payload["task"])
    context = _restore_worker_context(payload["context"])
    evidence_cards = [EvidenceCard(**item) for item in payload.get("evidence_cards", [])]
    section_payload = payload.get("section_draft")
    section_draft = ReportSectionDraft(**section_payload) if isinstance(section_payload, dict) else None
    agent_run_payload = payload.get("agent_run")
    agent_run = AgentRunRecord(**agent_run_payload) if isinstance(agent_run_payload, dict) else None
    return WorkerExecutionResult(
        task=task,
        context=context,
        evidence_cards=evidence_cards,
        section_draft=section_draft,
        raw_results=list(payload.get("raw_results", [])),
        tokens_used=int(payload.get("tokens_used", 0) or 0),
        branch_id=payload.get("branch_id"),
        agent_run=agent_run,
        error=str(payload.get("error") or ""),
    )


def _gap_result_from_payload(payload: dict[str, Any] | None) -> GapAnalysisResult | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return GapAnalysisResult.from_dict(payload)


def _derive_role_counters(agent_runs: list[AgentRunRecord]) -> dict[str, int]:
    counters: dict[str, int] = {}
    for run in agent_runs:
        agent_id = str(run.agent_id or "")
        if "-" not in agent_id:
            continue
        role, _, suffix = agent_id.rpartition("-")
        if not role:
            role = str(run.role)
        try:
            counters[role] = max(counters.get(role, 0), int(suffix))
        except ValueError:
            continue
    return counters


@dataclass
class _RuntimeView:
    owner: MultiAgentDeepSearchRuntime
    shared_state: dict[str, Any]
    task_queue: ResearchTaskQueue
    artifact_store: ArtifactStore
    agent_runs: list[AgentRunRecord]
    runtime_state: dict[str, Any]
    graph_run_id: str
    graph_attempt: int
    current_iteration: int
    root_branch_id: str | None
    current_node_id: str

    def __post_init__(self) -> None:
        self.runtime_state.setdefault("role_counters", _derive_role_counters(self.agent_runs))
        self.runtime_state.setdefault("searches_used", 0)
        self.runtime_state.setdefault("tokens_used", 0)
        self.runtime_state.setdefault("budget_stop_reason", "")
        self.runtime_state.setdefault("started_at_ts", self.owner.start_ts)
        self.runtime_state.setdefault("next_step", "")
        self.runtime_state.setdefault("planning_mode", "")
        self.runtime_state.setdefault("last_gap_result", {})
        self.runtime_state.setdefault("last_decision", {})

    def __getattr__(self, name: str) -> Any:
        return getattr(self.owner, name)

    @property
    def emitter(self) -> Any:
        return self.owner.emitter

    @property
    def start_ts(self) -> float:
        return float(self.runtime_state.get("started_at_ts") or self.owner.start_ts)

    @property
    def searches_used(self) -> int:
        return int(self.runtime_state.get("searches_used", 0) or 0)

    @searches_used.setter
    def searches_used(self, value: int) -> None:
        self.runtime_state["searches_used"] = max(0, int(value))

    @property
    def tokens_used(self) -> int:
        return int(self.runtime_state.get("tokens_used", 0) or 0)

    @tokens_used.setter
    def tokens_used(self, value: int) -> None:
        self.runtime_state["tokens_used"] = max(0, int(value))

    @property
    def budget_stop_reason(self) -> str | None:
        value = str(self.runtime_state.get("budget_stop_reason") or "").strip()
        return value or None

    @budget_stop_reason.setter
    def budget_stop_reason(self, value: str | None) -> None:
        self.runtime_state["budget_stop_reason"] = str(value or "")

    def next_agent_id(self, role: str) -> str:
        counters = self.runtime_state.setdefault("role_counters", {})
        counters[role] = int(counters.get(role, 0) or 0) + 1
        return f"{role}-{counters[role]}"

    def _check_cancel(self) -> None:
        if self.shared_state.get("is_cancelled"):
            raise asyncio.CancelledError("Task was cancelled (flag)")
        token_id = self.shared_state.get("cancel_token_id")
        if token_id:
            _check_cancel_token(token_id)

    def _knowledge_summary(self) -> str:
        sections = [section.summary for section in self.artifact_store.section_drafts() if section.summary]
        if sections:
            return "\n\n".join(sections[:8])
        notes = self.shared_state.get("summary_notes", [])
        if isinstance(notes, list) and notes:
            return "\n\n".join(str(note) for note in notes[:8])
        return ""

    def _quality_summary(self, gap_result: GapAnalysisResult | None) -> dict[str, Any]:
        evidence_cards = self.artifact_store.evidence_cards()
        unique_urls = {card.source_url for card in evidence_cards if card.source_url}
        coverage = float(gap_result.overall_coverage) if gap_result else 0.0
        citation_coverage = min(1.0, len(unique_urls) / max(1, len(evidence_cards))) if evidence_cards else 0.0
        return {
            "engine": "multi_agent",
            "stage": "final" if self.task_queue.ready_count() == 0 else "iteration",
            "query_coverage_score": coverage,
            "citation_coverage_score": citation_coverage,
            "knowledge_gap_count": len(gap_result.gaps) if gap_result else 0,
            "suggested_queries": gap_result.suggested_queries if gap_result else [],
            "analysis": gap_result.analysis if gap_result else "",
            "freshness_warning": "",
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "node_id": self.current_node_id,
            "branch_id": self.root_branch_id,
        }

    def _research_tree_snapshot(self) -> dict[str, Any]:
        tasks = sorted(self.task_queue.all_tasks(), key=lambda task: (task.priority, task.created_at, task.id))
        return {
            "id": "deepsearch_multi_agent",
            "topic": self.owner.topic,
            "engine": "multi_agent",
            "graph_run_id": self.graph_run_id,
            "branch_id": self.root_branch_id,
            "children": [
                {
                    "id": task.id,
                    "title": task.title or task.goal,
                    "query": task.query,
                    "status": task.status,
                    "priority": task.priority,
                    "branch_id": task.branch_id,
                    "parent_context_id": task.parent_context_id,
                    "attempts": task.attempts,
                }
                for task in tasks
            ],
        }

    def _scope_summary(self) -> dict[str, Any]:
        task_snapshot = self.task_queue.snapshot()
        briefs = self.artifact_store.branch_briefs()
        graph_scope: GraphScopeSnapshot = {
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "topic": self.owner.topic,
            "phase": self.current_node_id,
            "current_iteration": self.current_iteration,
            "budget": {
                "searches_used": self.searches_used,
                "tokens_used": self.tokens_used,
                "max_searches": self.max_searches,
                "max_tokens": self.max_tokens,
                "max_seconds": self.max_seconds,
                "budget_stop_reason": self.budget_stop_reason,
            },
            "task_queue_stats": task_snapshot.get("stats", {}),
            "artifact_counts": {
                "branch_briefs": len(briefs),
                "evidence_cards": len(self.artifact_store.evidence_cards()),
                "knowledge_gaps": len(self.artifact_store.gap_artifacts()),
                "report_section_drafts": len(self.artifact_store.section_drafts()),
                "has_final_report": self.artifact_store.final_report() is not None,
            },
            "final_status": "completed" if self.artifact_store.final_report() else "running",
        }
        branch_scopes = [
            {
                "branch_id": brief.id,
                "topic": brief.topic,
                "summary": brief.summary,
                "status": brief.status,
                "parent_branch_id": brief.parent_branch_id,
                "task_ids": [task.id for task in self.task_queue.all_tasks() if task.branch_id == brief.id],
            }
            for brief in briefs
        ]
        worker_scopes: list[WorkerScopeSnapshot] = []
        sub_contexts = self.shared_state.get("sub_agent_contexts", {})
        if isinstance(sub_contexts, dict):
            for scope_id, item in sub_contexts.items():
                if not isinstance(item, dict):
                    continue
                worker_scopes.append(
                    {
                        "scope_id": str(scope_id),
                        "task_id": str(item.get("task_id") or ""),
                        "branch_id": item.get("parent_scope_id"),
                        "agent_id": str(item.get("agent_id") or ""),
                        "query": str(item.get("query") or ""),
                        "attempt": int(item.get("attempt") or 0),
                        "status": "completed" if item.get("is_complete") else "running",
                        "artifact_ids": [
                            str(artifact.get("id"))
                            for artifact in item.get("artifacts_created", [])
                            if isinstance(artifact, dict) and artifact.get("id")
                        ],
                    }
                )
        return {
            "graph_scope": graph_scope,
            "branch_scopes": branch_scopes,
            "worker_scopes": worker_scopes,
        }

    def runtime_state_snapshot(self) -> dict[str, Any]:
        return {
            "engine": "multi_agent",
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "phase": self.current_node_id,
            "next_step": self.runtime_state.get("next_step", ""),
            "planning_mode": self.runtime_state.get("planning_mode", ""),
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_epochs,
            "searches_used": self.searches_used,
            "tokens_used": self.tokens_used,
            "max_searches": self.max_searches,
            "max_tokens": self.max_tokens,
            "max_seconds": self.max_seconds,
            "budget_stop_reason": self.budget_stop_reason,
            "elapsed_seconds": round(max(0.0, time.time() - self.start_ts), 3),
            "started_at_ts": self.start_ts,
            "root_branch_id": self.root_branch_id,
            "role_counters": copy.deepcopy(self.runtime_state.get("role_counters", {})),
            "last_gap_result": copy.deepcopy(self.runtime_state.get("last_gap_result", {})),
            "last_decision": copy.deepcopy(self.runtime_state.get("last_decision", {})),
            "scope_summary": self._scope_summary(),
        }

    def snapshot_patch(self, **extra: Any) -> dict[str, Any]:
        self.runtime_state["phase"] = self.current_node_id
        self.runtime_state["next_step"] = extra.get("next_step", self.runtime_state.get("next_step", ""))
        self.runtime_state["planning_mode"] = extra.get(
            "planning_mode",
            self.runtime_state.get("planning_mode", ""),
        )
        latest_gap = extra.get("latest_gap_result")
        if latest_gap is not None:
            self.runtime_state["last_gap_result"] = copy.deepcopy(latest_gap)
        latest_decision = extra.get("latest_decision")
        if latest_decision is not None:
            self.runtime_state["last_decision"] = copy.deepcopy(latest_decision)
        patch: dict[str, Any] = {
            "shared_state": copy.deepcopy(self.shared_state),
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "root_branch_id": self.root_branch_id,
            "task_queue": self.task_queue.snapshot(),
            "artifact_store": self.artifact_store.snapshot(),
            "runtime_state": self.runtime_state_snapshot(),
            "agent_runs": [run.to_dict() for run in self.agent_runs],
            "current_iteration": self.current_iteration,
            "planning_mode": self.runtime_state.get("planning_mode", ""),
            "next_step": self.runtime_state.get("next_step", ""),
        }
        for key, value in extra.items():
            if key in {"latest_gap_result", "latest_decision", "pending_worker_tasks", "worker_results", "final_result"}:
                patch[key] = value
        return patch

    def _emit(self, event_type: events.ToolEventType | str, payload: dict[str, Any]) -> None:
        events.emit(self.emitter, event_type, payload)

    def _emit_task_update(
        self,
        *,
        task: ResearchTask,
        status: str,
        attempt: int | None = None,
        reason: str | None = None,
    ) -> None:
        events.emit_task_update(self, task=task, status=status, attempt=attempt, reason=reason)

    def _emit_artifact_update(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        status: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        summary: str | None = None,
        source_url: str | None = None,
    ) -> None:
        events.emit_artifact_update(
            self,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            status=status,
            task_id=task_id,
            agent_id=agent_id,
            summary=summary,
            source_url=source_url,
        )

    def _emit_agent_start(
        self,
        *,
        agent_id: str,
        role: str,
        phase: str,
        task_id: str | None = None,
        iteration: int | None = None,
        branch_id: str | None = None,
        attempt: int | None = None,
    ) -> None:
        events.emit_agent_start(
            self,
            agent_id=agent_id,
            role=role,
            phase=phase,
            task_id=task_id,
            iteration=iteration,
            branch_id=branch_id,
            attempt=attempt,
        )

    def _emit_agent_complete(
        self,
        *,
        agent_id: str,
        role: str,
        phase: str,
        status: str,
        task_id: str | None = None,
        iteration: int | None = None,
        summary: str | None = None,
        branch_id: str | None = None,
        attempt: int | None = None,
    ) -> None:
        events.emit_agent_complete(
            self,
            agent_id=agent_id,
            role=role,
            phase=phase,
            status=status,
            task_id=task_id,
            iteration=iteration,
            summary=summary,
            branch_id=branch_id,
            attempt=attempt,
        )

    def _emit_decision(
        self,
        *,
        decision_type: str,
        reason: str,
        iteration: int | None = None,
        coverage: float | None = None,
        gap_count: int | None = None,
        attempt: int | None = None,
    ) -> None:
        events.emit_decision(
            self,
            decision_type=decision_type,
            reason=reason,
            iteration=iteration,
            coverage=coverage,
            gap_count=gap_count,
            attempt=attempt,
        )

    def _emit_research_tree_update(self) -> None:
        events.emit_research_tree_update(self)

    def start_agent_run(
        self,
        *,
        role: str,
        phase: str,
        task_id: str | None = None,
        branch_id: str | None = None,
        iteration: int | None = None,
        attempt: int | None = None,
        persist: bool = True,
    ) -> AgentRunRecord:
        record = AgentRunRecord(
            id=support._new_id("agent_run"),
            role=role,
            phase=phase,
            status="running",
            agent_id=self.next_agent_id(role),
            graph_run_id=self.graph_run_id,
            node_id=self.current_node_id,
            task_id=task_id,
            branch_id=branch_id,
            attempt=int(attempt or self.graph_attempt or 1),
        )
        if persist:
            self.agent_runs.append(record)
        self._emit_agent_start(
            agent_id=record.agent_id,
            role=record.role,
            phase=phase,
            task_id=task_id,
            iteration=iteration,
            branch_id=branch_id,
            attempt=record.attempt,
        )
        return record

    def finish_agent_run(
        self,
        record: AgentRunRecord,
        *,
        status: str,
        summary: str = "",
        iteration: int | None = None,
        branch_id: str | None = None,
    ) -> AgentRunRecord:
        record.status = status
        record.summary = summary
        record.ended_at = _now_iso()
        self._emit_agent_complete(
            agent_id=record.agent_id,
            role=record.role,
            phase=record.phase,
            status=status,
            task_id=record.task_id,
            iteration=iteration,
            summary=summary,
            branch_id=branch_id or record.branch_id,
            attempt=record.attempt,
        )
        return record


class MultiAgentDeepSearchRuntime:
    def __init__(self, state: dict[str, Any], config: dict[str, Any]):
        self._deps = _resolve_deps()
        self.state = dict(state)
        self.config = dict(config or {})
        self.cfg = self.config.get("configurable") or {}
        if not isinstance(self.cfg, dict):
            self.cfg = {}

        self.topic = str(self.state.get("input") or self.state.get("topic") or "").strip()
        self.thread_id = str(
            self.cfg.get("thread_id") or self.state.get("cancel_token_id") or ""
        ).strip()
        self.emitter = self._deps.get_emitter_sync(self.thread_id) if self.thread_id else None

        resume_runtime_state = self._resume_runtime_state_snapshot()
        self.start_ts = float(resume_runtime_state.get("started_at_ts") or time.time())
        self.max_epochs = max(
            1,
            support._configurable_int(
                self.config,
                "deepsearch_max_epochs",
                settings.deepsearch_max_epochs,
            ),
        )
        self.query_num = max(
            1,
            support._configurable_int(
                self.config,
                "deepsearch_query_num",
                settings.deepsearch_query_num,
            ),
        )
        self.results_per_query = max(
            1,
            support._configurable_int(
                self.config,
                "deepsearch_results_per_query",
                settings.deepsearch_results_per_query,
            ),
        )
        self.parallel_workers = max(
            1,
            support._configurable_int(
                self.config,
                "tree_parallel_branches",
                settings.tree_parallel_branches,
            ),
        )
        self.max_seconds = max(
            0.0,
            support._configurable_float(
                self.config,
                "deepsearch_max_seconds",
                settings.deepsearch_max_seconds,
            ),
        )
        self.max_tokens = max(
            0,
            support._configurable_int(
                self.config,
                "deepsearch_max_tokens",
                settings.deepsearch_max_tokens,
            ),
        )
        self.max_searches = max(
            0,
            support._configurable_int(
                self.config,
                "deepsearch_tree_max_searches",
                settings.deepsearch_tree_max_searches,
            ),
        )
        self.task_retry_limit = max(
            1,
            support._configurable_int(self.config, "deepsearch_task_retry_limit", 2),
        )
        self.pause_before_merge = bool(self.cfg.get("deepsearch_pause_before_merge"))

        self.provider_profile = support._resolve_provider_profile(self.state)

        planner_model = support._model_for_task("planning", self.config)
        researcher_model = support._model_for_task("research", self.config)
        reporter_model = support._model_for_task("writing", self.config)
        verifier_model = support._model_for_task("gap_analysis", self.config)
        coordinator_model = support._model_for_task("planning", self.config)

        self.planner = self._deps.ResearchPlanner(
            self._deps.create_chat_model(planner_model, temperature=0),
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
        self.verifier = self._deps.KnowledgeGapAnalyzer(
            self._deps.create_chat_model(verifier_model, temperature=0),
            self.config,
        )
        self.coordinator = self._deps.ResearchCoordinator(
            self._deps.create_chat_model(coordinator_model, temperature=0),
            self.config,
        )

    def _resume_task_queue_snapshot(self) -> dict[str, Any]:
        deep_runtime = self.state.get("deep_runtime") or {}
        if isinstance(deep_runtime, dict) and isinstance(deep_runtime.get("task_queue"), dict):
            return copy.deepcopy(deep_runtime["task_queue"])
        snapshot = self.state.get("deepsearch_task_queue")
        return copy.deepcopy(snapshot) if isinstance(snapshot, dict) else {}

    def _resume_artifact_store_snapshot(self) -> dict[str, Any]:
        deep_runtime = self.state.get("deep_runtime") or {}
        if isinstance(deep_runtime, dict) and isinstance(deep_runtime.get("artifact_store"), dict):
            return copy.deepcopy(deep_runtime["artifact_store"])
        snapshot = self.state.get("deepsearch_artifact_store")
        return copy.deepcopy(snapshot) if isinstance(snapshot, dict) else {}

    def _resume_runtime_state_snapshot(self) -> dict[str, Any]:
        deep_runtime = self.state.get("deep_runtime") or {}
        if isinstance(deep_runtime, dict) and isinstance(deep_runtime.get("runtime_state"), dict):
            return copy.deepcopy(deep_runtime["runtime_state"])
        snapshot = self.state.get("deepsearch_runtime_state")
        return copy.deepcopy(snapshot) if isinstance(snapshot, dict) else {}

    def _resume_agent_runs_snapshot(self) -> list[dict[str, Any]]:
        deep_runtime = self.state.get("deep_runtime") or {}
        if isinstance(deep_runtime, dict) and isinstance(deep_runtime.get("agent_runs"), list):
            return copy.deepcopy(deep_runtime["agent_runs"])
        snapshot = self.state.get("deepsearch_agent_runs")
        return copy.deepcopy(snapshot) if isinstance(snapshot, list) else []

    def _initial_shared_state(self) -> dict[str, Any]:
        return {
            "input": self.state.get("input", ""),
            "topic": self.topic,
            "route": self.state.get("route", "deep"),
            "domain": self.state.get("domain", ""),
            "domain_config": copy.deepcopy(self.state.get("domain_config", {})),
            "scraped_content": copy.deepcopy(self.state.get("scraped_content", [])),
            "summary_notes": copy.deepcopy(self.state.get("summary_notes", [])),
            "sources": copy.deepcopy(self.state.get("sources", [])),
            "errors": copy.deepcopy(self.state.get("errors", [])),
            "sub_agent_contexts": copy.deepcopy(self.state.get("sub_agent_contexts", {})),
            "cancel_token_id": self.state.get("cancel_token_id"),
            "is_cancelled": bool(self.state.get("is_cancelled")),
        }

    def _first_branch_id(self, artifact_store_snapshot: dict[str, Any]) -> str | None:
        briefs = artifact_store_snapshot.get("branch_briefs", [])
        if isinstance(briefs, list) and briefs:
            first = briefs[0]
            if isinstance(first, dict):
                return str(first.get("id") or "") or None
        return None

    def _initial_next_step(
        self,
        task_queue_snapshot: dict[str, Any],
        artifact_store_snapshot: dict[str, Any],
        runtime_state_snapshot: dict[str, Any],
    ) -> str:
        existing = str(runtime_state_snapshot.get("next_step") or "").strip()
        if existing:
            return existing
        if artifact_store_snapshot.get("final_report"):
            return "finalize"
        stats = task_queue_snapshot.get("stats", {}) if isinstance(task_queue_snapshot, dict) else {}
        if int(stats.get("total", 0) or 0) == 0:
            return "plan"
        if int(stats.get("ready", 0) or 0) > 0 or int(stats.get("in_progress", 0) or 0) > 0:
            return "dispatch"
        return "verify"

    def build_initial_graph_state(self) -> MultiAgentGraphState:
        task_queue_snapshot = self._resume_task_queue_snapshot()
        artifact_store_snapshot = self._resume_artifact_store_snapshot()
        runtime_state_snapshot = self._resume_runtime_state_snapshot()
        return {
            "shared_state": self._initial_shared_state(),
            "topic": self.topic,
            "graph_run_id": str(runtime_state_snapshot.get("graph_run_id") or support._new_id("graph_run")),
            "graph_attempt": int(runtime_state_snapshot.get("graph_attempt", 0) or 0) + 1,
            "root_branch_id": str(
                runtime_state_snapshot.get("root_branch_id")
                or self._first_branch_id(artifact_store_snapshot)
                or ""
            ).strip(),
            "task_queue": task_queue_snapshot,
            "artifact_store": artifact_store_snapshot,
            "runtime_state": runtime_state_snapshot,
            "agent_runs": self._resume_agent_runs_snapshot(),
            "current_iteration": int(runtime_state_snapshot.get("current_iteration", 0) or 0),
            "planning_mode": str(runtime_state_snapshot.get("planning_mode") or "").strip() or "initial",
            "next_step": self._initial_next_step(
                task_queue_snapshot,
                artifact_store_snapshot,
                runtime_state_snapshot,
            ),
            "latest_gap_result": copy.deepcopy(runtime_state_snapshot.get("last_gap_result", {})),
            "latest_decision": copy.deepcopy(runtime_state_snapshot.get("last_decision", {})),
            "pending_worker_tasks": [],
            "worker_results": [],
        }

    def _view(self, graph_state: MultiAgentGraphState, node_id: str) -> _RuntimeView:
        return _RuntimeView(
            owner=self,
            shared_state=copy.deepcopy(graph_state.get("shared_state") or self._initial_shared_state()),
            task_queue=ResearchTaskQueue.from_snapshot(graph_state.get("task_queue")),
            artifact_store=ArtifactStore.from_snapshot(graph_state.get("artifact_store")),
            agent_runs=_restore_agent_runs(graph_state.get("agent_runs", [])),
            runtime_state=copy.deepcopy(graph_state.get("runtime_state") or {}),
            graph_run_id=str(graph_state.get("graph_run_id") or support._new_id("graph_run")),
            graph_attempt=int(graph_state.get("graph_attempt", 1) or 1),
            current_iteration=int(graph_state.get("current_iteration", 0) or 0),
            root_branch_id=str(graph_state.get("root_branch_id") or "").strip() or None,
            current_node_id=node_id,
        )

    def _search_with_tracking(self, payload: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(payload.get("query") or "").strip()
        max_results = int(payload.get("max_results") or self.results_per_query)
        results = support._search_query(query, max_results, config, self.provider_profile)
        if query and self.emitter:
            events.emit(
                self.emitter,
                events.ToolEventType.SEARCH,
                {
                    "query": query,
                    "provider": "multi_search",
                    "results": support._compact_sources(results, limit=min(len(results), 5)),
                    "count": len(results),
                    "engine": "multi_agent",
                },
            )
        return results

    def _bootstrap_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "bootstrap")
        view._check_cancel()

        requeued = view.task_queue.requeue_in_progress(reason="checkpoint_resume")
        for task in requeued:
            view._emit_task_update(
                task=task,
                status=task.status,
                attempt=task.attempts,
                reason="checkpoint_resume",
            )

        briefs = view.artifact_store.branch_briefs()
        root_brief = next((brief for brief in briefs if brief.id == view.root_branch_id), None)
        if root_brief is None:
            root_brief = briefs[0] if briefs else None
        if root_brief is None:
            root_brief = BranchBrief(
                id=support._new_id("brief"),
                topic=self.topic,
                summary=f"围绕主题“{self.topic}”开展多 agent Deep Research。",
            )
            view.artifact_store.put_brief(root_brief)
            view._emit_artifact_update(
                artifact_id=root_brief.id,
                artifact_type="branch_brief",
                status=root_brief.status,
                summary=root_brief.summary,
            )
        view.root_branch_id = root_brief.id
        next_step = self._initial_next_step(
            view.task_queue.snapshot(),
            view.artifact_store.snapshot(),
            view.runtime_state,
        )
        planning_mode = str(graph_state.get("planning_mode") or view.runtime_state.get("planning_mode") or "").strip()
        if next_step == "plan" and not planning_mode:
            planning_mode = "initial"
        return view.snapshot_patch(next_step=next_step, planning_mode=planning_mode)

    def _route_after_bootstrap(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "plan").strip().lower()
        if next_step in {"dispatch", "verify", "report", "finalize"}:
            return next_step
        return "plan"

    def _plan_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "plan")
        planning_mode = str(graph_state.get("planning_mode") or view.runtime_state.get("planning_mode") or "initial")
        phase = "replan" if planning_mode == "replan" else "initial_plan"
        record = view.start_agent_run(
            role="planner",
            phase=phase,
            branch_id=view.root_branch_id,
            iteration=view.current_iteration or None,
            attempt=view.graph_attempt,
        )
        try:
            existing_queries = [task.query for task in view.task_queue.all_tasks() if task.query]
            if planning_mode == "replan":
                gap_result = _gap_result_from_payload(
                    graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
                )
                gap_labels = [gap.aspect for gap in gap_result.gaps] if gap_result else []
                plan_items = self.planner.refine_plan(
                    self.topic,
                    gaps=gap_labels,
                    existing_queries=existing_queries,
                    num_queries=min(
                        self.query_num,
                        max(1, len(gap_result.suggested_queries) if gap_result else 1),
                    ),
                )
                context_id = f"replan-{view.current_iteration or 0}"
            else:
                plan_items = self.planner.create_plan(
                    self.topic,
                    num_queries=self.query_num,
                    existing_knowledge=view._knowledge_summary(),
                    existing_queries=existing_queries,
                )
                context_id = view.root_branch_id or support._new_id("brief")

            tasks = dispatcher.build_tasks_from_plan(
                view,
                plan_items,
                context_id=context_id,
                branch_id=view.root_branch_id,
            )
            if tasks:
                view.task_queue.enqueue(tasks)
                for task in tasks:
                    view._emit_task_update(task=task, status=task.status, attempt=task.attempts)
                view._emit_research_tree_update()
            view.finish_agent_run(
                record,
                status="completed",
                summary=f"生成 {len(tasks)} 个研究任务",
                iteration=view.current_iteration or None,
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step="dispatch", planning_mode="")
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration or None,
                branch_id=view.root_branch_id,
            )
            raise

    def _dispatch_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "dispatch")
        view.current_iteration += 1
        gap_result = _gap_result_from_payload(
            graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
        )
        view._emit_decision(
            decision_type="research",
            reason="执行当前可调度的研究任务",
            iteration=view.current_iteration,
            coverage=gap_result.overall_coverage if gap_result else None,
            gap_count=len(gap_result.gaps) if gap_result else None,
            attempt=view.graph_attempt,
        )
        pending = dispatcher.claim_ready_task_payloads(view, view.current_iteration)
        if view.budget_stop_reason:
            view._emit_decision(
                decision_type="budget_stop",
                reason=view.budget_stop_reason,
                iteration=view.current_iteration,
                coverage=gap_result.overall_coverage if gap_result else None,
                gap_count=len(gap_result.gaps) if gap_result else None,
                attempt=view.graph_attempt,
            )
        return view.snapshot_patch(
            next_step="verify",
            pending_worker_tasks=pending,
            worker_results=[{"__reset__": True}],
        )

    def _route_after_dispatch(self, graph_state: MultiAgentGraphState) -> list[Send] | str:
        payloads = graph_state.get("pending_worker_tasks") or []
        if not payloads:
            return "verify"
        return [Send("researcher", {"worker_task": payload}) for payload in payloads]

    def _researcher_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "researcher")
        payload = graph_state.get("worker_task") or {}
        task_payload = payload.get("task") if isinstance(payload, dict) else None
        task = ResearchTask(**task_payload) if isinstance(task_payload, dict) else ResearchTask(**payload)
        branch_id = task.branch_id or payload.get("branch_id") or view.root_branch_id
        iteration = int(payload.get("iteration") or view.current_iteration or 0)
        attempt = int(payload.get("attempt") or task.attempts or 1)
        record = view.start_agent_run(
            role="researcher",
            phase="research",
            task_id=task.id,
            branch_id=branch_id,
            iteration=iteration,
            attempt=attempt,
            persist=False,
        )

        worker_parent_state = copy.deepcopy(view.shared_state)
        worker_context = build_research_worker_context(
            worker_parent_state,
            task_id=task.id,
            agent_id=record.agent_id,
            query=task.query,
            topic=self.topic,
            brief={
                "topic": self.topic,
                "goal": task.goal,
                "aspect": task.aspect,
                "iteration": iteration,
            },
            related_artifacts=view.artifact_store.get_related_artifacts(task.id),
            scope_id=f"worker-{task.id}-attempt-{attempt}",
            parent_scope_id=branch_id,
        )
        try:
            view._check_cancel()
            results = self.researcher.execute_queries(
                [task.query],
                max_results_per_query=self.results_per_query,
            )
            summary = self.researcher.summarize_findings(
                self.topic,
                results,
                existing_summary=view._knowledge_summary(),
            )
            evidence_cards: list[EvidenceCard] = []
            for item in results[: min(3, len(results))]:
                evidence_cards.append(
                    EvidenceCard(
                        id=support._new_id("evidence"),
                        task_id=task.id,
                        branch_id=branch_id,
                        source_title=str(item.get("title") or item.get("url") or "Untitled"),
                        source_url=str(item.get("url") or ""),
                        summary=str(item.get("summary") or item.get("snippet") or summary[:280]),
                        excerpt=str(item.get("raw_excerpt") or item.get("summary") or "")[:700],
                        source_provider=str(item.get("provider") or ""),
                        published_date=item.get("published_date"),
                        created_by=record.agent_id,
                        metadata={
                            "query": task.query,
                            "attempt": attempt,
                            "graph_run_id": view.graph_run_id,
                        },
                    )
                )

            section_draft = ReportSectionDraft(
                id=support._new_id("section"),
                task_id=task.id,
                branch_id=branch_id,
                title=task.title or task.goal,
                summary=summary or f"未能从“{task.query}”提取到足够结论。",
                evidence_ids=[card.id for card in evidence_cards],
                created_by=record.agent_id,
            )

            worker_context.summary_notes.append(section_draft.summary)
            worker_context.scraped_content.append(
                {
                    "query": task.query,
                    "results": results,
                    "timestamp": _now_iso(),
                    "task_id": task.id,
                    "agent_id": record.agent_id,
                    "attempt": attempt,
                }
            )
            worker_context.sources.extend(support._compact_sources(results, limit=10))
            worker_context.artifacts_created.extend(
                [card.to_dict() for card in evidence_cards] + [section_draft.to_dict()]
            )
            worker_context.is_complete = True

            view.finish_agent_run(
                record,
                status="completed",
                summary=section_draft.summary[:240],
                iteration=iteration,
                branch_id=branch_id,
            )

            result = WorkerExecutionResult(
                task=task,
                context=worker_context,
                evidence_cards=evidence_cards,
                section_draft=section_draft,
                raw_results=results,
                tokens_used=support._estimate_tokens_from_results(results)
                + support._estimate_tokens_from_text(summary),
                branch_id=branch_id,
                agent_run=record,
            )
        except Exception as exc:
            worker_context.errors.append(str(exc))
            worker_context.is_complete = True
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=iteration,
                branch_id=branch_id,
            )
            result = WorkerExecutionResult(
                task=task,
                context=worker_context,
                evidence_cards=[],
                section_draft=None,
                raw_results=[],
                tokens_used=0,
                branch_id=branch_id,
                agent_run=record,
                error=str(exc),
            )

        return {"worker_results": [result.to_dict()]}

    def _merge_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "merge")
        payloads = dispatcher.sort_worker_payloads(graph_state.get("worker_results") or [])
        if self.pause_before_merge and payloads:
            interrupt(
                {
                    "checkpoint": "deepsearch_merge",
                    "graph_run_id": view.graph_run_id,
                    "iteration": view.current_iteration,
                    "pending_workers": len(payloads),
                }
            )
        for payload in payloads:
            result = _restore_worker_result(payload)
            updates = merge_research_worker_context(view.shared_state, result.context)
            view.shared_state.update(updates)
            view.searches_used += 1
            view.tokens_used += max(0, result.tokens_used)

            if result.agent_run:
                view.agent_runs.append(result.agent_run)

            if result.evidence_cards:
                view.artifact_store.add_evidence(result.evidence_cards)
                for card in result.evidence_cards:
                    view._emit_artifact_update(
                        artifact_id=card.id,
                        artifact_type="evidence_card",
                        status=card.status,
                        task_id=card.task_id,
                        agent_id=card.created_by,
                        summary=card.summary[:180],
                        source_url=card.source_url,
                    )

            if result.section_draft:
                view.artifact_store.add_section_draft(result.section_draft)
                view._emit_artifact_update(
                    artifact_id=result.section_draft.id,
                    artifact_type="report_section_draft",
                    status=result.section_draft.status,
                    task_id=result.section_draft.task_id,
                    agent_id=result.section_draft.created_by,
                    summary=result.section_draft.summary[:180],
                )

            if result.raw_results:
                updated_task = view.task_queue.update_status(result.task.id, "completed")
                if updated_task:
                    view._emit_task_update(
                        task=updated_task,
                        status=updated_task.status,
                        attempt=updated_task.attempts,
                    )
                continue

            reason = result.error or "researcher returned no results"
            if result.task.attempts < self.task_retry_limit and not view.budget_stop_reason:
                failed_task = view.task_queue.update_status(result.task.id, "failed", reason=reason)
                if failed_task:
                    view._emit_task_update(
                        task=failed_task,
                        status=failed_task.status,
                        attempt=failed_task.attempts,
                        reason=reason,
                    )
                retry_task = view.task_queue.update_status(result.task.id, "ready", reason=reason)
                if retry_task:
                    view._emit_task_update(
                        task=retry_task,
                        status=retry_task.status,
                        attempt=retry_task.attempts,
                        reason=reason,
                    )
            else:
                failed_task = view.task_queue.update_status(result.task.id, "failed", reason=reason)
                if failed_task:
                    view._emit_task_update(
                        task=failed_task,
                        status=failed_task.status,
                        attempt=failed_task.attempts,
                        reason=reason,
                    )

        view._emit_research_tree_update()
        return view.snapshot_patch(
            next_step="verify",
            pending_worker_tasks=[],
            worker_results=[{"__reset__": True}],
        )

    def _verify_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "verify")
        record = view.start_agent_run(
            role="verifier",
            phase="coverage_check",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
        )
        try:
            executed_queries = [
                task.query for task in view.task_queue.all_tasks() if task.status == "completed"
            ]
            gap_result = self.verifier.analyze(
                self.topic,
                executed_queries=executed_queries,
                collected_knowledge=view._knowledge_summary(),
            )
            gap_artifacts = [
                KnowledgeGap(
                    id=support._new_id("gap"),
                    aspect=gap.aspect,
                    importance=gap.importance,
                    reason=gap.reason,
                    branch_id=view.root_branch_id,
                    suggested_queries=gap_result.suggested_queries,
                )
                for gap in gap_result.gaps
            ]
            view.artifact_store.replace_gaps(gap_artifacts)
            for gap in gap_artifacts:
                view._emit_artifact_update(
                    artifact_id=gap.id,
                    artifact_type="knowledge_gap",
                    status=gap.status,
                    summary=f"{gap.aspect}: {gap.reason}",
                )

            quality_summary = view._quality_summary(gap_result)
            view._emit(events.ToolEventType.QUALITY_UPDATE, quality_summary)
            view.finish_agent_run(
                record,
                status="completed",
                summary=f"coverage={gap_result.overall_coverage:.2f}, gaps={len(gap_result.gaps)}",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(
                next_step="coordinate",
                latest_gap_result=gap_result.to_dict(),
            )
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            raise

    def _coordinate_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "coordinate")
        gap_result = _gap_result_from_payload(
            graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
        )
        record = view.start_agent_run(
            role="coordinator",
            phase="loop_decision",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
        )
        try:
            if view.budget_stop_reason:
                latest_decision = {
                    "action": "budget_stop",
                    "reasoning": view.budget_stop_reason,
                    "iteration": view.current_iteration,
                }
                view._emit_decision(
                    decision_type="budget_stop",
                    reason=view.budget_stop_reason,
                    iteration=view.current_iteration,
                    coverage=gap_result.overall_coverage if gap_result else None,
                    gap_count=len(gap_result.gaps) if gap_result else None,
                    attempt=view.graph_attempt,
                )
                view.finish_agent_run(
                    record,
                    status="completed",
                    summary=view.budget_stop_reason,
                    iteration=view.current_iteration,
                    branch_id=view.root_branch_id,
                )
                return view.snapshot_patch(
                    next_step="report",
                    latest_decision=latest_decision,
                    planning_mode="",
                )

            evidence_count = len(view.artifact_store.evidence_cards())
            section_count = len(view.artifact_store.section_drafts())
            unique_urls = {
                card.source_url
                for card in view.artifact_store.evidence_cards()
                if card.source_url
            }
            citation_accuracy = min(1.0, len(unique_urls) / max(1, evidence_count)) if evidence_count else 0.0
            decision = self.coordinator.decide_next_action(
                topic=self.topic,
                num_queries=view.task_queue.completed_count(),
                num_sources=len(unique_urls),
                num_summaries=section_count,
                current_epoch=view.current_iteration,
                max_epochs=self.max_epochs,
                knowledge_summary=view._knowledge_summary(),
                quality_score=gap_result.overall_coverage if gap_result else 0.0,
                quality_gap_count=len(gap_result.gaps) if gap_result else 0,
                citation_accuracy=citation_accuracy,
            )
            latest_decision = {
                "action": decision.action.value,
                "reasoning": decision.reasoning,
                "iteration": view.current_iteration,
            }
            view._emit_decision(
                decision_type=decision.action.value,
                reason=decision.reasoning,
                iteration=view.current_iteration,
                coverage=gap_result.overall_coverage if gap_result else None,
                gap_count=len(gap_result.gaps) if gap_result else None,
                attempt=view.graph_attempt,
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=f"{decision.action.value}: {decision.reasoning}",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )

            next_step = "report"
            planning_mode = ""
            if view.current_iteration >= self.max_epochs:
                next_step = "report"
            elif view.task_queue.ready_count() > 0:
                next_step = "dispatch"
            elif (
                decision.action not in {CoordinatorAction.COMPLETE, CoordinatorAction.SYNTHESIZE}
                and gap_result
                and gap_result.gaps
            ):
                next_step = "plan"
                planning_mode = "replan"
            return view.snapshot_patch(
                next_step=next_step,
                planning_mode=planning_mode,
                latest_decision=latest_decision,
            )
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            raise

    def _route_after_coordinate(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "report").strip().lower()
        if next_step in {"plan", "dispatch", "report"}:
            return next_step
        return "report"

    def _report_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "report")
        record = view.start_agent_run(
            role="reporter",
            phase="final_report",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
        )
        try:
            section_drafts = view.artifact_store.section_drafts()
            findings = [section.summary for section in section_drafts if section.summary]
            evidence_cards = view.artifact_store.evidence_cards()
            citation_urls = [card.source_url for card in evidence_cards if card.source_url]

            final_report = self.reporter.generate_report(
                self.topic,
                findings=findings or [view._knowledge_summary() or "暂无充分结论"],
                sources=citation_urls[: max(5, min(20, len(citation_urls)))],
            )
            executive_summary = self.reporter.generate_executive_summary(final_report, self.topic)
            final_artifact = FinalReportArtifact(
                id=support._new_id("final_report"),
                report_markdown=final_report,
                executive_summary=executive_summary,
                citation_urls=citation_urls,
            )
            view.artifact_store.set_final_report(final_artifact)
            view._emit_artifact_update(
                artifact_id=final_artifact.id,
                artifact_type="final_report",
                status=final_artifact.status,
                agent_id=final_artifact.created_by,
                summary=executive_summary[:180],
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=executive_summary[:240] or "完成最终报告生成",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step="finalize")
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            raise

    def _finalize_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "finalize")
        gap_result = _gap_result_from_payload(
            graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
        )
        final_artifact = view.artifact_store.final_report()
        report_text = final_artifact.report_markdown if final_artifact else ""
        executive_summary = final_artifact.executive_summary if final_artifact else ""
        evidence_cards = view.artifact_store.evidence_cards()
        quality_summary = view._quality_summary(gap_result)
        sources = support._compact_sources(
            [card.to_dict() for card in evidence_cards],
            limit=max(5, min(20, len(evidence_cards))),
        )
        elapsed = max(0.0, time.time() - self.start_ts)

        deepsearch_artifacts = {
            "mode": "multi_agent",
            "engine": "multi_agent",
            "task_queue": view.task_queue.snapshot(),
            "artifact_store": view.artifact_store.snapshot(),
            "research_tree": view._research_tree_snapshot(),
            "quality_summary": quality_summary,
            "runtime_state": view.runtime_state_snapshot(),
        }

        view._emit(
            events.ToolEventType.RESEARCH_NODE_COMPLETE,
            {
                "node_id": "deepsearch_multi_agent",
                "summary": executive_summary or report_text[:1200],
                "sources": sources,
                "quality": quality_summary,
                "engine": "multi_agent",
                "iteration": view.current_iteration,
                "graph_run_id": view.graph_run_id,
                "graph_attempt": view.graph_attempt,
                "branch_id": view.root_branch_id,
            },
        )

        messages = [AIMessage(content=report_text)]
        if executive_summary:
            messages.append(AIMessage(content=f"执行摘要: {executive_summary}"))
        if view.budget_stop_reason:
            messages.append(AIMessage(content=f"(预算限制提示: {view.budget_stop_reason})"))

        view.runtime_state["next_step"] = "completed"
        result = {
            "deep_runtime": build_deep_runtime_snapshot(
                engine="multi_agent",
                task_queue=view.task_queue.snapshot(),
                artifact_store=view.artifact_store.snapshot(),
                runtime_state=view.runtime_state_snapshot(),
                agent_runs=[run.to_dict() for run in view.agent_runs],
            ),
            "research_plan": [task.query for task in view.task_queue.all_tasks()],
            "scraped_content": view.shared_state.get("scraped_content", []),
            "draft_report": report_text,
            "final_report": report_text,
            "quality_summary": quality_summary,
            "sources": sources,
            "deepsearch_artifacts": deepsearch_artifacts,
            "deepsearch_mode": "multi_agent",
            "deepsearch_engine": "multi_agent",
            "deepsearch_task_queue": view.task_queue.snapshot(),
            "deepsearch_artifact_store": view.artifact_store.snapshot(),
            "deepsearch_runtime_state": view.runtime_state_snapshot(),
            "deepsearch_agent_runs": [run.to_dict() for run in view.agent_runs],
            "research_tree": view._research_tree_snapshot(),
            "messages": messages,
            "is_complete": False,
            "budget_stop_reason": view.budget_stop_reason,
            "deepsearch_tokens_used": view.tokens_used,
            "deepsearch_elapsed_seconds": elapsed,
            "errors": view.shared_state.get("errors", []),
            "sub_agent_contexts": view.shared_state.get("sub_agent_contexts", {}),
        }
        return view.snapshot_patch(final_result=result, next_step="completed")

    def build_graph(self, *, checkpointer: Any = None, interrupt_before: Any = None):
        workflow = StateGraph(MultiAgentGraphState)
        workflow.add_node("bootstrap", self._bootstrap_node)
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("dispatch", self._dispatch_node)
        workflow.add_node("researcher", self._researcher_node)
        workflow.add_node("merge", self._merge_node)
        workflow.add_node("verify", self._verify_node)
        workflow.add_node("coordinate", self._coordinate_node)
        workflow.add_node("report", self._report_node)
        workflow.add_node("finalize", self._finalize_node)

        workflow.set_entry_point("bootstrap")
        workflow.add_conditional_edges(
            "bootstrap",
            self._route_after_bootstrap,
            ["plan", "dispatch", "verify", "report", "finalize"],
        )
        workflow.add_edge("plan", "dispatch")
        workflow.add_conditional_edges(
            "dispatch",
            self._route_after_dispatch,
            ["researcher", "verify"],
        )
        workflow.add_edge("researcher", "merge")
        workflow.add_edge("merge", "verify")
        workflow.add_edge("verify", "coordinate")
        workflow.add_conditional_edges(
            "coordinate",
            self._route_after_coordinate,
            ["plan", "dispatch", "report"],
        )
        workflow.add_edge("report", "finalize")
        workflow.add_edge("finalize", END)
        return workflow.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)

    def run(self) -> dict[str, Any]:
        try:
            graph = self.build_graph()
            output = graph.invoke(self.build_initial_graph_state(), self.config)
            if isinstance(output, dict) and isinstance(output.get("final_result"), dict):
                return output["final_result"]
            return output if isinstance(output, dict) else {}
        except asyncio.CancelledError:
            return {
                "is_cancelled": True,
                "is_complete": True,
                "errors": ["DeepSearch was cancelled"],
                "final_report": "任务已被取消",
            }


def create_multi_agent_deepsearch_graph(
    state: dict[str, Any],
    config: dict[str, Any],
    *,
    checkpointer: Any = None,
    interrupt_before: Any = None,
):
    runtime = MultiAgentDeepSearchRuntime(state, config)
    return runtime.build_graph(checkpointer=checkpointer, interrupt_before=interrupt_before)


def run_multi_agent_deepsearch(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    runtime = MultiAgentDeepSearchRuntime(state, config)
    return runtime.run()


__all__ = [
    "GapAnalysisResult",
    "MultiAgentDeepSearchRuntime",
    "create_multi_agent_deepsearch_graph",
    "run_multi_agent_deepsearch",
]
