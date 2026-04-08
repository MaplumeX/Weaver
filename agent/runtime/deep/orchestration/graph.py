"""
Lightweight LangGraph-backed Deep Research runtime.

This module keeps the public entrypoints stable while dramatically reducing the
number of persisted runtime artifacts. The loop is intentionally compact:

clarify -> scope -> scope_review -> research_brief -> supervisor_plan
-> dispatch -> researcher/revisor -> merge -> reviewer -> supervisor_decide
-> outline_gate -> report -> final_claim_gate -> finalize
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
from langgraph.types import Send, interrupt

import agent.runtime.deep.support.runtime_support as support
from agent.contracts.events import ToolEventType
from agent.contracts.events import get_emitter_sync as get_emitter_sync
from agent.core.llm_factory import create_chat_model as create_chat_model
from agent.core.state import build_deep_runtime_snapshot
from agent.research.source_url_utils import canonicalize_source_url
from agent.runtime.deep.artifacts.public_artifacts import build_public_deep_research_artifacts
from agent.runtime.deep.config import resolve_max_searches, resolve_parallel_workers
from agent.runtime.deep.roles import (
    DeepResearchClarifyAgent as DeepResearchClarifyAgent,
)
from agent.runtime.deep.roles import (
    DeepResearchScopeAgent as DeepResearchScopeAgent,
)
from agent.runtime.deep.roles import (
    ResearchAgent as ResearchAgent,
)
from agent.runtime.deep.roles import (
    ResearchReporter as ResearchReporter,
)
from agent.runtime.deep.roles import (
    ResearchSupervisor as ResearchSupervisor,
)
from agent.runtime.deep.roles.reporter import (
    ReportContext,
    ReportSectionContext,
    ReportSource,
)
from agent.runtime.deep.schema import (
    AgentRunRecord,
    EvidenceBundle,
    FinalReportArtifact,
    OutlineArtifact,
    OutlineSection,
    ResearchPlanArtifact,
    ResearchTask,
    ScopeDraft,
    SectionCertificationArtifact,
    SectionDraftArtifact,
    SectionReviewArtifact,
    _now_iso,
)
from agent.runtime.deep.services.knowledge_gap import (
    GapAnalysisResult,
)
from agent.runtime.deep.services.knowledge_gap import (
    KnowledgeGapAnalyzer as KnowledgeGapAnalyzer,
)
from agent.runtime.deep.state import read_deep_runtime_snapshot
from agent.runtime.deep.store import ResearchTaskQueue
from agent.runtime.deep.support.graph_helpers import (
    MultiAgentGraphState,
)
from agent.runtime.deep.support.graph_helpers import (
    build_clarify_transcript as _build_clarify_transcript,
)
from agent.runtime.deep.support.graph_helpers import (
    build_scope_draft as _build_scope_draft,
)
from agent.runtime.deep.support.graph_helpers import (
    extract_interrupt_text as _extract_interrupt_text,
)
from agent.runtime.deep.support.graph_helpers import (
    format_scope_draft_markdown as _format_scope_draft_markdown,
)
from agent.runtime.deep.support.graph_helpers import (
    scope_draft_from_payload as _scope_draft_from_payload,
)
from agent.runtime.deep.support.graph_helpers import (
    split_findings as _split_findings,
)
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


def _text_overlap_score(left: str, right: str) -> float:
    left_tokens = set(_coverage_tokens(left))
    right_tokens = set(_coverage_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(1, min(len(left_tokens), len(right_tokens)))


def _branch_title(task: ResearchTask) -> str:
    return task.title or task.objective or task.goal or task.query


def _branch_summary_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": result.get("id"),
        "task_id": result.get("task_id"),
        "branch_id": result.get("branch_id"),
        "title": result.get("title"),
        "summary": result.get("summary"),
        "key_findings": list(result.get("key_findings") or []),
        "open_questions": list(result.get("open_questions") or []),
        "validation_status": result.get("validation_status", "pending"),
        "source_urls": list(result.get("source_urls") or []),
    }


def _branch_validation_text(result: dict[str, Any]) -> str:
    summary = str(result.get("summary") or "").strip()
    findings = [str(item).strip() for item in result.get("key_findings", []) or [] if str(item).strip()]
    return "\n".join([summary, *findings]).strip()


def _section_title(payload: dict[str, Any]) -> str:
    return str(
        payload.get("title")
        or payload.get("objective")
        or payload.get("core_question")
        or payload.get("query")
        or "研究章节"
    ).strip()


def _section_draft_text(payload: dict[str, Any]) -> str:
    summary = str(payload.get("summary") or "").strip()
    findings = [str(item).strip() for item in payload.get("key_findings", []) or [] if str(item).strip()]
    limitations = [str(item).strip() for item in payload.get("limitations", []) or [] if str(item).strip()]
    return "\n".join([summary, *findings, *limitations]).strip()


def _primary_claim_units(payload: dict[str, Any]) -> list[dict[str, Any]]:
    claim_units = [
        item
        for item in payload.get("claim_units", []) or []
        if isinstance(item, dict)
    ]
    primary = [
        item
        for item in claim_units
        if str(item.get("importance") or "secondary").strip().lower() == "primary"
    ]
    return primary or claim_units[:1]


def _claim_grounding_ratio(payload: dict[str, Any]) -> float:
    primary = _primary_claim_units(payload)
    if not primary:
        return 0.0
    grounded = 0
    for item in primary:
        if bool(item.get("grounded")) or list(item.get("evidence_passage_ids") or []):
            grounded += 1
    return grounded / max(1, len(primary))


def _needs_freshness_advisory(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    freshness_markers = (
        "latest",
        "current",
        "recent",
        "today",
        "newest",
        "最新",
        "当前",
        "近期",
        "最近",
        "今年",
        "本月",
    )
    return any(marker in normalized for marker in freshness_markers)


_SECTION_OBJECTIVE_HARD_GATE_THRESHOLD = 0.7
_SECTION_OBJECTIVE_SOURCE_FALLBACK_THRESHOLD = 0.0
_SECTION_GROUNDING_HARD_GATE_THRESHOLD = 0.6


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
        self._outline = dict(snapshot.get("outline") or {})
        self._plan = dict(snapshot.get("plan") or {})
        self._evidence_bundles = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("evidence_bundles", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        section_draft_items = snapshot.get("section_drafts")
        if not isinstance(section_draft_items, list):
            section_draft_items = []
        self._section_drafts = {
            str(item.get("section_id") or item.get("task_id") or item.get("id")): dict(item)
            for item in section_draft_items or []
            if isinstance(item, dict) and (item.get("section_id") or item.get("task_id") or item.get("id"))
        }
        section_review_items = snapshot.get("section_reviews")
        if not isinstance(section_review_items, list):
            section_review_items = []
        self._section_reviews = {
            str(item.get("section_id") or item.get("task_id") or item.get("id")): dict(item)
            for item in section_review_items or []
            if isinstance(item, dict) and (item.get("section_id") or item.get("task_id") or item.get("id"))
        }
        self._section_certifications = {
            str(item.get("section_id") or item.get("id")): dict(item)
            for item in snapshot.get("section_certifications", []) or []
            if isinstance(item, dict) and (item.get("section_id") or item.get("id"))
        }
        self._final_report = dict(snapshot.get("final_report") or {})

    def scope(self) -> dict[str, Any]:
        return copy.deepcopy(self._scope)

    def set_scope(self, scope: dict[str, Any]) -> None:
        self._scope = copy.deepcopy(scope)

    def outline(self) -> dict[str, Any]:
        return copy.deepcopy(self._outline)

    def set_outline(self, outline: dict[str, Any]) -> None:
        self._outline = copy.deepcopy(outline)

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

    def evidence_bundle(self, task_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._evidence_bundles.get(task_id, {}))

    def section_drafts(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(
                self._section_drafts.values(),
                key=lambda value: (
                    int(value.get("section_order", 0) or 0),
                    str(value.get("section_id") or value.get("task_id") or ""),
                ),
            )
        ]

    def set_section_draft(self, draft: dict[str, Any]) -> None:
        key = str(draft.get("section_id") or draft.get("task_id") or draft.get("id") or "").strip()
        if key:
            self._section_drafts[key] = copy.deepcopy(draft)

    def section_draft(self, section_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._section_drafts.get(section_id, {}))

    def section_reviews(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(
                self._section_reviews.values(),
                key=lambda value: (
                    int(value.get("section_order", 0) or 0),
                    str(value.get("section_id") or value.get("task_id") or ""),
                ),
            )
        ]

    def set_section_review(self, review: dict[str, Any]) -> None:
        key = str(review.get("section_id") or review.get("task_id") or review.get("id") or "").strip()
        if key:
            self._section_reviews[key] = copy.deepcopy(review)

    def section_review(self, section_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._section_reviews.get(section_id, {}))

    def clear_section_review(self, section_id: str) -> None:
        key = str(section_id or "").strip()
        if key:
            self._section_reviews.pop(key, None)

    def section_certifications(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(
                self._section_certifications.values(),
                key=lambda value: (
                    int(value.get("section_order", 0) or 0),
                    str(value.get("section_id") or ""),
                ),
            )
        ]

    def set_section_certification(self, certification: dict[str, Any]) -> None:
        key = str(certification.get("section_id") or certification.get("id") or "").strip()
        if key:
            self._section_certifications[key] = copy.deepcopy(certification)

    def section_certification(self, section_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._section_certifications.get(section_id, {}))

    def final_report(self) -> dict[str, Any]:
        return copy.deepcopy(self._final_report)

    def set_final_report(self, report: dict[str, Any]) -> None:
        self._final_report = copy.deepcopy(report)

    def certified_section_drafts(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.section_drafts()
            if bool(item.get("certified"))
        ]

    def reportable_section_drafts(self) -> list[dict[str, Any]]:
        reportable: list[dict[str, Any]] = []
        for item in self.section_drafts():
            summary = str(item.get("summary") or "").strip()
            findings = [
                str(value).strip()
                for value in item.get("key_findings", []) or []
                if str(value).strip()
            ]
            if summary or findings:
                reportable.append(item)
        return reportable

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
            "outline": copy.deepcopy(self._outline),
            "plan": copy.deepcopy(self._plan),
            "evidence_bundles": self.evidence_bundles(),
            "section_drafts": self.section_drafts(),
            "section_reviews": self.section_reviews(),
            "section_certifications": self.section_certifications(),
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
        self.max_gap_branches_per_iteration = max(
            1,
            support._configurable_int(
                self.config,
                "deep_research_max_gap_branches_per_iteration",
                getattr(settings, "deep_research_max_gap_branches_per_iteration", 2),
            ),
        )
        configured_max_total_tasks = support._configurable_int(
            self.config,
            "deep_research_max_total_tasks",
            getattr(settings, "deep_research_max_total_tasks", 0),
        )
        default_max_total_tasks = max(1, self.query_num) + (self.max_epochs * self.max_gap_branches_per_iteration)
        self.max_total_tasks = configured_max_total_tasks if configured_max_total_tasks > 0 else default_max_total_tasks
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
            support._configurable_int(self.config, "deep_research_section_revision_limit", 1),
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
            "outline_gate_summary": {},
            "last_review_summary": {},
            "final_claim_gate_summary": {},
            "section_status_map": {},
            "section_revision_counts": {},
            "section_research_retry_counts": {},
            "searches_used": 0,
            "tokens_used": 0,
            "budget_stop_reason": "",
            "terminal_status": "",
            "terminal_reason": "",
            "tool_runtime_context": support._tool_runtime_context_snapshot(self.config),
            "role_tool_policies": {},
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
        section_id: str | None = None,
        branch_id: str | None = None,
        stage: str = "",
        objective_summary: str = "",
        attempt: int = 1,
        requested_tools: list[str] | None = None,
    ) -> dict[str, Any]:
        agent_id = self._next_agent_id(role, parts.runtime_state)
        policy_snapshot = support._deep_research_role_tool_policy_snapshot(
            role,
            allowed_tools=requested_tools,
        )
        requested_tool_snapshot = (
            [str(item).strip() for item in (requested_tools or []) if str(item).strip()]
            if requested_tools is not None
            else list(policy_snapshot.get("requested_tools") or [])
        )
        role_tool_policies = dict(parts.runtime_state.get("role_tool_policies") or {})
        role_tool_policies[role] = copy.deepcopy(policy_snapshot)
        role_tool_policies[role]["requested_tools"] = requested_tool_snapshot
        parts.runtime_state["role_tool_policies"] = role_tool_policies
        record = AgentRunRecord(
            id=support._new_id("agent_run"),
            role=role,  # type: ignore[arg-type]
            phase=phase,
            status="running",
            agent_id=agent_id,
            graph_run_id=self.graph_run_id,
            node_id=phase,
            task_id=task_id,
            section_id=section_id,
            branch_id=branch_id,
            stage=stage,
            objective_summary=objective_summary,
            attempt=attempt,
            requested_tools=requested_tool_snapshot,
            resolved_tools=list(policy_snapshot.get("allowed_tool_names") or []),
        ).to_dict()
        self._emit(
            ToolEventType.RESEARCH_AGENT_START,
            {
                "agent_id": agent_id,
                "role": role,
                "phase": phase,
                "task_id": task_id,
                "section_id": section_id,
                "branch_id": branch_id,
                "iteration": max(1, parts.current_iteration or 1),
                "attempt": attempt,
                "stage": stage,
                "objective_summary": objective_summary,
                "requested_tools": requested_tool_snapshot,
                "resolved_tools": list(policy_snapshot.get("allowed_tool_names") or []),
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
                "section_id": record.get("section_id"),
                "branch_id": record.get("branch_id"),
                "iteration": max(1, parts.current_iteration or 1),
                "attempt": record.get("attempt", 1),
                "status": status,
                "summary": summary[:240],
                "stage": stage or record.get("stage") or "",
                "requested_tools": list(record.get("requested_tools") or []),
                "resolved_tools": list(record.get("resolved_tools") or []),
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
            "section_id": task.section_id,
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
        section_id: str | None = None,
        branch_id: str | None = None,
        iteration: int = 1,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "status": status,
            "task_id": task_id,
            "section_id": section_id,
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

    def _derive_coverage_targets(
        self,
        scope: dict[str, Any],
        tasks: list[ResearchTask],
    ) -> tuple[list[str], str]:
        scope_questions = _dedupe_texts(scope.get("core_questions") or []) if isinstance(scope, dict) else []
        if scope_questions and len(scope_questions) <= max(1, len(tasks)):
            return scope_questions, "scope_core_questions"

        plan_objectives = _dedupe_texts(
            [
                task.objective or task.goal or task.title or task.query
                for task in tasks
                if isinstance(task, ResearchTask)
            ]
        )
        if plan_objectives:
            return plan_objectives, "planned_objectives"
        return scope_questions, "scope_core_questions" if scope_questions else ""

    def _assign_coverage_targets(
        self,
        tasks: list[ResearchTask],
        coverage_targets: list[str],
    ) -> dict[str, list[str]]:
        normalized_targets = _dedupe_texts(coverage_targets)
        if not normalized_targets:
            return {}

        assignments: dict[str, list[str]] = {}
        remaining_targets = list(normalized_targets)
        for task in sorted(tasks, key=lambda item: (item.priority, item.created_at, item.id)):
            task_text = "\n".join(
                _dedupe_texts(
                    [
                        task.title,
                        task.objective,
                        task.goal,
                        task.query,
                        *list(task.query_hints or []),
                        *list(task.acceptance_criteria or []),
                    ]
                )
            )
            ranked_targets = sorted(
                normalized_targets,
                key=lambda item: (-_text_overlap_score(task_text, item), item),
            )
            selected = ""
            for candidate in ranked_targets:
                if candidate in remaining_targets:
                    selected = candidate
                    break
            if not selected:
                selected = ranked_targets[0] if ranked_targets else ""
            if not selected:
                continue
            assignments[task.id] = [selected]
            if selected in remaining_targets:
                remaining_targets.remove(selected)
        return assignments

    def _ensure_coverage_state(self, parts: _RuntimeParts) -> None:
        scope = parts.artifact_store.scope()
        if not scope:
            scope = copy.deepcopy(parts.runtime_state.get("approved_scope_draft") or {})
        tasks = parts.task_queue.all_tasks()

        coverage_targets = _dedupe_texts(parts.runtime_state.get("coverage_targets") or [])
        if not coverage_targets:
            coverage_targets, source = self._derive_coverage_targets(scope, tasks)
            parts.runtime_state["coverage_targets"] = coverage_targets
            parts.runtime_state["coverage_target_source"] = source
        elif not str(parts.runtime_state.get("coverage_target_source") or "").strip():
            parts.runtime_state["coverage_target_source"] = "scope_core_questions"

        if not coverage_targets:
            parts.runtime_state["task_coverage_map"] = dict(parts.runtime_state.get("task_coverage_map") or {})
            return

        task_coverage_map = {
            str(task_id): _dedupe_texts(targets)
            for task_id, targets in dict(parts.runtime_state.get("task_coverage_map") or {}).items()
            if str(task_id).strip()
        }
        missing_tasks = [task for task in tasks if task.id not in task_coverage_map]
        if missing_tasks:
            task_coverage_map.update(self._assign_coverage_targets(missing_tasks, coverage_targets))
        parts.runtime_state["task_coverage_map"] = task_coverage_map

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

    def _outline_sections(self, outline: dict[str, Any]) -> list[dict[str, Any]]:
        sections = [
            item
            for item in list(outline.get("sections") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        return sorted(
            sections,
            key=lambda item: (
                int(item.get("section_order", 0) or 0),
                str(item.get("id") or ""),
            ),
        )

    def _build_outline_tasks(
        self,
        *,
        outline: dict[str, Any],
        scope: dict[str, Any],
    ) -> list[ResearchTask]:
        tasks: list[ResearchTask] = []
        for index, section in enumerate(self._outline_sections(outline), 1):
            core_question = str(section.get("core_question") or section.get("objective") or "").strip()
            title = _section_title(section)
            query_hints = _dedupe_texts([
                core_question,
                f"{self.topic} {core_question}".strip(),
                title,
            ])
            query = query_hints[0] if query_hints else core_question or title
            task = ResearchTask(
                id=support._new_id("task"),
                goal=core_question or title,
                query=query,
                priority=max(1, int(section.get("section_order", index) or index)),
                objective=str(section.get("objective") or core_question or title).strip(),
                task_kind="section_research",
                acceptance_criteria=_dedupe_texts(section.get("acceptance_checks") or [core_question]),
                allowed_tools=["search", "read", "extract", "synthesize"],
                input_artifact_ids=[
                    str(item).strip()
                    for item in [
                        str(scope.get("id") or "").strip(),
                        str(outline.get("id") or "").strip(),
                    ]
                    if str(item).strip()
                ],
                output_artifact_types=["section_draft", "evidence_bundle"],
                query_hints=query_hints or [core_question or title],
                title=title,
                aspect="section",
                section_id=str(section.get("id") or "").strip(),
            )
            tasks.append(task)
        return tasks

    def _fallback_outline_plan(self, scope: dict[str, Any]) -> dict[str, Any]:
        questions = _dedupe_texts(scope.get("core_questions") or [scope.get("research_goal") or self.topic])
        sections = [
            OutlineSection(
                id=support._new_id("section"),
                title=f"问题 {index}: {question}",
                objective=question,
                core_question=question,
                acceptance_checks=[question],
                source_requirements=[
                    "至少 1 个可引用来源",
                    "至少 1 段可定位 passage 支撑主结论",
                ],
                freshness_policy="default_advisory",
                section_order=index,
                status="planned",
            ).to_dict()
            for index, question in enumerate(questions, 1)
        ]
        return OutlineArtifact(
            id=support._new_id("outline"),
            topic=self.topic,
            outline_version=1,
            sections=sections,
            required_section_ids=[str(item.get("id") or "") for item in sections if str(item.get("id") or "")],
            question_section_map={
                str(item.get("core_question") or "").strip(): str(item.get("id") or "").strip()
                for item in sections
                if str(item.get("core_question") or "").strip() and str(item.get("id") or "").strip()
            },
        ).to_dict()

    def _fallback_section_decision(
        self,
        *,
        outline: dict[str, Any],
        section_status_map: dict[str, Any],
        budget_stop_reason: str = "",
    ) -> dict[str, Any]:
        if budget_stop_reason:
            return {"action": "stop", "reasoning": budget_stop_reason}
        required_ids = [
            str(item).strip()
            for item in (outline.get("required_section_ids") or [])
            if str(item).strip()
        ]
        if not required_ids:
            required_ids = [
                str(item.get("id") or "").strip()
                for item in self._outline_sections(outline)
                if str(item.get("id") or "").strip()
            ]
        if not required_ids:
            required_ids = [
                str(section_id).strip()
                for section_id in dict(section_status_map or {}).keys()
                if str(section_id).strip()
            ]
        blocked = [
            section_id
            for section_id in required_ids
            if str((section_status_map or {}).get(section_id) or "").strip() == "blocked"
        ]
        if blocked:
            return {"action": "stop", "reasoning": "存在阻塞的 required section"}
        pending = [
            section_id
            for section_id in required_ids
            if str((section_status_map or {}).get(section_id) or "planned").strip() not in {"certified", "blocked", "failed"}
        ]
        if pending:
            return {"action": "dispatch", "reasoning": "仍有未认证的 section"}
        return {"action": "report", "reasoning": "所有 required section 已认证"}

    def _section_map(self, outline: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("id") or "").strip(): item
            for item in self._outline_sections(outline)
            if str(item.get("id") or "").strip()
        }

    def _build_section_draft(
        self,
        task: ResearchTask,
        section: dict[str, Any],
        bundle: dict[str, Any],
        outcome: dict[str, Any],
        created_by: str,
    ) -> dict[str, Any]:
        summary = str(outcome.get("summary") or "").strip()
        claim_units = [
            item
            for item in list(outcome.get("claim_units") or [])
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
        if not claim_units:
            fallback_passage_ids = [
                str(item.get("id") or "").strip()
                for item in bundle.get("passages", []) or []
                if str(item.get("id") or "").strip()
            ]
            fallback_source_urls = [
                str(item.get("url") or "").strip()
                for item in bundle.get("sources", []) or []
                if str(item.get("url") or "").strip()
            ]
            fallback_claim_texts = _dedupe_texts([summary, *(outcome.get("key_findings") or [])])
            claim_units = [
                {
                    "id": f"claim_{index}",
                    "text": text,
                    "importance": "primary" if index <= 2 else "secondary",
                    "evidence_passage_ids": fallback_passage_ids[:1],
                    "evidence_urls": fallback_source_urls[:1],
                    "grounded": bool(fallback_passage_ids),
                }
                for index, text in enumerate(fallback_claim_texts, 1)
                if text
            ]
        draft = SectionDraftArtifact(
            id=support._new_id("section_draft"),
            task_id=task.id,
            section_id=str(task.section_id or ""),
            branch_id=task.branch_id,
            title=_section_title(section) or _branch_title(task),
            objective=str(section.get("objective") or task.objective or task.goal).strip(),
            core_question=str(section.get("core_question") or task.objective or task.goal).strip(),
            summary=summary,
            key_findings=list(outcome.get("key_findings") or _split_findings(summary) or [summary]),
            open_questions=list(outcome.get("open_questions") or []),
            confidence_note=str(outcome.get("confidence_note") or "").strip(),
            source_urls=[str(item.get("url") or "").strip() for item in bundle.get("sources", []) if item.get("url")],
            claim_units=claim_units,
            limitations=list(outcome.get("limitations") or []),
            evidence_bundle_id=str(bundle.get("id") or "") or None,
            created_by=created_by,
        ).to_dict()
        draft["section_order"] = int(section.get("section_order", 0) or 0)
        return draft

    def _build_review_issue(self, issue_type: str, message: str, *, blocking: bool) -> dict[str, Any]:
        return {
            "id": support._new_id("issue"),
            "issue_type": issue_type,
            "message": message,
            "blocking": blocking,
            "status": "open",
            "created_at": _now_iso(),
        }

    def _review_section_draft(
        self,
        *,
        section: dict[str, Any],
        draft: dict[str, Any],
        bundle: dict[str, Any],
        revision_count: int,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        draft_text = _section_draft_text(draft)
        objective = str(section.get("objective") or section.get("core_question") or draft.get("objective") or "").strip()
        objective_overlap = _text_overlap_score(objective, draft_text)
        objective_score = 1.0 if objective_overlap >= 0.15 else (0.8 if objective_overlap >= 0.05 else 0.55)

        grounding_ratio = _claim_grounding_ratio(draft)
        grounding_score = round(grounding_ratio, 3)
        source_count = len(bundle.get("sources") or [])
        has_primary_sources = source_count > 0 and len(bundle.get("passages") or []) > 0
        objective_met = bool(str(draft.get("summary") or "").strip()) and (
            objective_score >= _SECTION_OBJECTIVE_HARD_GATE_THRESHOLD
            or source_count > 0
        )

        blocking_issues: list[dict[str, Any]] = []
        advisory_issues: list[dict[str, Any]] = []
        follow_up_queries: list[str] = []

        if not draft_text:
            blocking_issues.append(
                self._build_review_issue("objective_not_met", "章节草稿为空，尚未回答核心问题", blocking=True)
            )
        elif not objective_met:
            blocking_issues.append(
                self._build_review_issue("objective_not_met", "章节尚未稳定回答核心问题", blocking=True)
            )

        if not has_primary_sources:
            blocking_issues.append(
                self._build_review_issue("insufficient_sources", "缺少可定位来源或 passage，无法支撑主结论", blocking=True)
            )

        if grounding_ratio < _SECTION_GROUNDING_HARD_GATE_THRESHOLD:
            blocking_issues.append(
                self._build_review_issue(
                    "primary_claim_ungrounded",
                    f"主结论的证据绑定比例不足 {int(_SECTION_GROUNDING_HARD_GATE_THRESHOLD * 100)}%",
                    blocking=True,
                )
            )
            follow_up_queries.extend(
                _dedupe_texts(draft.get("open_questions") or [objective, str(section.get("core_question") or "")])
            )
        elif grounding_ratio < 1.0:
            advisory_issues.append(
                self._build_review_issue(
                    "secondary_claim_ungrounded",
                    "仍有部分结论未完全绑定证据，建议在报告中保留限制说明",
                    blocking=False,
                )
            )

        if _needs_freshness_advisory(f"{self.topic} {objective}"):
            published_dates = [
                str(item.get("published_date") or "").strip()
                for item in bundle.get("sources", []) or []
                if str(item.get("published_date") or "").strip()
            ]
            if not published_dates:
                advisory_issues.append(
                    self._build_review_issue(
                        "freshness_risk",
                        "该章节关注最新信息，但来源缺少明确发布时间，默认作为 advisory 处理",
                        blocking=False,
                    )
                )

        if advisory_issues and not blocking_issues and revision_count < self.section_revision_limit and not str(draft.get("summary") or "").strip():
            verdict = "revise_section"
        elif blocking_issues:
            verdict = "request_research"
        else:
            verdict = "accept_section"

        review = SectionReviewArtifact(
            id=support._new_id("section_review"),
            task_id=str(draft.get("task_id") or ""),
            section_id=str(draft.get("section_id") or ""),
            branch_id=draft.get("branch_id"),
            verdict=verdict,
            objective_score=round(objective_score, 3),
            grounding_score=grounding_score,
            freshness_score=0.65 if advisory_issues else 0.8,
            contradiction_score=1.0,
            blocking_issues=blocking_issues,
            advisory_issues=advisory_issues,
            follow_up_queries=_dedupe_texts(follow_up_queries or [objective]),
            notes="; ".join(
                [str(item.get("message") or "").strip() for item in [*blocking_issues, *advisory_issues] if str(item.get("message") or "").strip()]
            ),
        ).to_dict()
        review["section_order"] = int(section.get("section_order", 0) or 0)

        certification: dict[str, Any] | None = None
        if verdict == "accept_section":
            certification = SectionCertificationArtifact(
                id=support._new_id("section_certification"),
                section_id=str(draft.get("section_id") or ""),
                certified=True,
                key_claims_grounded_ratio=round(grounding_ratio, 3),
                objective_met=objective_met,
                has_primary_sources=has_primary_sources,
                freshness_warning=(
                    "freshness_risk"
                    if any(str(item.get("issue_type") or "") == "freshness_risk" for item in advisory_issues)
                    else ""
                ),
                limitations=[
                    str(item.get("message") or "").strip()
                    for item in advisory_issues
                    if str(item.get("message") or "").strip()
                ],
                blocking_issue_count=0,
                advisory_issue_count=len(advisory_issues),
            ).to_dict()
            certification["section_order"] = int(section.get("section_order", 0) or 0)

        return review, certification

    def _build_revision_task(
        self,
        *,
        section: dict[str, Any],
        draft: dict[str, Any],
        review: dict[str, Any],
        scope: dict[str, Any],
        revision_count: int,
    ) -> ResearchTask:
        core_question = str(section.get("core_question") or section.get("objective") or draft.get("objective") or "").strip()
        return ResearchTask(
            id=support._new_id("task"),
            goal=core_question,
            query=str(draft.get("summary") or core_question).strip() or core_question,
            priority=max(1, int(section.get("section_order", 1) or 1)),
            objective=str(section.get("objective") or core_question).strip(),
            task_kind="section_revision",
            acceptance_criteria=_dedupe_texts(section.get("acceptance_checks") or [core_question]),
            allowed_tools=["synthesize"],
            input_artifact_ids=[
                str(item).strip()
                for item in [
                    str(scope.get("id") or "").strip(),
                    str(section.get("id") or "").strip(),
                    str(draft.get("id") or "").strip(),
                    str(review.get("id") or "").strip(),
                ]
                if str(item).strip()
            ],
            output_artifact_types=["section_draft"],
            query_hints=[core_question],
            title=f"修订章节: {_section_title(section)}",
            aspect="section_revision",
            section_id=str(section.get("id") or "").strip(),
            parent_task_id=str(draft.get("task_id") or "") or None,
            revision_kind="reviewer_revision",
            target_issue_ids=[
                str(item.get("id") or "").strip()
                for item in review.get("advisory_issues", []) or []
                if str(item.get("id") or "").strip()
            ],
        )

    def _build_research_retry_task(
        self,
        *,
        section: dict[str, Any],
        draft: dict[str, Any],
        review: dict[str, Any],
        scope: dict[str, Any],
    ) -> ResearchTask:
        follow_up_queries = _dedupe_texts(review.get("follow_up_queries") or [section.get("core_question")])
        query = follow_up_queries[0] if follow_up_queries else str(section.get("core_question") or "").strip()
        return ResearchTask(
            id=support._new_id("task"),
            goal=str(section.get("core_question") or section.get("objective") or "").strip(),
            query=query,
            priority=max(1, int(section.get("section_order", 1) or 1)),
            objective=str(section.get("objective") or section.get("core_question") or "").strip(),
            task_kind="section_research",
            acceptance_criteria=_dedupe_texts(section.get("acceptance_checks") or [section.get("core_question")]),
            allowed_tools=["search", "read", "extract", "synthesize"],
            input_artifact_ids=[
                str(item).strip()
                for item in [
                    str(scope.get("id") or "").strip(),
                    str(section.get("id") or "").strip(),
                    str(draft.get("id") or "").strip(),
                    str(review.get("id") or "").strip(),
                ]
                if str(item).strip()
            ],
            output_artifact_types=["section_draft", "evidence_bundle"],
            query_hints=follow_up_queries or [query],
            title=f"补充研究: {_section_title(section)}",
            aspect="section_retry",
            section_id=str(section.get("id") or "").strip(),
            parent_task_id=str(draft.get("task_id") or "") or None,
            target_issue_ids=[
                str(item.get("id") or "").strip()
                for item in review.get("blocking_issues", []) or []
                if str(item.get("id") or "").strip()
            ],
        )

    def _aggregate_sections(
        self,
        queue: ResearchTaskQueue,
        store: LightweightArtifactStore,
        runtime_state: dict[str, Any],
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
                for item in self._outline_sections(outline)
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
        ready = bool(required_section_ids) and not pending_section_ids and not blocked_section_ids
        return {
            "required_section_count": len(required_section_ids),
            "certified_section_count": len(certified_section_ids),
            "pending_section_count": len(pending_section_ids),
            "blocked_section_count": len(blocked_section_ids),
            "required_section_ids": required_section_ids,
            "certified_section_ids": certified_section_ids,
            "missing_section_ids": pending_section_ids,
            "blocked_section_ids": blocked_section_ids,
            "advisory_issue_count": advisory_issue_count,
            "blocking_issue_count": blocking_issue_count,
            "outline_ready": ready,
            "ready_task_count": queue.ready_count(),
            "source_count": len(store.all_sources()),
        }

    def _build_report_sections(self, store: LightweightArtifactStore) -> list[ReportSectionContext]:
        sections: list[ReportSectionContext] = []
        for item in store.reportable_section_drafts():
            section_id = str(item.get("section_id") or "").strip()
            review = store.section_review(section_id) if section_id else {}
            certification = store.section_certification(section_id) if section_id else {}
            summary = str(item.get("summary") or "").strip()
            findings = _dedupe_texts(
                [str(value).strip() for value in item.get("key_findings", []) or [] if str(value).strip()]
            )
            limitation_messages = _dedupe_texts(
                [
                    *[str(value).strip() for value in item.get("limitations", []) or [] if str(value).strip()],
                    *[
                        str(value).strip()
                        for value in certification.get("limitations", []) or []
                        if str(value).strip()
                    ],
                    *[
                        str(issue.get("message") or "").strip()
                        for issue in review.get("advisory_issues", []) or []
                        if str(issue.get("message") or "").strip()
                    ],
                    *[
                        str(issue.get("message") or "").strip()
                        for issue in review.get("blocking_issues", []) or []
                        if str(issue.get("message") or "").strip()
                    ],
                ]
            )
            if not bool(item.get("certified")):
                limitation_messages = _dedupe_texts(
                    [
                        "该章节基于当前可得信息整理，尚未达到完全认证标准",
                        *limitation_messages,
                    ]
                )
            sections.append(
                ReportSectionContext(
                    title=str(item.get("title") or "研究章节"),
                    summary=summary or (findings[0] if findings else "暂无充分章节摘要"),
                    branch_summaries=[f"限制: {message}" for message in limitation_messages],
                    findings=findings,
                    citation_urls=list(item.get("source_urls") or []),
                )
            )
        return sections

    def _normalize_passages_for_claim_gate(self, store: LightweightArtifactStore) -> list[dict[str, Any]]:
        passages: list[dict[str, Any]] = []
        for bundle in store.evidence_bundles():
            task_id = str(bundle.get("task_id") or "").strip()
            section_id = ""
            draft = self.artifact_store_section_draft_by_task(store, task_id)
            if draft:
                section_id = str(draft.get("section_id") or "").strip()
            for item in bundle.get("passages", []) or []:
                if not isinstance(item, dict):
                    continue
                passages.append(
                    {
                        **copy.deepcopy(item),
                        "task_id": task_id,
                        "section_id": section_id,
                    }
                )
        return passages

    def artifact_store_section_draft_by_task(self, store: LightweightArtifactStore, task_id: str) -> dict[str, Any]:
        task_key = str(task_id or "").strip()
        if not task_key:
            return {}
        for draft in store.section_drafts():
            if str(draft.get("task_id") or "").strip() == task_key:
                return copy.deepcopy(draft)
        return {}

    def _build_plan_artifact(
        self,
        scope: dict[str, Any],
        tasks: list[ResearchTask],
        *,
        coverage_targets: list[str] | None = None,
        coverage_target_source: str = "",
    ) -> dict[str, Any]:
        artifact = ResearchPlanArtifact(
            id=support._new_id("plan"),
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

    def _append_tasks_to_plan_artifact(self, parts: _RuntimeParts, tasks: list[ResearchTask]) -> None:
        if not tasks:
            return
        plan = parts.artifact_store.plan()
        if not plan:
            return
        plan_tasks = [
            item
            for item in list(plan.get("tasks") or [])
            if isinstance(item, dict)
        ]
        for task in tasks:
            plan_tasks.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "objective": task.objective,
                    "query": task.query,
                    "priority": task.priority,
                }
            )
        plan["tasks"] = plan_tasks
        if parts.runtime_state.get("coverage_targets"):
            plan["coverage_targets"] = _dedupe_texts(parts.runtime_state.get("coverage_targets") or [])
        if parts.runtime_state.get("coverage_target_source"):
            plan["coverage_target_source"] = str(parts.runtime_state.get("coverage_target_source") or "")
        parts.artifact_store.set_plan(plan)

    def _build_gap_branch_tasks(
        self,
        parts: _RuntimeParts,
        aggregate: dict[str, Any],
    ) -> tuple[list[ResearchTask], dict[str, list[str]]]:
        uncovered_questions = _dedupe_texts(aggregate.get("uncovered_questions") or [])
        if not uncovered_questions:
            return [], {}

        all_tasks = parts.task_queue.all_tasks()
        remaining_capacity = max(0, self.max_total_tasks - len(all_tasks))
        if remaining_capacity <= 0:
            return [], {}

        task_coverage_map = {
            str(task_id): _dedupe_texts(targets)
            for task_id, targets in dict(parts.runtime_state.get("task_coverage_map") or {}).items()
            if str(task_id).strip()
        }
        active_questions = {
            target
            for task in all_tasks
            if task.status in {"ready", "in_progress"}
            for target in task_coverage_map.get(task.id, [])
        }
        related_task_map = {
            str(question): [
                str(task_id).strip()
                for task_id in task_ids
                if str(task_id).strip()
            ]
            for question, task_ids in dict(aggregate.get("coverage_question_task_ids") or {}).items()
        }
        query_map = {
            str(question): _dedupe_texts(queries)
            for question, queries in dict(aggregate.get("recommended_gap_queries_by_question") or {}).items()
        }
        existing_queries = {
            str(task.query or "").strip().lower()
            for task in all_tasks
            if str(task.query or "").strip()
        }
        scope = parts.artifact_store.scope()
        base_priority = max((task.priority for task in all_tasks), default=0)
        branch_limit = min(self.max_gap_branches_per_iteration, remaining_capacity)
        new_tasks: list[ResearchTask] = []
        assignments: dict[str, list[str]] = {}

        for question in uncovered_questions:
            if len(new_tasks) >= branch_limit:
                break
            if question in active_questions:
                continue
            candidate_queries = _dedupe_texts(query_map.get(question) or [question, f"{self.topic} {question}"])
            query = next(
                (item for item in candidate_queries if item.lower() not in existing_queries),
                candidate_queries[0] if candidate_queries else question,
            )
            query_hints = _dedupe_texts([query, *candidate_queries, question])
            task = ResearchTask(
                id=support._new_id("task"),
                goal=question,
                query=query,
                priority=base_priority + len(new_tasks) + 1,
                objective=question,
                task_kind="branch_research",
                acceptance_criteria=[question],
                allowed_tools=["search", "read", "extract", "synthesize"],
                input_artifact_ids=[str(scope.get("id") or "")] if scope.get("id") else [],
                query_hints=query_hints,
                title=f"补齐覆盖: {question}",
                aspect="coverage_gap",
                branch_id=support._new_id("branch"),
                parent_task_id=(related_task_map.get(question) or [None])[0],
            )
            new_tasks.append(task)
            assignments[task.id] = [question]
            existing_queries.update(item.lower() for item in query_hints if item)

        return new_tasks, assignments

    def _build_evidence_bundle(self, task: ResearchTask, outcome: dict[str, Any], created_by: str) -> dict[str, Any]:
        sources = [
            item
            for item in copy.deepcopy(outcome.get("sources") or [])
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        ]
        if not sources:
            sources = support._compact_sources(
                list(outcome.get("search_results") or []),
                limit=max(3, self.results_per_query),
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
            id=support._new_id("bundle"),
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

    def _build_branch_result(
        self,
        task: ResearchTask,
        bundle: dict[str, Any],
        outcome: dict[str, Any],
        created_by: str,
    ) -> dict[str, Any]:
        summary = str(outcome.get("summary") or "").strip()
        return {
            "id": support._new_id("branch_result"),
            "task_id": task.id,
            "section_id": task.section_id,
            "branch_id": task.branch_id,
            "title": _branch_title(task),
            "objective": task.objective or task.goal,
            "summary": summary,
            "key_findings": list(outcome.get("key_findings") or _split_findings(summary) or [summary]),
            "open_questions": list(outcome.get("open_questions") or []),
            "confidence_note": str(outcome.get("confidence_note") or "").strip(),
            "source_urls": [
                str(item.get("url") or "").strip()
                for item in bundle.get("sources", [])
                if item.get("url")
            ],
            "evidence_bundle_id": str(bundle.get("id") or "") or None,
            "created_by": created_by,
        }

    def _build_validation_summary(
        self,
        task: ResearchTask,
        branch_result: dict[str, Any],
        gap_result: GapAnalysisResult,
        runtime_state: dict[str, Any],
    ) -> dict[str, Any]:
        acceptance_score = _score_acceptance_match(task, _branch_validation_text(branch_result))
        advisory_only = acceptance_score >= 1.0
        if gap_result.overall_coverage >= 0.6 or advisory_only:
            status = "passed"
        elif task.attempts < self.task_retry_limit and self.max_epochs > 1:
            status = "retry"
        else:
            status = "failed"
        assigned_targets = _dedupe_texts((runtime_state.get("task_coverage_map") or {}).get(task.id) or [])
        coverage_hits = assigned_targets if status == "passed" and bool(branch_result.get("source_urls")) else []
        coverage_misses = [item for item in assigned_targets if item not in coverage_hits]
        missing_aspects = _dedupe_texts([gap.aspect for gap in gap_result.gaps] + coverage_misses)
        notes = gap_result.analysis or ""
        if advisory_only and missing_aspects:
            notes = f"{notes}; acceptance criteria 已满足, 缺口作为 advisory hints 记录".strip("; ")
        payload = {
            "id": support._new_id("validation"),
            "task_id": task.id,
            "section_id": task.section_id,
            "branch_id": task.branch_id,
            "status": status,
            "score": float(gap_result.overall_coverage),
            "missing_aspects": missing_aspects,
            "retry_queries": _dedupe_texts(gap_result.suggested_queries or [task.query]),
            "notes": notes,
            "status_reason": "advisory_only" if advisory_only and missing_aspects else "",
        }
        payload["coverage_hits"] = coverage_hits
        payload["coverage_misses"] = coverage_misses
        payload["coverage_confidence"] = round(max(float(gap_result.overall_coverage), acceptance_score), 3)
        payload["suggested_follow_up_queries"] = _dedupe_texts(gap_result.suggested_queries or [task.query])
        return payload

    def _aggregate_validation(
        self,
        queue: ResearchTaskQueue,
        store: LightweightArtifactStore,
        runtime_state: dict[str, Any],
    ) -> dict[str, Any]:
        validations = store.section_reviews()
        passed = [item for item in validations if item.get("status") == "passed"]
        retry = [item for item in validations if item.get("status") == "retry"]
        failed = [item for item in validations if item.get("status") == "failed"]
        advisory = [
            item
            for item in validations
            if item.get("status") == "passed" and item.get("status_reason") == "advisory_only"
        ]
        coverage_targets = _dedupe_texts(runtime_state.get("coverage_targets") or [])
        coverage_question_task_ids: dict[str, list[str]] = {}
        recommended_gap_queries_by_question: dict[str, list[str]] = {}
        covered_questions: list[str] = []

        for item in validations:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id") or "").strip()
            for question in _dedupe_texts(item.get("coverage_hits") or []):
                if task_id:
                    coverage_question_task_ids.setdefault(question, []).append(task_id)
                if question not in covered_questions:
                    covered_questions.append(question)
            for question in _dedupe_texts(item.get("coverage_misses") or []):
                if task_id:
                    coverage_question_task_ids.setdefault(question, []).append(task_id)
                suggested = _dedupe_texts(
                    item.get("suggested_follow_up_queries") or item.get("retry_queries") or [question]
                )
                existing = recommended_gap_queries_by_question.setdefault(question, [])
                recommended_gap_queries_by_question[question] = _dedupe_texts([*existing, *suggested])

        uncovered_questions = [item for item in coverage_targets if item not in covered_questions]
        for question in uncovered_questions:
            recommended_gap_queries_by_question.setdefault(question, [question])

        coverage_by_question = [
            {
                "question": question,
                "status": "covered" if question in covered_questions else "uncovered",
                "task_ids": coverage_question_task_ids.get(question, []),
                "suggested_queries": recommended_gap_queries_by_question.get(question, []),
            }
            for question in coverage_targets
        ]
        coverage_target_count = len(coverage_targets)
        covered_question_count = len(covered_questions)
        coverage_score = (
            round(covered_question_count / max(1, coverage_target_count), 3)
            if coverage_target_count > 0
            else round(len(passed) / max(1, len(store.section_drafts())), 3)
        )
        coverage_ready = (
            bool(passed) and not uncovered_questions
            if coverage_target_count > 0
            else bool(passed)
        )
        return {
            "branch_count": len(store.section_drafts()),
            "passed_branch_count": len(passed),
            "retry_branch_count": len(retry),
            "failed_branch_count": len(failed),
            "advisory_gap_count": len(advisory),
            "coverage_ready": coverage_ready,
            "coverage_target_count": coverage_target_count,
            "covered_question_count": covered_question_count,
            "coverage_score": coverage_score,
            "coverage_by_question": coverage_by_question,
            "uncovered_questions": uncovered_questions,
            "recommended_gap_queries": _dedupe_texts(
                query
                for question in uncovered_questions
                for query in recommended_gap_queries_by_question.get(question, [])
            ),
            "recommended_gap_queries_by_question": recommended_gap_queries_by_question,
            "coverage_question_task_ids": coverage_question_task_ids,
            "coverage_target_source": str(runtime_state.get("coverage_target_source") or ""),
            "retry_task_ids": [item.get("task_id") for item in retry if item.get("task_id")],
            "passed_task_ids": [item.get("task_id") for item in passed if item.get("task_id")],
            "validation_summary_ids": [item.get("id") for item in validations if item.get("id")],
            "ready_task_count": queue.ready_count(),
            "source_count": len(store.all_sources()),
        }

    def _quality_summary(self, queue: ResearchTaskQueue, store: LightweightArtifactStore, runtime_state: dict[str, Any]) -> dict[str, Any]:
        aggregate = self._aggregate_sections(queue, store, runtime_state)
        certified_section_count = int(aggregate.get("certified_section_count") or 0)
        required_section_count = int(aggregate.get("required_section_count") or 0)
        source_count = int(aggregate.get("source_count") or 0)
        coverage_score = round(certified_section_count / max(1, required_section_count), 3) if required_section_count else 0.0
        missing_section_ids = _dedupe_texts(aggregate.get("missing_section_ids") or [])
        final_claim_gate_summary = runtime_state.get("final_claim_gate_summary")
        claim_gate = final_claim_gate_summary if isinstance(final_claim_gate_summary, dict) else {}
        return {
            "section_count": required_section_count,
            "certified_section_count": certified_section_count,
            "pending_section_count": int(aggregate.get("pending_section_count") or 0),
            "blocked_section_count": int(aggregate.get("blocked_section_count") or 0),
            "advisory_issue_count": int(aggregate.get("advisory_issue_count") or 0),
            "blocking_issue_count": int(aggregate.get("blocking_issue_count") or 0),
            "coverage_ready": bool(aggregate.get("outline_ready")),
            "missing_section_ids": missing_section_ids,
            "coverage_summary": {
                "ready": bool(aggregate.get("outline_ready")),
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
            "claim_verifier_total": int(claim_gate.get("claim_verifier_total") or 0),
            "claim_verifier_verified": int(claim_gate.get("claim_verifier_verified") or 0),
            "claim_verifier_unsupported": int(claim_gate.get("claim_verifier_unsupported") or 0),
            "claim_verifier_contradicted": int(claim_gate.get("claim_verifier_contradicted") or 0),
        }

    def _research_topology_snapshot(
        self,
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
            "topic": self.topic,
            "engine": "multi_agent",
            "graph_run_id": self.graph_run_id,
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
                    "validation_status": "certified"
                    if bool(certifications_by_section.get(str(task.section_id or ""), {}).get("certified"))
                    else str(
                        (runtime_state.get("section_status_map") or {}).get(str(task.section_id or "")) or "pending"
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
            final_claim_gate_summary = runtime_state_snapshot.get("final_claim_gate_summary")
            if isinstance(final_claim_gate_summary, dict) and final_claim_gate_summary:
                return "finalize"
            return "final_claim_gate"
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
                for item in certifications if isinstance(certifications, list) and isinstance(item, dict)
            }
            for draft in section_drafts:
                if not isinstance(draft, dict):
                    continue
                section_id = str(draft.get("section_id") or "").strip()
                if section_id and section_id not in certified_ids:
                    return "reviewer"
        outline_gate_summary = runtime_state_snapshot.get("outline_gate_summary")
        if isinstance(outline_gate_summary, dict) and bool(outline_gate_summary.get("outline_ready")):
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
            "final_claim_gate",
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
        return self._patch(parts, next_step="outline_plan")

    def _outline_plan_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        approved_scope = copy.deepcopy(parts.runtime_state.get("approved_scope_draft") or {})
        if not approved_scope:
            return self._patch(parts, next_step="scope_review")
        scope = parts.artifact_store.scope()
        if not scope:
            return self._patch(parts, next_step="research_brief")
        if parts.artifact_store.outline():
            if parts.task_queue.ready_count() > 0:
                return self._patch(parts, next_step="dispatch")
            return self._patch(parts, next_step="reviewer")

        parts.runtime_state["active_agent"] = "supervisor"
        record = self._start_agent_run(parts, role="supervisor", phase="outline_plan", attempt=self.graph_attempt)
        if hasattr(self.supervisor, "create_outline_plan"):
            outline = self.supervisor.create_outline_plan(self.topic, approved_scope=scope)
        else:
            outline = self._fallback_outline_plan(scope)
        sections = self._outline_sections(outline)
        tasks = self._build_outline_tasks(outline=outline, scope=scope)
        if not tasks:
            parts.runtime_state["terminal_status"] = "blocked"
            parts.runtime_state["terminal_reason"] = "outline plan produced no executable tasks"
            self._finish_agent_run(parts, record, status="completed", summary=parts.runtime_state["terminal_reason"])
            return self._patch(parts, next_step="finalize")

        parts.artifact_store.set_outline(outline)
        parts.runtime_state["outline_id"] = str(outline.get("id") or "")
        parts.runtime_state["section_status_map"] = {
            str(section.get("id") or ""): "planned"
            for section in sections
            if str(section.get("id") or "")
        }
        parts.task_queue.enqueue(tasks)
        plan_artifact = self._build_plan_artifact(scope, tasks)
        plan_artifact["outline_id"] = str(outline.get("id") or "")
        plan_artifact["required_section_ids"] = list(outline.get("required_section_ids") or [])
        parts.artifact_store.set_plan(plan_artifact)
        parts.runtime_state["plan_id"] = str(plan_artifact.get("id") or "")
        parts.runtime_state["supervisor_phase"] = "outline_plan"
        self._emit_artifact_update(
            artifact_id=str(outline.get("id") or support._new_id("outline")),
            artifact_type="outline",
            summary=f"generated {len(sections)} required sections",
            iteration=max(1, parts.current_iteration or 1),
            extra={
                "required_section_ids": list(outline.get("required_section_ids") or []),
                "section_count": len(sections),
            },
        )
        self._emit_artifact_update(
            artifact_id=str(plan_artifact.get("id") or support._new_id("plan")),
            artifact_type="plan",
            summary=f"generated {len(tasks)} section tasks",
            iteration=max(1, parts.current_iteration or 1),
        )
        for task in tasks:
            self._emit_task_update(task, task.status, iteration=max(1, parts.current_iteration or 1))
        self._emit_decision("outline_plan", f"generated {len(sections)} required sections", iteration=max(1, parts.current_iteration or 1))
        self._finish_agent_run(parts, record, status="completed", summary=f"generated {len(sections)} sections")
        return self._patch(parts, next_step="dispatch")

    def _supervisor_plan_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        return self._outline_plan_node(graph_state)

    def _route_after_supervisor_plan(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "dispatch").strip().lower()
        if next_step in {"scope_review", "research_brief", "dispatch", "reviewer", "finalize"}:
            return next_step
        return "dispatch"

    def _dispatch_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        budget_stop_reason = self._budget_stop_reason(parts.runtime_state)
        if budget_stop_reason:
            parts.runtime_state["budget_stop_reason"] = budget_stop_reason
            self._emit_decision("budget_stop", budget_stop_reason, iteration=max(1, parts.current_iteration or 1))
            return self._patch(parts, next_step="reviewer")

        if parts.task_queue.ready_count() == 0:
            return self._patch(parts, next_step="reviewer")

        parts.current_iteration += 1
        parts.runtime_state["current_iteration"] = parts.current_iteration
        claimed = parts.task_queue.claim_ready_tasks(
            limit=self.parallel_workers,
            agent_ids=[self._next_agent_id("researcher", parts.runtime_state) for _ in range(self.parallel_workers)],
        )
        for task in claimed:
            self._emit_task_update(task, "in_progress", iteration=parts.current_iteration)
        self._emit_decision("research", "dispatch ready section tasks", iteration=parts.current_iteration)
        return self._patch(
            parts,
            next_step="reviewer",
            pending_worker_tasks=[task.to_dict() for task in claimed],
            worker_results=[{"__reset__": True}],
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
        parts.runtime_state["active_agent"] = "supervisor"
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
        try:
            task.stage = "search"
            self._emit_task_update(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="search")
            outcome = self.researcher.research_branch(
                task,
                topic=self.topic,
                existing_summary="\n".join(parts.shared_state.get("summary_notes", [])[:6]),
                max_results_per_query=self.results_per_query,
            )
            results = list(outcome.get("search_results") or [])
            if not results:
                raise RuntimeError("section researcher returned no evidence")
            task.stage = "read"
            self._emit_task_update(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="read")
            task.stage = "extract"
            self._emit_task_update(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="extract")
            task.stage = "synthesize"
            self._emit_task_update(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="synthesize")
            summary = str(outcome.get("summary") or "").strip() or f"未能为 {_branch_title(task)} 形成有效章节摘要。"
            bundle = self._build_evidence_bundle(task, outcome, str(record.get("agent_id") or "researcher"))
            section_draft = self._build_section_draft(
                task,
                section,
                bundle,
                outcome,
                str(record.get("agent_id") or "researcher"),
            )
            self._finish_agent_run(parts, record, status="completed", summary=summary, stage="synthesize")
            return {
                "worker_results": [
                    {
                        "task": task.to_dict(),
                        "result_status": "completed",
                        "section_draft": section_draft,
                        "evidence_bundle": bundle,
                        "raw_results": copy.deepcopy(results),
                        "tokens_used": (
                            support._estimate_tokens_from_results(results)
                            + sum(
                                support._estimate_tokens_from_text(str(item.get("content") or "")[:800])
                                for item in bundle.get("documents", [])[:3]
                                if isinstance(item, dict)
                            )
                            + support._estimate_tokens_from_text(summary)
                        ),
                        "searches_used": len(outcome.get("queries") or task.query_hints or [task.query]),
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

    def _revisor_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        payload = graph_state.get("worker_task") or {}
        task_payload = payload.get("task") if isinstance(payload, dict) else None
        task = ResearchTask(**task_payload) if isinstance(task_payload, dict) else ResearchTask(**payload)
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
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
            revised_draft["id"] = support._new_id("section_draft")
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
            self._emit_task_update(task, "in_progress", iteration=max(1, parts.current_iteration or 1), reason="revision")
            self._finish_agent_run(parts, record, status="completed", summary=revised_summary, stage="revision")
            return {
                "worker_results": [
                    {
                        "task": task.to_dict(),
                        "result_status": "completed",
                        "section_draft": revised_draft,
                        "raw_results": [],
                        "tokens_used": support._estimate_tokens_from_text(revised_summary),
                        "searches_used": 0,
                        "agent_run": copy.deepcopy(record),
                    }
                ]
            }
        except Exception as exc:
            self._finish_agent_run(parts, record, status="failed", summary=str(exc), stage=task.stage or "revision")
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
                role = str(agent_run.get("role") or "").strip()
                if role:
                    role_tool_policies = dict(parts.runtime_state.get("role_tool_policies") or {})
                    role_tool_policies[role] = {
                        "role": role,
                        "requested_tools": list(agent_run.get("requested_tools") or []),
                        "allowed_tool_names": list(agent_run.get("resolved_tools") or []),
                    }
                    parts.runtime_state["role_tool_policies"] = role_tool_policies
            parts.runtime_state["searches_used"] = int(parts.runtime_state.get("searches_used") or 0) + int(payload.get("searches_used") or 0)
            parts.runtime_state["tokens_used"] = int(parts.runtime_state.get("tokens_used") or 0) + int(payload.get("tokens_used") or 0)
            task = ResearchTask(**payload["task"])
            if payload.get("result_status") == "completed":
                bundle = copy.deepcopy(payload.get("evidence_bundle") or {})
                section_draft = copy.deepcopy(payload.get("section_draft") or {})
                if bundle:
                    parts.artifact_store.set_evidence_bundle(bundle)
                if section_draft:
                    parts.artifact_store.set_section_draft(section_draft)
                updated_task = parts.task_queue.update_status(task.id, "completed")
                if updated_task:
                    self._emit_task_update(updated_task, "completed", iteration=max(1, parts.current_iteration or 1))
                if task.section_id:
                    parts.runtime_state["section_status_map"] = {
                        **dict(parts.runtime_state.get("section_status_map") or {}),
                        str(task.section_id): "drafted",
                    }
                parts.shared_state["summary_notes"] = [
                    *(parts.shared_state.get("summary_notes") or []),
                    str(section_draft.get("summary") or ""),
                ]
                if bundle:
                    parts.shared_state["sources"] = [
                        *(parts.shared_state.get("sources") or []),
                        *(bundle.get("sources") or []),
                    ]
                parts.shared_state["scraped_content"] = [
                    *(parts.shared_state.get("scraped_content") or []),
                    {
                        "task_id": task.id,
                        "section_id": task.section_id,
                        "query": task.query,
                        "results": copy.deepcopy(payload.get("raw_results") or []),
                        "summary": section_draft.get("summary"),
                    },
                ]
                if bundle:
                    self._emit_artifact_update(
                        artifact_id=str(bundle.get("id") or support._new_id("bundle")),
                        artifact_type="evidence_bundle",
                        summary=f"{len(bundle.get('sources', []))} sources",
                        task_id=task.id,
                        section_id=task.section_id,
                        branch_id=task.branch_id,
                        iteration=max(1, parts.current_iteration or 1),
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
                    self._emit_artifact_update(
                        artifact_id=str(section_draft.get("id") or support._new_id("section_draft")),
                        artifact_type="section_draft",
                        summary=str(section_draft.get("summary") or ""),
                        task_id=task.id,
                        section_id=task.section_id,
                        branch_id=task.branch_id,
                        iteration=max(1, parts.current_iteration or 1),
                        extra={
                            "title": str(section_draft.get("title") or ""),
                            "source_urls": list(section_draft.get("source_urls") or []),
                            "finding_count": len(section_draft.get("key_findings") or []),
                        },
                    )
            else:
                reason = str(payload.get("error") or "researcher returned no results")
                failed_task = parts.task_queue.update_stage(task.id, task.stage or "search", status="failed", reason=reason)
                if failed_task:
                    self._emit_task_update(failed_task, "failed", iteration=max(1, parts.current_iteration or 1), reason=reason)
                if task.task_kind == "section_revision":
                    if task.section_id:
                        parts.runtime_state["section_status_map"] = {
                            **dict(parts.runtime_state.get("section_status_map") or {}),
                            str(task.section_id): "drafted",
                        }
                elif task.attempts < self.task_retry_limit and not parts.runtime_state.get("budget_stop_reason"):
                    retry_task = parts.task_queue.update_stage(task.id, "planned", status="ready", reason=reason)
                    if retry_task:
                        self._emit_task_update(retry_task, "ready", iteration=max(1, parts.current_iteration or 1), reason=reason)
                parts.shared_state["errors"] = [
                    *(parts.shared_state.get("errors") or []),
                    reason,
                ]
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
        active_task_keys = {
            (str(task.section_id or "").strip(), str(task.task_kind or "").strip())
            for task in parts.task_queue.all_tasks()
            if task.status in {"ready", "in_progress"}
        }
        for draft in parts.artifact_store.section_drafts():
            section_id = str(draft.get("section_id") or "").strip()
            if not section_id:
                continue
            certification = parts.artifact_store.section_certification(section_id)
            if bool(certification.get("certified")):
                continue
            review = parts.artifact_store.section_review(section_id)
            if review and str(review.get("task_id") or "") == str(draft.get("task_id") or "") and str(draft.get("review_status") or "").strip() != "pending":
                continue
            section = section_map.get(section_id, {})
            bundle = parts.artifact_store.evidence_bundle(str(draft.get("task_id") or ""))
            revision_count = int((parts.runtime_state.get("section_revision_counts") or {}).get(section_id, 0) or 0)
            research_retry_count = int((parts.runtime_state.get("section_research_retry_counts") or {}).get(section_id, 0) or 0)
            review, certification = self._review_section_draft(
                section=section,
                draft=draft,
                bundle=bundle,
                revision_count=revision_count,
            )
            draft["review_artifact_id"] = review.get("id")
            draft["review_status"] = review.get("verdict")
            parts.artifact_store.set_section_review(review)
            self._emit_artifact_update(
                artifact_id=str(review.get("id") or support._new_id("section_review")),
                artifact_type="section_review",
                summary=str(review.get("notes") or review.get("verdict") or ""),
                task_id=str(draft.get("task_id") or ""),
                section_id=section_id,
                branch_id=draft.get("branch_id"),
                iteration=max(1, parts.current_iteration or 1),
                extra={
                    "review_verdict": review.get("verdict"),
                    "blocking_issue_count": len(review.get("blocking_issues") or []),
                    "advisory_issue_count": len(review.get("advisory_issues") or []),
                },
            )
            verdict = str(review.get("verdict") or "").strip()
            if certification:
                draft["certified"] = True
                draft["certification_artifact_id"] = certification.get("id")
                draft["limitations"] = _dedupe_texts(
                    [*list(draft.get("limitations") or []), *list(certification.get("limitations") or [])]
                )
                parts.artifact_store.set_section_certification(certification)
                self._emit_artifact_update(
                    artifact_id=str(certification.get("id") or support._new_id("section_certification")),
                    artifact_type="section_certification",
                    summary="section certified",
                    task_id=str(draft.get("task_id") or ""),
                    section_id=section_id,
                    branch_id=draft.get("branch_id"),
                    iteration=max(1, parts.current_iteration or 1),
                    extra={
                        "certified": True,
                        "limitations": list(certification.get("limitations") or []),
                    },
                )
                parts.runtime_state["section_status_map"] = {
                    **dict(parts.runtime_state.get("section_status_map") or {}),
                    section_id: "certified",
                }
            elif verdict == "revise_section":
                parts.runtime_state["section_status_map"] = {
                    **dict(parts.runtime_state.get("section_status_map") or {}),
                    section_id: "revising",
                }
                if (section_id, "section_revision") not in active_task_keys:
                    revision_task = self._build_revision_task(
                        section=section,
                        draft=draft,
                        review=review,
                        scope=parts.artifact_store.scope(),
                        revision_count=revision_count,
                    )
                    parts.task_queue.enqueue([revision_task])
                    parts.runtime_state["section_revision_counts"] = {
                        **dict(parts.runtime_state.get("section_revision_counts") or {}),
                        section_id: revision_count + 1,
                    }
                    active_task_keys.add((section_id, "section_revision"))
                    self._emit_task_update(revision_task, revision_task.status, iteration=max(1, parts.current_iteration or 1), reason="review_revision")
            elif verdict == "request_research":
                if research_retry_count < self.task_retry_limit and not parts.runtime_state.get("budget_stop_reason"):
                    parts.runtime_state["section_status_map"] = {
                        **dict(parts.runtime_state.get("section_status_map") or {}),
                        section_id: "research_retry",
                    }
                    if (section_id, "section_research") not in active_task_keys:
                        retry_task = self._build_research_retry_task(
                            section=section,
                            draft=draft,
                            review=review,
                            scope=parts.artifact_store.scope(),
                        )
                        parts.task_queue.enqueue([retry_task])
                        parts.runtime_state["section_research_retry_counts"] = {
                            **dict(parts.runtime_state.get("section_research_retry_counts") or {}),
                            section_id: research_retry_count + 1,
                        }
                        active_task_keys.add((section_id, "section_research"))
                        self._emit_task_update(retry_task, retry_task.status, iteration=max(1, parts.current_iteration or 1), reason="review_research_retry")
                else:
                    parts.runtime_state["section_status_map"] = {
                        **dict(parts.runtime_state.get("section_status_map") or {}),
                        section_id: "blocked",
                    }
            elif verdict == "block_section":
                parts.runtime_state["section_status_map"] = {
                    **dict(parts.runtime_state.get("section_status_map") or {}),
                    section_id: "blocked",
                }
            parts.artifact_store.set_section_draft(draft)

        aggregate = self._aggregate_sections(parts.task_queue, parts.artifact_store, parts.runtime_state)
        parts.runtime_state["last_review_summary"] = aggregate
        parts.runtime_state["outline_gate_summary"] = copy.deepcopy(aggregate)
        decision_type = "review_passed" if aggregate.get("outline_ready") else "review_updated"
        self._emit_decision(decision_type, "section review updated", iteration=max(1, parts.current_iteration or 1), extra=aggregate)
        self._emit(ToolEventType.QUALITY_UPDATE, self._quality_summary(parts.task_queue, parts.artifact_store, parts.runtime_state))
        self._finish_agent_run(parts, record, status="completed", summary="section review updated")
        return self._patch(parts, next_step="supervisor_decide")

    def _verify_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        return self._reviewer_node(graph_state)

    def _supervisor_decide_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        aggregate = self._aggregate_sections(parts.task_queue, parts.artifact_store, parts.runtime_state)
        reportable_sections = self._build_report_sections(parts.artifact_store)
        budget_stop_reason = self._budget_stop_reason(parts.runtime_state)
        previous_budget_stop_reason = str(parts.runtime_state.get("budget_stop_reason") or "")
        parts.runtime_state["budget_stop_reason"] = budget_stop_reason
        if budget_stop_reason and budget_stop_reason != previous_budget_stop_reason:
            self._emit_decision("budget_stop", budget_stop_reason, iteration=max(1, parts.current_iteration or 1))
        if parts.task_queue.ready_count() > 0 and parts.current_iteration < self.max_epochs and not budget_stop_reason:
            return self._patch(parts, next_step="dispatch")
        if hasattr(self.supervisor, "decide_section_action"):
            decision = self.supervisor.decide_section_action(
                outline=parts.artifact_store.outline(),
                section_status_map=dict(parts.runtime_state.get("section_status_map") or {}),
                budget_stop_reason=budget_stop_reason,
            )
            raw_action = getattr(decision, "action", "")
            decision_action = str(getattr(raw_action, "value", raw_action) or "").strip().lower()
            decision_reason = str(getattr(decision, "reasoning", "") or "").strip()
        else:
            decision = self._fallback_section_decision(
                outline=parts.artifact_store.outline(),
                section_status_map=dict(parts.runtime_state.get("section_status_map") or {}),
                budget_stop_reason=budget_stop_reason,
            )
            decision_action = str(decision.get("action") or "").strip().lower()
            decision_reason = str(decision.get("reasoning") or "").strip()
        if decision_action == "report" and bool(aggregate.get("outline_ready")):
            parts.runtime_state["terminal_status"] = ""
            parts.runtime_state["terminal_reason"] = ""
            self._emit_decision("report", decision_reason, iteration=max(1, parts.current_iteration or 1), extra=aggregate)
            return self._patch(parts, next_step="outline_gate")
        if reportable_sections:
            parts.runtime_state["terminal_status"] = ""
            parts.runtime_state["terminal_reason"] = ""
            self._emit_decision(
                "report_partial",
                decision_reason or budget_stop_reason or "using best available section drafts",
                iteration=max(1, parts.current_iteration or 1),
                extra={
                    **aggregate,
                    "reportable_section_count": len(reportable_sections),
                },
            )
            return self._patch(parts, next_step="outline_gate")
        parts.runtime_state["terminal_status"] = "blocked"
        if budget_stop_reason:
            parts.runtime_state["terminal_reason"] = budget_stop_reason
        elif aggregate.get("blocked_section_count"):
            parts.runtime_state["terminal_reason"] = "required sections remain blocked"
        elif aggregate.get("pending_section_count"):
            parts.runtime_state["terminal_reason"] = "required sections are not yet certified"
        else:
            parts.runtime_state["terminal_reason"] = decision_reason or "no certified sections available"
        self._emit_decision("stop", parts.runtime_state["terminal_reason"], iteration=max(1, parts.current_iteration or 1))
        return self._patch(parts, next_step="finalize")

    def _route_after_supervisor_decide(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "report").strip().lower()
        if next_step in {"dispatch", "outline_gate", "report", "finalize"}:
            return next_step
        return "report"

    def _outline_gate_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        aggregate = self._aggregate_sections(parts.task_queue, parts.artifact_store, parts.runtime_state)
        parts.runtime_state["outline_gate_summary"] = aggregate
        reportable_sections = self._build_report_sections(parts.artifact_store)
        if not bool(aggregate.get("outline_ready")):
            if reportable_sections:
                parts.runtime_state["terminal_status"] = ""
                parts.runtime_state["terminal_reason"] = ""
                self._emit_decision(
                    "outline_partial",
                    "required sections are incomplete; generating a partial report with limitations",
                    iteration=max(1, parts.current_iteration or 1),
                    extra={
                        **aggregate,
                        "reportable_section_count": len(reportable_sections),
                    },
                )
                return self._patch(parts, next_step="report")
            parts.runtime_state["terminal_status"] = "blocked"
            parts.runtime_state["terminal_reason"] = "required sections are not fully certified"
            return self._patch(parts, next_step="finalize")
        parts.runtime_state["terminal_status"] = ""
        parts.runtime_state["terminal_reason"] = ""
        self._emit_decision("outline_ready", "certified sections ready for final report", iteration=max(1, parts.current_iteration or 1), extra=aggregate)
        return self._patch(parts, next_step="report")

    def _report_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "supervisor"
        record = self._start_agent_run(parts, role="reporter", phase="report", attempt=self.graph_attempt)
        report_sections = self._build_report_sections(parts.artifact_store)
        if not report_sections:
            self._finish_agent_run(parts, record, status="failed", summary="no reportable sections")
            return self._patch(parts, next_step="finalize")

        all_sources = [
            ReportSource(
                url=str(item.get("url") or ""),
                title=str(item.get("title") or item.get("url") or ""),
                provider=str(item.get("provider") or ""),
                published_date=item.get("published_date"),
            )
            for item in parts.artifact_store.all_sources()
            if str(item.get("url") or "").strip()
        ]
        referenced_urls: list[str] = []
        seen_referenced_urls: set[str] = set()
        for section in report_sections:
            for raw_url in section.citation_urls:
                normalized_url = canonicalize_source_url(raw_url)
                if not normalized_url or normalized_url in seen_referenced_urls:
                    continue
                seen_referenced_urls.add(normalized_url)
                referenced_urls.append(normalized_url)

        if referenced_urls:
            source_by_url = {
                canonicalize_source_url(source.url): source
                for source in all_sources
                if canonicalize_source_url(source.url)
            }
            sources = [
                source_by_url.get(url) or ReportSource(url=url, title=url)
                for url in referenced_urls
            ]
        else:
            sources = all_sources

        report_context = ReportContext(topic=self.topic, sections=report_sections, sources=sources)
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
        return self._patch(parts, next_step="final_claim_gate")

    def _final_claim_gate_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        parts = self._unpack(graph_state)
        parts.runtime_state["active_agent"] = "verifier"
        record = self._start_agent_run(parts, role="verifier", phase="final_claim_gate", attempt=self.graph_attempt)
        final_artifact = parts.artifact_store.final_report()
        report = str(final_artifact.get("report_markdown") or "")
        if not report.strip():
            self._finish_agent_run(parts, record, status="completed", summary="no final report to verify")
            return self._patch(parts, next_step="finalize")

        try:
            from agent.contracts.claim_verifier import ClaimStatus, ClaimVerifier

            verifier = ClaimVerifier()
            passages = [
                item
                for item in self._normalize_passages_for_claim_gate(parts.artifact_store)
                if isinstance(item, dict)
            ]
            checks = verifier.verify_report(
                report,
                list(parts.shared_state.get("scraped_content") or []),
                passages=passages,
            )
            contradicted = [item for item in checks if item.status == ClaimStatus.CONTRADICTED]
            unsupported = [item for item in checks if item.status == ClaimStatus.UNSUPPORTED]
            verified = [item for item in checks if item.status == ClaimStatus.VERIFIED]
            gate_summary = {
                "claim_verifier_total": len(checks),
                "claim_verifier_verified": len(verified),
                "claim_verifier_unsupported": len(unsupported),
                "claim_verifier_contradicted": len(contradicted),
                "passed": len(contradicted) == 0,
                "review_needed": bool(contradicted or unsupported),
            }
            parts.runtime_state["final_claim_gate_summary"] = gate_summary
            parts.runtime_state["terminal_status"] = ""
            parts.runtime_state["terminal_reason"] = ""
            if contradicted or unsupported:
                self._emit_decision(
                    "final_claim_gate_review_needed",
                    "final claim gate found claims that need manual review",
                    iteration=max(1, parts.current_iteration or 1),
                    extra=gate_summary,
                )
            else:
                self._emit_decision("final_claim_gate_passed", "final claim gate passed", iteration=max(1, parts.current_iteration or 1), extra=gate_summary)
            self._finish_agent_run(parts, record, status="completed", summary="final claim gate completed")
        except Exception as exc:
            parts.runtime_state["final_claim_gate_summary"] = {"error": str(exc), "passed": False}
            self._finish_agent_run(parts, record, status="failed", summary=str(exc))
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
        workflow.add_node("outline_plan", self._outline_plan_node)
        workflow.add_node("dispatch", self._dispatch_node)
        workflow.add_node("researcher", self._researcher_node)
        workflow.add_node("revisor", self._revisor_node)
        workflow.add_node("merge", self._merge_node)
        workflow.add_node("reviewer", self._reviewer_node)
        workflow.add_node("supervisor_decide", self._supervisor_decide_node)
        workflow.add_node("outline_gate", self._outline_gate_node)
        workflow.add_node("report", self._report_node)
        workflow.add_node("final_claim_gate", self._final_claim_gate_node)
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
                "final_claim_gate",
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
        workflow.add_edge("report", "final_claim_gate")
        workflow.add_edge("final_claim_gate", "finalize")
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
    "GapAnalysisResult",
    "MultiAgentDeepResearchRuntime",
    "_format_scope_draft_markdown",
    "run_multi_agent_deep_research",
]
