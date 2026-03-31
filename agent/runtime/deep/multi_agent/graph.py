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
    BranchSynthesis,
    EvidenceCard,
    EvidencePassage,
    FetchedDocument,
    FinalReportArtifact,
    GraphScopeSnapshot,
    KnowledgeGap,
    ReportSectionDraft,
    ResearchTask,
    SourceCandidate,
    ScopeDraft,
    VerificationResult,
    WorkerExecutionResult,
    WorkerScopeSnapshot,
    _now_iso,
)
from agent.runtime.deep.multi_agent.store import ArtifactStore, ResearchTaskQueue
from agent.workflows.agents.coordinator import CoordinatorAction
from agent.workflows.claim_verifier import ClaimStatus, ClaimVerifier
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
    latest_verification_summary: dict[str, Any]
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
    source_candidates = [SourceCandidate(**item) for item in payload.get("source_candidates", [])]
    fetched_documents = [FetchedDocument(**item) for item in payload.get("fetched_documents", [])]
    evidence_passages = [EvidencePassage(**item) for item in payload.get("evidence_passages", [])]
    synthesis_payload = payload.get("branch_synthesis")
    branch_synthesis = BranchSynthesis(**synthesis_payload) if isinstance(synthesis_payload, dict) else None
    evidence_cards = [EvidenceCard(**item) for item in payload.get("evidence_cards", [])]
    section_payload = payload.get("section_draft")
    section_draft = ReportSectionDraft(**section_payload) if isinstance(section_payload, dict) else None
    agent_run_payload = payload.get("agent_run")
    agent_run = AgentRunRecord(**agent_run_payload) if isinstance(agent_run_payload, dict) else None
    return WorkerExecutionResult(
        task=task,
        context=context,
        source_candidates=source_candidates,
        fetched_documents=fetched_documents,
        evidence_passages=evidence_passages,
        branch_synthesis=branch_synthesis,
        evidence_cards=evidence_cards,
        section_draft=section_draft,
        raw_results=list(payload.get("raw_results", [])),
        tokens_used=int(payload.get("tokens_used", 0) or 0),
        searches_used=int(payload.get("searches_used", 0) or 0),
        branch_id=payload.get("branch_id"),
        task_stage=str(payload.get("task_stage") or task.stage or ""),
        result_status=str(payload.get("result_status") or "completed"),
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


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _split_findings(summary: str) -> list[str]:
    text = str(summary or "").strip()
    if not text:
        return []
    parts = [item.strip(" -•\t") for item in text.replace("\r", "\n").split("\n") if item.strip()]
    findings = [part for part in parts if len(part) >= 12]
    if findings:
        return findings[:6]
    return [text[:300]]


def _derive_branch_queries(task: ResearchTask, limit: int = 3) -> list[str]:
    candidates = list(task.query_hints or [])
    if not candidates and task.query:
        candidates.append(task.query)
    if not candidates and task.objective:
        candidates.append(task.objective)
    if not candidates and task.title:
        candidates.append(task.title)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def _criterion_is_covered(summary: str, criterion: str) -> bool:
    criterion_text = str(criterion or "").strip().lower()
    summary_text = str(summary or "").strip().lower()
    if not criterion_text or not summary_text:
        return False
    tokens = [token for token in criterion_text.replace("，", " ").replace(",", " ").split() if len(token) > 1]
    if not tokens:
        return criterion_text in summary_text
    matches = sum(1 for token in tokens if token in summary_text)
    return matches >= max(1, min(2, len(tokens)))


def _scope_draft_from_payload(payload: dict[str, Any] | None) -> ScopeDraft | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return ScopeDraft(
        id=str(payload.get("id") or support._new_id("scope")),
        version=max(1, int(payload.get("version", 1) or 1)),
        topic=str(payload.get("topic") or ""),
        research_goal=str(payload.get("research_goal") or ""),
        research_steps=_coerce_string_list(payload.get("research_steps")),
        core_questions=_coerce_string_list(payload.get("core_questions")),
        in_scope=_coerce_string_list(payload.get("in_scope")),
        out_of_scope=_coerce_string_list(payload.get("out_of_scope")),
        constraints=_coerce_string_list(payload.get("constraints")),
        source_preferences=_coerce_string_list(payload.get("source_preferences")),
        deliverable_preferences=_coerce_string_list(payload.get("deliverable_preferences")),
        assumptions=_coerce_string_list(payload.get("assumptions")),
        intake_summary=copy.deepcopy(payload.get("intake_summary") or {}),
        feedback=str(payload.get("feedback") or ""),
        status=str(payload.get("status") or "awaiting_review"),
        created_by=str(payload.get("created_by") or "scope"),
        created_at=str(payload.get("created_at") or _now_iso()),
        updated_at=str(payload.get("updated_at") or _now_iso()),
    )


def _scope_version(payload: dict[str, Any] | None) -> int:
    draft = _scope_draft_from_payload(payload)
    return int(draft.version) if draft else 0


def _format_scope_draft_markdown(payload: dict[str, Any] | ScopeDraft | None) -> str:
    draft = payload if isinstance(payload, ScopeDraft) else _scope_draft_from_payload(payload)
    if not draft:
        return ""

    research_steps = list(draft.research_steps or [])
    if not research_steps:
        focus_items = draft.in_scope or draft.core_questions or [draft.research_goal or draft.topic]
        focus_text = "; ".join(item for item in focus_items[:3] if item) or (draft.research_goal or draft.topic)
        question_text = "; ".join(item for item in draft.core_questions[:3] if item)
        research_steps = [
            f"先确认这次调研的目标与覆盖范围, 重点聚焦: {focus_text}.",
            (
                f"围绕这些关键问题收集最新信息与事实依据: {question_text}."
                if question_text
                else f'围绕"{draft.research_goal or draft.topic}"拆解关键问题并补齐必要背景信息.'
            ),
            "对比不同来源中的数据, 观点和时间线, 识别主要趋势, 差异与潜在风险.",
            "最后整合证据, 输出结构化结论与可执行建议.",
        ]

    sections = [
        f"# 研究计划草案 v{draft.version}",
        "",
        "如果按这个方向开始调研, 我会大致这样推进:",
        "",
    ]
    sections.extend(f"{index}. {item}" for index, item in enumerate(research_steps, 1))
    if draft.feedback:
        sections.extend(
            [
                "",
                "已吸收的最新修改要求:",
                f"> {draft.feedback}",
            ]
        )
    return "\n".join(sections)


def _extract_interrupt_text(
    payload: Any,
    *,
    keys: tuple[str, ...],
) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _build_scope_draft(
    *,
    topic: str,
    version: int,
    draft_payload: dict[str, Any],
    intake_summary: dict[str, Any],
    feedback: str,
    agent_id: str,
    previous: dict[str, Any] | None = None,
) -> ScopeDraft:
    previous_draft = _scope_draft_from_payload(previous)
    return ScopeDraft(
        id=previous_draft.id if previous_draft else support._new_id("scope"),
        version=max(1, int(version or 1)),
        topic=topic,
        research_goal=str(
            draft_payload.get("research_goal")
            or (previous_draft.research_goal if previous_draft else "")
            or topic
        ).strip()
        or topic,
        research_steps=_coerce_string_list(draft_payload.get("research_steps"))
        or (previous_draft.research_steps if previous_draft else []),
        core_questions=_coerce_string_list(draft_payload.get("core_questions"))
        or (previous_draft.core_questions if previous_draft else []),
        in_scope=_coerce_string_list(draft_payload.get("in_scope"))
        or (previous_draft.in_scope if previous_draft else []),
        out_of_scope=_coerce_string_list(draft_payload.get("out_of_scope"))
        or (previous_draft.out_of_scope if previous_draft else []),
        constraints=_coerce_string_list(draft_payload.get("constraints"))
        or _coerce_string_list(intake_summary.get("constraints"))
        or (previous_draft.constraints if previous_draft else []),
        source_preferences=_coerce_string_list(draft_payload.get("source_preferences"))
        or _coerce_string_list(intake_summary.get("source_preferences"))
        or (previous_draft.source_preferences if previous_draft else []),
        deliverable_preferences=_coerce_string_list(draft_payload.get("deliverable_preferences"))
        or (previous_draft.deliverable_preferences if previous_draft else []),
        assumptions=_coerce_string_list(draft_payload.get("assumptions"))
        or (previous_draft.assumptions if previous_draft else []),
        intake_summary=copy.deepcopy(intake_summary),
        feedback=feedback,
        status="awaiting_review",
        created_by=agent_id,
    )


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
        self.runtime_state.setdefault("last_verification_summary", {})
        self.runtime_state.setdefault("intake_status", "pending")
        self.runtime_state.setdefault("clarify_question", "")
        self.runtime_state.setdefault("clarify_question_history", [])
        self.runtime_state.setdefault("clarify_answer_history", [])
        self.runtime_state.setdefault("intake_summary", {})
        self.runtime_state.setdefault("scope_revision_count", 0)
        self.runtime_state.setdefault("scope_feedback_history", [])
        self.runtime_state.setdefault("pending_scope_feedback", "")
        self.runtime_state.setdefault("current_scope_draft", {})
        self.runtime_state.setdefault("approved_scope_draft", {})

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
        syntheses = [synthesis.summary for synthesis in self.artifact_store.branch_syntheses() if synthesis.summary]
        if syntheses:
            return "\n\n".join(syntheses[:8])
        sections = [section.summary for section in self.artifact_store.section_drafts() if section.summary]
        if sections:
            return "\n\n".join(sections[:8])
        notes = self.shared_state.get("summary_notes", [])
        if isinstance(notes, list) and notes:
            return "\n\n".join(str(note) for note in notes[:8])
        return ""

    def _quality_summary(self, gap_result: GapAnalysisResult | None) -> dict[str, Any]:
        passages = self.artifact_store.evidence_passages()
        evidence_cards = self.artifact_store.evidence_cards()
        unique_urls = {passage.url for passage in passages if passage.url}
        if not unique_urls:
            unique_urls = {card.source_url for card in evidence_cards if card.source_url}
        syntheses = self.artifact_store.branch_syntheses()
        verification_results = self.artifact_store.verification_results(validation_stage="coverage_check")
        verified_branch_ids = {
            result.branch_id
            for result in verification_results
            if result.branch_id and result.outcome == "passed"
        }
        coverage = float(gap_result.overall_coverage) if gap_result else 0.0
        citation_denominator = max(1, len(passages) or len(evidence_cards) or len(syntheses))
        citation_coverage = min(1.0, len(unique_urls) / citation_denominator) if unique_urls else 0.0
        return {
            "engine": "multi_agent",
            "stage": "final" if self.task_queue.ready_count() == 0 else "iteration",
            "query_coverage_score": coverage,
            "citation_coverage_score": citation_coverage,
            "knowledge_gap_count": len(gap_result.gaps) if gap_result else 0,
            "suggested_queries": gap_result.suggested_queries if gap_result else [],
            "analysis": gap_result.analysis if gap_result else "",
            "freshness_warning": "",
            "verified_branch_count": len(verified_branch_ids),
            "branch_synthesis_count": len(syntheses),
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
                    "title": task.title or task.objective or task.goal,
                    "objective": task.objective,
                    "task_kind": task.task_kind,
                    "stage": task.stage,
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
        current_scope = copy.deepcopy(self.runtime_state.get("current_scope_draft") or {})
        approved_scope = copy.deepcopy(self.runtime_state.get("approved_scope_draft") or {})
        graph_scope: GraphScopeSnapshot = {
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "topic": self.owner.topic,
            "phase": self.current_node_id,
            "current_iteration": self.current_iteration,
            "intake_status": str(self.runtime_state.get("intake_status") or "pending"),
            "scope_revision_count": int(self.runtime_state.get("scope_revision_count", 0) or 0),
            "current_scope_version": _scope_version(current_scope),
            "approved_scope_version": _scope_version(approved_scope),
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
                "source_candidates": len(self.artifact_store.source_candidates()),
                "fetched_documents": len(self.artifact_store.fetched_documents()),
                "evidence_passages": len(self.artifact_store.evidence_passages()),
                "evidence_cards": len(self.artifact_store.evidence_cards()),
                "branch_syntheses": len(self.artifact_store.branch_syntheses()),
                "verification_results": len(self.artifact_store.verification_results()),
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
                "objective": brief.objective,
                "task_kind": brief.task_kind,
                "current_stage": brief.current_stage,
                "verification_status": brief.verification_status,
                "latest_task_id": brief.latest_task_id,
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
                        "objective": str((item.get("brief") or {}).get("objective") or ""),
                        "task_kind": str((item.get("brief") or {}).get("task_kind") or ""),
                        "stage": str((item.get("brief") or {}).get("stage") or ""),
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
            "intake": {
                "clarify_question": str(self.runtime_state.get("clarify_question") or ""),
                "clarify_question_history": copy.deepcopy(
                    self.runtime_state.get("clarify_question_history", [])
                ),
                "clarify_answer_history": copy.deepcopy(
                    self.runtime_state.get("clarify_answer_history", [])
                ),
                "intake_summary": copy.deepcopy(self.runtime_state.get("intake_summary", {})),
                "scope_feedback_history": copy.deepcopy(
                    self.runtime_state.get("scope_feedback_history", [])
                ),
                "current_scope_draft": current_scope,
                "approved_scope_draft": approved_scope,
            },
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
            "last_verification_summary": copy.deepcopy(
                self.runtime_state.get("last_verification_summary", {})
            ),
            "intake_status": str(self.runtime_state.get("intake_status") or "pending"),
            "clarify_question": str(self.runtime_state.get("clarify_question") or ""),
            "clarify_question_history": copy.deepcopy(
                self.runtime_state.get("clarify_question_history", [])
            ),
            "clarify_answer_history": copy.deepcopy(
                self.runtime_state.get("clarify_answer_history", [])
            ),
            "intake_summary": copy.deepcopy(self.runtime_state.get("intake_summary", {})),
            "scope_revision_count": int(self.runtime_state.get("scope_revision_count", 0) or 0),
            "scope_feedback_history": copy.deepcopy(
                self.runtime_state.get("scope_feedback_history", [])
            ),
            "pending_scope_feedback": str(self.runtime_state.get("pending_scope_feedback") or ""),
            "current_scope_draft": copy.deepcopy(self.runtime_state.get("current_scope_draft", {})),
            "approved_scope_draft": copy.deepcopy(self.runtime_state.get("approved_scope_draft", {})),
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
        latest_verification = extra.get("latest_verification_summary")
        if latest_verification is not None:
            self.runtime_state["last_verification_summary"] = copy.deepcopy(latest_verification)
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
            if key in {
                "latest_gap_result",
                "latest_decision",
                "latest_verification_summary",
                "pending_worker_tasks",
                "worker_results",
                "final_result",
            }:
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
        branch_id: str | None = None,
        agent_id: str | None = None,
        summary: str | None = None,
        source_url: str | None = None,
        task_kind: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        events.emit_artifact_update(
            self,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            status=status,
            task_id=task_id,
            branch_id=branch_id,
            agent_id=agent_id,
            summary=summary,
            source_url=source_url,
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            extra=extra,
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
        task_kind: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
        objective_summary: str | None = None,
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
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            objective_summary=objective_summary,
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
        task_kind: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
        objective_summary: str | None = None,
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
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            objective_summary=objective_summary,
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
        branch_id: str | None = None,
        task_id: str | None = None,
        task_kind: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        events.emit_decision(
            self,
            decision_type=decision_type,
            reason=reason,
            iteration=iteration,
            coverage=coverage,
            gap_count=gap_count,
            attempt=attempt,
            branch_id=branch_id,
            task_id=task_id,
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            extra=extra,
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
        task_kind: str = "",
        stage: str = "",
        validation_stage: str = "",
        objective_summary: str = "",
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
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            objective_summary=objective_summary,
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
            task_kind=task_kind or record.task_kind,
            stage=stage or record.stage,
            validation_stage=validation_stage or record.validation_stage,
            objective_summary=objective_summary or record.objective_summary,
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
        stage: str | None = None,
        validation_stage: str | None = None,
    ) -> AgentRunRecord:
        record.status = status
        record.summary = summary
        record.ended_at = _now_iso()
        if stage:
            record.stage = stage
        if validation_stage:
            record.validation_stage = validation_stage
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
            task_kind=record.task_kind,
            stage=record.stage,
            validation_stage=record.validation_stage,
            objective_summary=record.objective_summary,
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
        self.allow_interrupts = bool(self.cfg.get("allow_interrupts"))
        self.resumed_from_checkpoint = bool(
            self.state.get("resumed_from_checkpoint") or self.cfg.get("resumed_from_checkpoint")
        )

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
        self.scope_revision_limit = max(
            1,
            support._configurable_int(self.config, "deepsearch_scope_revision_limit", 3),
        )
        self.max_clarify_rounds = max(
            1,
            support._configurable_int(self.config, "deepsearch_clarify_round_limit", 2),
        )
        self.pause_before_merge = bool(self.cfg.get("deepsearch_pause_before_merge"))

        self.provider_profile = support._resolve_provider_profile(self.state)

        planner_model = support._model_for_task("planning", self.config)
        researcher_model = support._model_for_task("research", self.config)
        reporter_model = support._model_for_task("writing", self.config)
        verifier_model = support._model_for_task("gap_analysis", self.config)
        coordinator_model = support._model_for_task("planning", self.config)

        self.clarifier = self._deps.DeepResearchClarifyAgent(
            self._deps.create_chat_model(planner_model, temperature=0),
            self.config,
        )
        self.scope_agent = self._deps.DeepResearchScopeAgent(
            self._deps.create_chat_model(planner_model, temperature=0),
            self.config,
        )
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
        self.claim_verifier = ClaimVerifier()
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
        approved_scope = runtime_state_snapshot.get("approved_scope_draft")
        current_scope = runtime_state_snapshot.get("current_scope_draft")
        intake_status = str(runtime_state_snapshot.get("intake_status") or "pending").strip().lower()
        if not isinstance(approved_scope, dict) or not approved_scope:
            if isinstance(current_scope, dict) and current_scope:
                return "scope_review"
            if intake_status in {"ready_for_scope", "scope_revision_requested"}:
                return "scope"
            return "clarify"
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
            "latest_verification_summary": copy.deepcopy(
                runtime_state_snapshot.get("last_verification_summary", {})
            ),
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
        next_step = str(graph_state.get("next_step") or "clarify").strip().lower()
        if next_step in {"clarify", "scope", "scope_review", "dispatch", "verify", "report", "finalize"}:
            return next_step
        return "plan"

    def _clarify_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "clarify")
        record = view.start_agent_run(
            role="clarify",
            phase="intake",
            branch_id=view.root_branch_id,
            attempt=view.graph_attempt,
        )
        try:
            clarify_answers = list(view.runtime_state.get("clarify_answer_history") or [])
            result = self.clarifier.assess_intake(
                self.topic,
                clarify_answers=clarify_answers,
            )
            intake_summary = copy.deepcopy(result.get("intake_summary") or {})
            if intake_summary:
                view.runtime_state["intake_summary"] = intake_summary

            question = str(result.get("question") or "").strip()
            missing_information = _coerce_string_list(result.get("missing_information"))
            needs_clarification = bool(result.get("needs_clarification"))

            if (
                needs_clarification
                and question
                and self.allow_interrupts
                and len(clarify_answers) < self.max_clarify_rounds
            ):
                prompt = {
                    "checkpoint": "deepsearch_clarify",
                    "message": question,
                    "instruction": "Answer the clarification question so Deep Research can draft the scope.",
                    "question": question,
                    "content": "",
                    "graph_run_id": view.graph_run_id,
                    "graph_attempt": view.graph_attempt,
                    "missing_information": missing_information,
                    "intake_summary": intake_summary,
                    "available_actions": ["answer_clarification"],
                }
                view._emit_decision(
                    decision_type="clarify_required",
                    reason=question,
                    attempt=view.graph_attempt,
                    extra={
                        "missing_information": missing_information,
                    },
                )
                view.finish_agent_run(
                    record,
                    status="completed",
                    summary=question,
                    branch_id=view.root_branch_id,
                )
                updated = interrupt(prompt)
                answer = _extract_interrupt_text(
                    updated,
                    keys=("clarify_answer", "answer", "content", "feedback"),
                )
                if not answer:
                    raise ValueError("deepsearch clarify resume requires non-empty clarify_answer")
                question_history = list(view.runtime_state.get("clarify_question_history") or [])
                question_history.append(question)
                answer_history = list(view.runtime_state.get("clarify_answer_history") or [])
                answer_history.append(answer)
                view.runtime_state["clarify_question"] = question
                view.runtime_state["clarify_question_history"] = question_history
                view.runtime_state["clarify_answer_history"] = answer_history
                view.runtime_state["intake_status"] = "pending"
                return view.snapshot_patch(next_step="clarify")

            if needs_clarification and question:
                reason = (
                    f"{question} (interrupts unavailable or clarify round limit reached; continuing with best-effort scope)"
                )
            else:
                reason = "intake information is sufficient for scope drafting"
            view.runtime_state["clarify_question"] = ""
            view.runtime_state["intake_status"] = "ready_for_scope"
            view._emit_decision(
                decision_type="scope_ready",
                reason=reason,
                attempt=view.graph_attempt,
                extra={
                    "intake_summary": intake_summary,
                },
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=str(intake_summary.get("research_goal") or reason)[:240],
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step="scope")
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                branch_id=view.root_branch_id,
            )
            raise

    def _route_after_clarify(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "scope").strip().lower()
        if next_step in {"clarify", "scope"}:
            return next_step
        return "scope"

    def _scope_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "scope")
        record = view.start_agent_run(
            role="scope",
            phase="draft_scope",
            branch_id=view.root_branch_id,
            attempt=view.graph_attempt,
        )
        try:
            intake_summary = copy.deepcopy(view.runtime_state.get("intake_summary") or {})
            current_scope_payload = copy.deepcopy(view.runtime_state.get("current_scope_draft") or {})
            pending_feedback = str(view.runtime_state.get("pending_scope_feedback") or "").strip()
            current_scope = _scope_draft_from_payload(current_scope_payload)
            next_version = 1
            if current_scope:
                next_version = current_scope.version + 1 if pending_feedback else current_scope.version

            scope_payload = self.scope_agent.create_scope(
                self.topic,
                intake_summary=intake_summary,
                previous_scope=current_scope_payload if pending_feedback else {},
                scope_feedback=pending_feedback,
            )
            scope_draft = _build_scope_draft(
                topic=self.topic,
                version=next_version,
                draft_payload=scope_payload,
                intake_summary=intake_summary,
                feedback=pending_feedback,
                agent_id=record.agent_id,
                previous=current_scope_payload if pending_feedback else None,
            )

            view.runtime_state["current_scope_draft"] = scope_draft.to_dict()
            view.runtime_state["pending_scope_feedback"] = ""
            view.runtime_state["scope_revision_count"] = max(0, scope_draft.version - 1)
            view.runtime_state["intake_status"] = "awaiting_scope_review"

            decision_type = "scope_revision_requested" if pending_feedback else "scope_ready"
            decision_reason = (
                pending_feedback
                if pending_feedback
                else "structured scope draft is ready for user review"
            )
            view._emit_decision(
                decision_type=decision_type,
                reason=decision_reason,
                attempt=view.graph_attempt,
                extra={
                    "scope_version": scope_draft.version,
                },
            )
            view._emit_artifact_update(
                artifact_id=scope_draft.id,
                artifact_type="scope_draft",
                status=scope_draft.status,
                agent_id=scope_draft.created_by,
                summary=scope_draft.research_goal[:180],
                extra={
                    "scope_version": scope_draft.version,
                    "review_state": scope_draft.status,
                    "content": _format_scope_draft_markdown(scope_draft),
                },
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=scope_draft.research_goal[:240],
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step="scope_review")
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                branch_id=view.root_branch_id,
            )
            raise

    def _scope_review_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "scope_review")
        current_scope_payload = copy.deepcopy(view.runtime_state.get("current_scope_draft") or {})
        scope_draft = _scope_draft_from_payload(current_scope_payload)
        if not scope_draft:
            return view.snapshot_patch(next_step="scope")

        if not self.allow_interrupts:
            approved_payload = scope_draft.to_dict()
            approved_payload["status"] = "approved"
            approved_payload["updated_at"] = _now_iso()
            view.runtime_state["current_scope_draft"] = copy.deepcopy(approved_payload)
            view.runtime_state["approved_scope_draft"] = copy.deepcopy(approved_payload)
            view.runtime_state["intake_status"] = "scope_approved"
            view._emit_decision(
                decision_type="scope_approved",
                reason="interrupts disabled; auto-approving current scope draft",
                attempt=view.graph_attempt,
                extra={"scope_version": scope_draft.version},
            )
            view._emit_artifact_update(
                artifact_id=scope_draft.id,
                artifact_type="scope_draft",
                status="approved",
                agent_id=scope_draft.created_by,
                summary=scope_draft.research_goal[:180],
                extra={
                    "scope_version": scope_draft.version,
                    "review_state": "approved",
                    "content": _format_scope_draft_markdown(approved_payload),
                },
            )
            return view.snapshot_patch(next_step="plan")

        prompt = {
            "checkpoint": "deepsearch_scope_review",
            "message": "Review the proposed Deep Research scope.",
            "instruction": (
                "Approve the current scope draft to start research, or provide natural-language feedback "
                "to request a rewrite. Direct field edits are not accepted."
            ),
            "graph_run_id": view.graph_run_id,
            "graph_attempt": view.graph_attempt,
            "scope_draft": scope_draft.to_dict(),
            "scope_version": scope_draft.version,
            "scope_revision_count": int(view.runtime_state.get("scope_revision_count", 0) or 0),
            "content": _format_scope_draft_markdown(scope_draft),
            "available_actions": ["approve_scope", "revise_scope"],
            "allow_direct_edit": False,
        }
        updated = interrupt(prompt)
        if isinstance(updated, dict) and any(
            key in updated
            for key in ("scope_draft", "current_scope_draft", "approved_scope_draft", "modifications")
        ):
            raise ValueError(
                "Scope review does not accept direct scope draft edits; submit scope_feedback instead."
            )

        action = ""
        if isinstance(updated, dict):
            action = str(updated.get("action") or updated.get("decision") or "").strip().lower()
        if not action:
            action = (
                "revise_scope"
                if _extract_interrupt_text(updated, keys=("scope_feedback", "feedback", "content"))
                else "approve_scope"
            )

        if action == "approve_scope":
            approved_payload = scope_draft.to_dict()
            approved_payload["status"] = "approved"
            approved_payload["updated_at"] = _now_iso()
            view.runtime_state["current_scope_draft"] = copy.deepcopy(approved_payload)
            view.runtime_state["approved_scope_draft"] = copy.deepcopy(approved_payload)
            view.runtime_state["intake_status"] = "scope_approved"
            view._emit_decision(
                decision_type="scope_approved",
                reason="user approved the current scope draft",
                attempt=view.graph_attempt,
                extra={"scope_version": scope_draft.version},
            )
            view._emit_artifact_update(
                artifact_id=scope_draft.id,
                artifact_type="scope_draft",
                status="approved",
                agent_id=scope_draft.created_by,
                summary=scope_draft.research_goal[:180],
                extra={
                    "scope_version": scope_draft.version,
                    "review_state": "approved",
                    "content": _format_scope_draft_markdown(approved_payload),
                },
            )
            return view.snapshot_patch(next_step="plan")

        if action != "revise_scope":
            raise ValueError(f"Unsupported scope review action: {action}")

        scope_feedback = _extract_interrupt_text(
            updated,
            keys=("scope_feedback", "feedback", "content"),
        )
        if not scope_feedback:
            raise ValueError("revise_scope requires non-empty scope_feedback")
        feedback_history = list(view.runtime_state.get("scope_feedback_history") or [])
        feedback_history.append(
            {
                "scope_version": scope_draft.version,
                "feedback": scope_feedback,
                "at": _now_iso(),
            }
        )
        view.runtime_state["scope_feedback_history"] = feedback_history
        view.runtime_state["pending_scope_feedback"] = scope_feedback
        view.runtime_state["intake_status"] = "scope_revision_requested"
        view._emit_decision(
            decision_type="scope_revision_requested",
            reason=scope_feedback,
            attempt=view.graph_attempt,
            extra={"scope_version": scope_draft.version},
        )
        view._emit_artifact_update(
            artifact_id=scope_draft.id,
            artifact_type="scope_draft",
            status="revision_requested",
            agent_id=scope_draft.created_by,
            summary=scope_feedback[:180],
            extra={
                "scope_version": scope_draft.version,
                "review_state": "revision_requested",
                "content": _format_scope_draft_markdown(scope_draft),
            },
        )
        return view.snapshot_patch(next_step="scope")

    def _route_after_scope_review(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "plan").strip().lower()
        if next_step in {"scope", "plan"}:
            return next_step
        return "plan"

    def _plan_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "plan")
        approved_scope = copy.deepcopy(view.runtime_state.get("approved_scope_draft") or {})
        if not approved_scope:
            return view.snapshot_patch(next_step="scope_review")
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
            existing_objectives = [
                task.objective or task.title or task.goal
                for task in view.task_queue.all_tasks()
                if (task.objective or task.title or task.goal)
            ]
            if planning_mode == "replan":
                gap_result = _gap_result_from_payload(
                    graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
                )
                gap_labels = [gap.aspect for gap in gap_result.gaps] if gap_result else []
                plan_items = self.planner.refine_plan(
                    self.topic,
                    gaps=gap_labels,
                    existing_queries=existing_objectives,
                    num_queries=min(
                        self.query_num,
                        max(1, len(gap_result.suggested_queries) if gap_result else 1),
                    ),
                    approved_scope=approved_scope,
                )
                context_id = str(approved_scope.get("id") or f"replan-{view.current_iteration or 0}")
            else:
                plan_items = self.planner.create_plan(
                    self.topic,
                    num_queries=self.query_num,
                    existing_knowledge=view._knowledge_summary(),
                    existing_queries=existing_objectives,
                    approved_scope=approved_scope,
                )
                context_id = str(approved_scope.get("id") or view.root_branch_id or support._new_id("brief"))

            tasks = dispatcher.build_tasks_from_plan(
                view,
                plan_items,
                context_id=context_id,
                branch_id=view.root_branch_id,
            )
            if tasks:
                view.task_queue.enqueue(tasks)
                for brief in dispatcher.build_briefs_from_tasks(
                    self.topic,
                    tasks,
                    parent_branch_id=view.root_branch_id,
                    context_id=context_id,
                ):
                    existing_brief = view.artifact_store.get_brief(brief.id)
                    if existing_brief:
                        brief.latest_synthesis_id = existing_brief.latest_synthesis_id
                        brief.latest_verification_id = existing_brief.latest_verification_id
                        brief.verification_status = existing_brief.verification_status
                    view.artifact_store.put_brief(brief)
                    view._emit_artifact_update(
                        artifact_id=brief.id,
                        artifact_type="branch_brief",
                        status=brief.status,
                        branch_id=brief.id,
                        task_id=brief.latest_task_id,
                        summary=brief.summary,
                        task_kind=brief.task_kind,
                        stage=brief.current_stage,
                        extra={
                            "objective_summary": brief.objective,
                            "input_artifact_ids": brief.input_artifact_ids,
                        },
                    )
                for task in tasks:
                    view._emit_task_update(task=task, status=task.status, attempt=task.attempts)
                view._emit_research_tree_update()
            view.finish_agent_run(
                record,
                status="completed",
                summary=f"生成 {len(tasks)} 个 branch 研究任务",
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
        objective_summary = task.objective or task.title or task.goal
        record = view.start_agent_run(
            role="researcher",
            phase="branch_research",
            task_id=task.id,
            branch_id=branch_id,
            iteration=iteration,
            attempt=attempt,
            task_kind=task.task_kind,
            stage="search",
            objective_summary=objective_summary,
            persist=False,
        )

        worker_parent_state = copy.deepcopy(view.shared_state)
        branch_brief = view.artifact_store.get_brief(branch_id or "") if branch_id else None
        worker_context = build_research_worker_context(
            worker_parent_state,
            task_id=task.id,
            agent_id=record.agent_id,
            query=task.query,
            topic=self.topic,
            brief={
                "topic": self.topic,
                "goal": task.goal,
                "objective": objective_summary,
                "aspect": task.aspect,
                "task_kind": task.task_kind,
                "acceptance_criteria": list(task.acceptance_criteria),
                "allowed_tools": list(task.allowed_tools),
                "iteration": iteration,
                "stage": "planned",
                "branch_summary": branch_brief.summary if branch_brief else "",
            },
            related_artifacts=view.artifact_store.get_related_artifacts(task.id, branch_id=branch_id),
            scope_id=f"worker-{task.id}-attempt-{attempt}",
            parent_scope_id=branch_id,
        )

        current_stage = "search"

        def _emit_stage(stage: str, *, reason: str = "") -> None:
            nonlocal current_stage
            current_stage = stage
            task.stage = stage
            worker_context.brief["stage"] = stage
            view._emit_task_update(
                task=task,
                status="in_progress",
                attempt=attempt,
                reason=reason or "",
            )

        try:
            view._check_cancel()
            _emit_stage("search")
            queries = _derive_branch_queries(task)
            if not queries:
                raise RuntimeError("branch task has no executable query hints")

            results: list[dict[str, Any]] = []
            searches_used = 0
            for query in queries:
                view._check_cancel()
                query_results = self.researcher.execute_queries(
                    [query],
                    max_results_per_query=self.results_per_query,
                )
                if query:
                    searches_used += 1
                for item in query_results:
                    if not isinstance(item, dict):
                        continue
                    results.append({**item, "query": query})

            if not results:
                raise RuntimeError("branch agent returned no evidence")

            _emit_stage("read")
            source_candidates: list[SourceCandidate] = []
            fetched_documents: list[FetchedDocument] = []
            evidence_passages: list[EvidencePassage] = []
            evidence_cards: list[EvidenceCard] = []
            for index, item in enumerate(results[: min(len(results), max(3, self.results_per_query))], 1):
                source_candidate_id = support._new_id("source")
                document_id = support._new_id("document")
                passage_id = support._new_id("passage")
                content = str(
                    item.get("raw_excerpt")
                    or item.get("content")
                    or item.get("summary")
                    or item.get("snippet")
                    or ""
                ).strip()
                summary_text = str(item.get("summary") or item.get("snippet") or content[:280]).strip()
                source_title = str(item.get("title") or item.get("url") or "Untitled")
                source_url = str(item.get("url") or "")
                source_candidates.append(
                    SourceCandidate(
                        id=source_candidate_id,
                        task_id=task.id,
                        branch_id=branch_id,
                        title=source_title,
                        url=source_url,
                        summary=summary_text[:400],
                        rank=index,
                        source_provider=str(item.get("provider") or ""),
                        published_date=item.get("published_date"),
                        created_by=record.agent_id,
                        metadata={
                            "query": str(item.get("query") or task.query or objective_summary),
                            "attempt": attempt,
                            "graph_run_id": view.graph_run_id,
                        },
                    )
                )
                fetched_documents.append(
                    FetchedDocument(
                        id=document_id,
                        task_id=task.id,
                        branch_id=branch_id,
                        source_candidate_id=source_candidate_id,
                        url=source_url,
                        title=source_title,
                        content=content[:2400],
                        excerpt=content[:700],
                        created_by=record.agent_id,
                        metadata={
                            "query": str(item.get("query") or task.query or objective_summary),
                            "attempt": attempt,
                        },
                    )
                )
                evidence_passages.append(
                    EvidencePassage(
                        id=passage_id,
                        task_id=task.id,
                        branch_id=branch_id,
                        document_id=document_id,
                        url=source_url,
                        text=content[:900],
                        quote=content[:240],
                        source_title=source_title,
                        snippet_hash=f"{task.id}-{index}-{attempt}",
                        created_by=record.agent_id,
                        metadata={
                            "query": str(item.get("query") or task.query or objective_summary),
                            "attempt": attempt,
                        },
                    )
                )
                evidence_cards.append(
                    EvidenceCard(
                        id=support._new_id("evidence"),
                        task_id=task.id,
                        branch_id=branch_id,
                        source_title=source_title,
                        source_url=source_url,
                        summary=summary_text[:280],
                        excerpt=content[:700],
                        source_provider=str(item.get("provider") or ""),
                        published_date=item.get("published_date"),
                        created_by=record.agent_id,
                        metadata={
                            "query": str(item.get("query") or task.query or objective_summary),
                            "attempt": attempt,
                            "graph_run_id": view.graph_run_id,
                            "passage_id": passage_id,
                        },
                    )
                )

            _emit_stage("extract")
            summary = self.researcher.summarize_findings(
                self.topic,
                results,
                existing_summary=view._knowledge_summary(),
            )
            findings = _split_findings(summary)

            _emit_stage("synthesize")
            branch_synthesis = BranchSynthesis(
                id=support._new_id("synthesis"),
                task_id=task.id,
                branch_id=branch_id,
                objective=objective_summary,
                summary=summary or f"未能为“{objective_summary}”形成充分结论。",
                findings=findings,
                acceptance_criteria=list(task.acceptance_criteria),
                evidence_passage_ids=[passage.id for passage in evidence_passages],
                source_document_ids=[document.id for document in fetched_documents],
                citation_urls=[candidate.url for candidate in source_candidates if candidate.url],
                created_by=record.agent_id,
                metadata={
                    "query_hints": list(queries),
                    "attempt": attempt,
                    "task_kind": task.task_kind,
                    "graph_run_id": view.graph_run_id,
                },
            )

            section_draft = ReportSectionDraft(
                id=support._new_id("section"),
                task_id=task.id,
                branch_id=branch_id,
                title=task.title or objective_summary,
                summary=branch_synthesis.summary,
                evidence_ids=[card.id for card in evidence_cards],
                created_by=record.agent_id,
            )

            worker_context.summary_notes.append(branch_synthesis.summary)
            worker_context.scraped_content.append(
                {
                    "query": task.query,
                    "queries": queries,
                    "objective": objective_summary,
                    "task_kind": task.task_kind,
                    "stage": current_stage,
                    "results": results,
                    "timestamp": _now_iso(),
                    "task_id": task.id,
                    "agent_id": record.agent_id,
                    "attempt": attempt,
                    "branch_id": branch_id,
                }
            )
            worker_context.sources.extend(support._compact_sources(results, limit=10))
            worker_context.artifacts_created.extend(
                [candidate.to_dict() for candidate in source_candidates]
                + [document.to_dict() for document in fetched_documents]
                + [passage.to_dict() for passage in evidence_passages]
                + [card.to_dict() for card in evidence_cards]
                + [branch_synthesis.to_dict(), section_draft.to_dict()]
            )
            worker_context.is_complete = True

            view.finish_agent_run(
                record,
                status="completed",
                summary=branch_synthesis.summary[:240],
                iteration=iteration,
                branch_id=branch_id,
                stage=current_stage,
            )

            result = WorkerExecutionResult(
                task=task,
                context=worker_context,
                source_candidates=source_candidates,
                fetched_documents=fetched_documents,
                evidence_passages=evidence_passages,
                branch_synthesis=branch_synthesis,
                evidence_cards=evidence_cards,
                section_draft=section_draft,
                raw_results=results,
                tokens_used=support._estimate_tokens_from_results(results)
                + support._estimate_tokens_from_text(summary),
                searches_used=searches_used,
                branch_id=branch_id,
                task_stage=current_stage,
                result_status="completed",
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
                stage=current_stage,
            )
            result = WorkerExecutionResult(
                task=task,
                context=worker_context,
                source_candidates=[],
                fetched_documents=[],
                evidence_passages=[],
                branch_synthesis=None,
                evidence_cards=[],
                section_draft=None,
                raw_results=[],
                tokens_used=0,
                searches_used=0,
                branch_id=branch_id,
                task_stage=current_stage,
                result_status="failed",
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
            view.searches_used += max(0, result.searches_used)
            view.tokens_used += max(0, result.tokens_used)

            if result.agent_run:
                view.agent_runs.append(result.agent_run)

            if result.source_candidates:
                view.artifact_store.add_source_candidates(result.source_candidates)
                for candidate in result.source_candidates:
                    view._emit_artifact_update(
                        artifact_id=candidate.id,
                        artifact_type="source_candidate",
                        status=candidate.status,
                        task_id=candidate.task_id,
                        branch_id=candidate.branch_id,
                        agent_id=candidate.created_by,
                        summary=candidate.summary[:180],
                        source_url=candidate.url,
                        task_kind=result.task.task_kind,
                        stage="search",
                    )

            if result.fetched_documents:
                view.artifact_store.add_fetched_documents(result.fetched_documents)
                for document in result.fetched_documents:
                    view._emit_artifact_update(
                        artifact_id=document.id,
                        artifact_type="fetched_document",
                        status=document.status,
                        task_id=document.task_id,
                        branch_id=document.branch_id,
                        agent_id=document.created_by,
                        summary=document.title[:180] or document.excerpt[:180],
                        source_url=document.url,
                        task_kind=result.task.task_kind,
                        stage="read",
                    )

            if result.evidence_passages:
                view.artifact_store.add_evidence_passages(result.evidence_passages)
                for passage in result.evidence_passages:
                    view._emit_artifact_update(
                        artifact_id=passage.id,
                        artifact_type="evidence_passage",
                        status=passage.status,
                        task_id=passage.task_id,
                        branch_id=passage.branch_id,
                        agent_id=passage.created_by,
                        summary=passage.quote[:180] or passage.text[:180],
                        source_url=passage.url,
                        task_kind=result.task.task_kind,
                        stage="extract",
                    )

            if result.evidence_cards:
                view.artifact_store.add_evidence(result.evidence_cards)
                for card in result.evidence_cards:
                    view._emit_artifact_update(
                        artifact_id=card.id,
                        artifact_type="evidence_card",
                        status=card.status,
                        task_id=card.task_id,
                        branch_id=card.branch_id,
                        agent_id=card.created_by,
                        summary=card.summary[:180],
                        source_url=card.source_url,
                        task_kind=result.task.task_kind,
                        stage="extract",
                    )

            if result.branch_synthesis:
                view.artifact_store.add_branch_synthesis(result.branch_synthesis)
                view._emit_artifact_update(
                    artifact_id=result.branch_synthesis.id,
                    artifact_type="branch_synthesis",
                    status=result.branch_synthesis.status,
                    task_id=result.branch_synthesis.task_id,
                    branch_id=result.branch_synthesis.branch_id,
                    agent_id=result.branch_synthesis.created_by,
                    summary=result.branch_synthesis.summary[:180],
                    task_kind=result.task.task_kind,
                    stage="synthesize",
                    extra={
                        "objective_summary": result.branch_synthesis.objective,
                        "citation_urls": result.branch_synthesis.citation_urls,
                    },
                )

            if result.section_draft:
                view.artifact_store.add_section_draft(result.section_draft)
                view._emit_artifact_update(
                    artifact_id=result.section_draft.id,
                    artifact_type="report_section_draft",
                    status=result.section_draft.status,
                    task_id=result.section_draft.task_id,
                    branch_id=result.section_draft.branch_id,
                    agent_id=result.section_draft.created_by,
                    summary=result.section_draft.summary[:180],
                    task_kind=result.task.task_kind,
                    stage="synthesize",
                )

            if result.branch_id:
                branch_brief = view.artifact_store.get_brief(result.branch_id)
                if branch_brief:
                    branch_brief.latest_task_id = result.task.id
                    branch_brief.current_stage = result.task_stage or result.task.stage or branch_brief.current_stage
                    branch_brief.summary = result.task.title or result.task.objective or branch_brief.summary
                    branch_brief.objective = result.task.objective or branch_brief.objective
                    branch_brief.task_kind = result.task.task_kind or branch_brief.task_kind
                    branch_brief.allowed_tools = list(result.task.allowed_tools or branch_brief.allowed_tools)
                    branch_brief.acceptance_criteria = list(
                        result.task.acceptance_criteria or branch_brief.acceptance_criteria
                    )
                    if result.branch_synthesis:
                        branch_brief.latest_synthesis_id = result.branch_synthesis.id
                    branch_brief.verification_status = "pending"
                    view.artifact_store.put_brief(branch_brief)

            if result.raw_results and result.branch_synthesis:
                updated_task = view.task_queue.update_stage(
                    result.task.id,
                    "reported",
                    status="completed",
                )
                if updated_task:
                    view._emit_task_update(
                        task=updated_task,
                        status=updated_task.status,
                        attempt=updated_task.attempts,
                    )
                continue

            reason = result.error or "researcher returned no results"
            if result.task.attempts < self.task_retry_limit and not view.budget_stop_reason:
                failed_task = view.task_queue.update_stage(
                    result.task.id,
                    result.task_stage or result.task.stage or "search",
                    status="failed",
                    reason=reason,
                )
                if failed_task:
                    view._emit_task_update(
                        task=failed_task,
                        status=failed_task.status,
                        attempt=failed_task.attempts,
                        reason=reason,
                    )
                retry_task = view.task_queue.update_stage(
                    result.task.id,
                    "dispatch",
                    status="ready",
                    reason=reason,
                )
                if retry_task:
                    view._emit_task_update(
                        task=retry_task,
                        status=retry_task.status,
                        attempt=retry_task.attempts,
                        reason=reason,
                    )
            else:
                failed_task = view.task_queue.update_stage(
                    result.task.id,
                    result.task_stage or result.task.stage or "search",
                    status="failed",
                    reason=reason,
                )
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
        task_map = {task.id: task for task in view.task_queue.all_tasks()}
        syntheses = sorted(
            view.artifact_store.branch_syntheses(),
            key=lambda item: (item.task_id, item.created_at, item.id),
        )
        claim_record = view.start_agent_run(
            role="verifier",
            phase="claim_check",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
            stage="claim_check",
            validation_stage="claim_check",
        )
        claim_results: list[VerificationResult] = []
        claim_outcomes_by_task: dict[str, VerificationResult] = {}
        try:
            for synthesis in syntheses:
                task = task_map.get(synthesis.task_id)
                if task:
                    task.stage = "claim_check"
                    view._emit_task_update(
                        task=task,
                        status=task.status,
                        attempt=task.attempts,
                    )
                related_passages = [
                    passage
                    for passage in view.artifact_store.evidence_passages(branch_id=synthesis.branch_id)
                    if not synthesis.evidence_passage_ids or passage.id in synthesis.evidence_passage_ids
                ]
                claim_checks = self.claim_verifier.verify_report(
                    synthesis.summary,
                    [],
                    passages=[
                        {
                            "url": passage.url,
                            "text": passage.text,
                            "quote": passage.quote,
                            "snippet_hash": passage.snippet_hash,
                            "heading_path": passage.heading_path,
                        }
                        for passage in related_passages
                    ],
                )
                statuses = [check.status for check in claim_checks]
                if any(status == ClaimStatus.CONTRADICTED for status in statuses):
                    outcome = "failed"
                    recommended_action = "retry_branch"
                    summary = "claim/citation 检查发现矛盾证据"
                elif any(status == ClaimStatus.UNSUPPORTED for status in statuses):
                    outcome = "needs_follow_up"
                    recommended_action = "retry_branch"
                    summary = "claim/citation 检查发现证据不足"
                else:
                    outcome = "passed"
                    recommended_action = "report"
                    summary = "claim/citation 检查通过"
                evidence_urls = list(
                    dict.fromkeys(
                        url
                        for check in claim_checks
                        for url in check.evidence_urls
                        if url
                    )
                )
                evidence_passage_ids = [
                    passage.id
                    for passage in related_passages
                    if not evidence_urls or passage.url in evidence_urls
                ]
                verification_result = VerificationResult(
                    id=support._new_id("verification"),
                    task_id=synthesis.task_id,
                    branch_id=synthesis.branch_id,
                    synthesis_id=synthesis.id,
                    validation_stage="claim_check",
                    outcome=outcome,
                    summary=summary,
                    recommended_action=recommended_action,
                    evidence_urls=evidence_urls,
                    evidence_passage_ids=evidence_passage_ids,
                    metadata={
                        "claims": [
                            {
                                "claim": check.claim,
                                "status": check.status.value,
                                "evidence_urls": check.evidence_urls,
                                "evidence_passages": check.evidence_passages,
                                "notes": check.notes,
                            }
                            for check in claim_checks
                        ],
                        "branch_summary": synthesis.summary[:240],
                    },
                )
                claim_results.append(verification_result)
                claim_outcomes_by_task[synthesis.task_id] = verification_result

            if claim_results:
                view.artifact_store.add_verification_results(claim_results)
                for result in claim_results:
                    branch_task = task_map.get(result.task_id)
                    view._emit_artifact_update(
                        artifact_id=result.id,
                        artifact_type="verification_result",
                        status=result.status,
                        task_id=result.task_id,
                        branch_id=result.branch_id,
                        agent_id=result.created_by,
                        summary=result.summary,
                        task_kind=branch_task.task_kind if branch_task else None,
                        stage="claim_check",
                        validation_stage=result.validation_stage,
                        extra={"outcome": result.outcome, "recommended_action": result.recommended_action},
                    )
                    if result.branch_id:
                        brief = view.artifact_store.get_brief(result.branch_id)
                        if brief:
                            brief.latest_verification_id = result.id
                            brief.current_stage = "claim_check"
                            brief.verification_status = result.outcome
                            view.artifact_store.put_brief(brief)

            view.finish_agent_run(
                claim_record,
                status="completed",
                summary=f"claim_checks={len(claim_results)}",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
                stage="claim_check",
                validation_stage="claim_check",
            )
        except Exception as exc:
            view.finish_agent_run(
                claim_record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
                stage="claim_check",
                validation_stage="claim_check",
            )
            raise

        coverage_record = view.start_agent_run(
            role="verifier",
            phase="coverage_check",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
            stage="coverage_check",
            validation_stage="coverage_check",
        )
        try:
            executed_objectives = [
                task.objective or task.query or task.title or task.goal
                for task in view.task_queue.all_tasks()
                if task.status == "completed"
            ]
            verified_knowledge = "\n\n".join(
                synthesis.summary
                for synthesis in syntheses
                if claim_outcomes_by_task.get(synthesis.task_id)
                and claim_outcomes_by_task[synthesis.task_id].outcome == "passed"
            )
            gap_result = self.verifier.analyze(
                self.topic,
                executed_queries=executed_objectives,
                collected_knowledge=verified_knowledge or view._knowledge_summary(),
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
                    branch_id=view.root_branch_id,
                    summary=f"{gap.aspect}: {gap.reason}",
                    stage="coverage_check",
                    validation_stage="coverage_check",
                )

            coverage_results: list[VerificationResult] = []
            verified_task_ids: list[str] = []
            retry_task_ids: list[str] = []
            failed_branch_count = 0
            follow_up_branch_count = 0
            for synthesis in syntheses:
                task = task_map.get(synthesis.task_id)
                claim_result = claim_outcomes_by_task.get(synthesis.task_id)
                missing_criteria = [
                    criterion
                    for criterion in (task.acceptance_criteria if task else [])
                    if not _criterion_is_covered(synthesis.summary, criterion)
                ]
                if claim_result and claim_result.outcome == "failed":
                    outcome = "failed"
                    recommended_action = "retry_branch"
                    summary = "coverage 检查终止，claim/citation 已失败"
                    failed_branch_count += 1
                elif claim_result and claim_result.outcome == "needs_follow_up":
                    outcome = "needs_follow_up"
                    recommended_action = "retry_branch"
                    summary = "coverage 检查发现需先补充分支证据"
                    follow_up_branch_count += 1
                elif missing_criteria:
                    outcome = "needs_follow_up"
                    recommended_action = "retry_branch"
                    summary = f"coverage 检查发现分支仍缺少 {len(missing_criteria)} 项验收标准"
                    follow_up_branch_count += 1
                else:
                    outcome = "passed"
                    recommended_action = "report"
                    summary = "coverage 检查通过"
                    verified_task_ids.append(synthesis.task_id)

                if recommended_action == "retry_branch":
                    retry_task_ids.append(synthesis.task_id)

                result = VerificationResult(
                    id=support._new_id("verification"),
                    task_id=synthesis.task_id,
                    branch_id=synthesis.branch_id,
                    synthesis_id=synthesis.id,
                    validation_stage="coverage_check",
                    outcome=outcome,
                    summary=summary,
                    recommended_action=recommended_action,
                    gap_ids=[gap.id for gap in gap_artifacts],
                    evidence_urls=list(synthesis.citation_urls),
                    evidence_passage_ids=list(synthesis.evidence_passage_ids),
                    metadata={
                        "missing_acceptance_criteria": missing_criteria,
                        "gap_analysis": gap_result.analysis,
                    },
                )
                coverage_results.append(result)

            if coverage_results:
                view.artifact_store.add_verification_results(coverage_results)
                for result in coverage_results:
                    branch_task = task_map.get(result.task_id)
                    view._emit_artifact_update(
                        artifact_id=result.id,
                        artifact_type="verification_result",
                        status=result.status,
                        task_id=result.task_id,
                        branch_id=result.branch_id,
                        agent_id=result.created_by,
                        summary=result.summary,
                        task_kind=branch_task.task_kind if branch_task else None,
                        stage="coverage_check",
                        validation_stage=result.validation_stage,
                        extra={
                            "outcome": result.outcome,
                            "recommended_action": result.recommended_action,
                            "gap_ids": result.gap_ids,
                        },
                    )
                    if result.branch_id:
                        brief = view.artifact_store.get_brief(result.branch_id)
                        if brief:
                            brief.latest_verification_id = result.id
                            brief.current_stage = "coverage_check"
                            brief.verification_status = result.outcome
                            view.artifact_store.put_brief(brief)

            quality_summary = view._quality_summary(gap_result)
            view._emit(events.ToolEventType.QUALITY_UPDATE, quality_summary)

            verification_summary = {
                "verified_branches": len({task_map[task_id].branch_id for task_id in verified_task_ids if task_id in task_map}),
                "verified_task_ids": verified_task_ids,
                "retry_branches": len({task_map[task_id].branch_id for task_id in retry_task_ids if task_id in task_map}),
                "retry_task_ids": list(dict.fromkeys(retry_task_ids)),
                "failed_branches": failed_branch_count,
                "follow_up_branches": follow_up_branch_count,
                "coverage_gap_count": len(gap_artifacts),
                "replan_hints": list(gap_result.suggested_queries),
            }
            if verification_summary["retry_task_ids"]:
                view._emit_decision(
                    decision_type="verification_retry_requested",
                    reason="branch 验证要求补证据或重试",
                    iteration=view.current_iteration,
                    gap_count=len(gap_artifacts),
                    attempt=view.graph_attempt,
                    validation_stage="coverage_check",
                    extra={"retry_task_ids": verification_summary["retry_task_ids"]},
                )
            elif gap_artifacts:
                view._emit_decision(
                    decision_type="coverage_gap_detected",
                    reason="整体 coverage 仍存在缺口，需要补充规划",
                    iteration=view.current_iteration,
                    gap_count=len(gap_artifacts),
                    attempt=view.graph_attempt,
                    validation_stage="coverage_check",
                    extra={"suggested_queries": gap_result.suggested_queries},
                )
            else:
                view._emit_decision(
                    decision_type="verification_passed",
                    reason="branch 验证通过，可进入汇总",
                    iteration=view.current_iteration,
                    coverage=gap_result.overall_coverage,
                    gap_count=len(gap_artifacts),
                    attempt=view.graph_attempt,
                    validation_stage="coverage_check",
                )

            view.finish_agent_run(
                coverage_record,
                status="completed",
                summary=f"coverage={gap_result.overall_coverage:.2f}, gaps={len(gap_result.gaps)}",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
                stage="coverage_check",
                validation_stage="coverage_check",
            )
            return view.snapshot_patch(
                next_step="coordinate",
                latest_gap_result=gap_result.to_dict(),
                latest_verification_summary=verification_summary,
            )
        except Exception as exc:
            view.finish_agent_run(
                coverage_record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
                stage="coverage_check",
                validation_stage="coverage_check",
            )
            raise

    def _coordinate_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "coordinate")
        gap_result = _gap_result_from_payload(
            graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
        )
        verification_summary = copy.deepcopy(
            graph_state.get("latest_verification_summary")
            or view.runtime_state.get("last_verification_summary")
            or {}
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

            retry_task_ids = [
                task_id
                for task_id in verification_summary.get("retry_task_ids", [])
                if isinstance(task_id, str) and task_id.strip()
            ]
            ready_for_retry = []
            for task_id in retry_task_ids:
                existing_task = view.task_queue.get(task_id)
                if not existing_task:
                    continue
                if existing_task.attempts >= self.task_retry_limit:
                    continue
                retried_task = view.task_queue.update_stage(
                    task_id,
                    "dispatch",
                    status="ready",
                    reason="verification_follow_up",
                )
                if retried_task:
                    ready_for_retry.append(retried_task)
                    view._emit_task_update(
                        task=retried_task,
                        status=retried_task.status,
                        attempt=retried_task.attempts,
                        reason="verification_follow_up",
                    )
            if ready_for_retry:
                latest_decision = {
                    "action": "retry_branch",
                    "reasoning": "branch 验证要求补证据，已重新放回调度队列",
                    "iteration": view.current_iteration,
                    "retry_task_ids": [task.id for task in ready_for_retry],
                }
                view._emit_decision(
                    decision_type="retry_branch",
                    reason=latest_decision["reasoning"],
                    iteration=view.current_iteration,
                    gap_count=len(gap_result.gaps) if gap_result else None,
                    attempt=view.graph_attempt,
                    extra={"retry_task_ids": latest_decision["retry_task_ids"]},
                )
                view.finish_agent_run(
                    record,
                    status="completed",
                    summary=latest_decision["reasoning"],
                    iteration=view.current_iteration,
                    branch_id=view.root_branch_id,
                )
                return view.snapshot_patch(
                    next_step="dispatch",
                    latest_decision=latest_decision,
                    planning_mode="",
                )

            evidence_count = len(view.artifact_store.evidence_passages()) or len(view.artifact_store.evidence_cards())
            section_count = len(view.artifact_store.branch_syntheses())
            unique_urls = {
                passage.url
                for passage in view.artifact_store.evidence_passages()
                if passage.url
            }
            if not unique_urls:
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
                verification_summary=verification_summary,
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
            coverage_results = {
                result.task_id: result
                for result in view.artifact_store.verification_results(validation_stage="coverage_check")
            }
            claim_results = {
                result.task_id: result
                for result in view.artifact_store.verification_results(validation_stage="claim_check")
            }
            verified_syntheses = [
                synthesis
                for synthesis in view.artifact_store.branch_syntheses()
                if claim_results.get(synthesis.task_id)
                and coverage_results.get(synthesis.task_id)
                and claim_results[synthesis.task_id].outcome == "passed"
                and coverage_results[synthesis.task_id].outcome == "passed"
            ]
            findings = [synthesis.summary for synthesis in verified_syntheses if synthesis.summary]
            citation_urls = list(
                dict.fromkeys(
                    url
                    for synthesis in verified_syntheses
                    for url in synthesis.citation_urls
                    if url
                )
            )

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
        workflow.add_node("clarify", self._clarify_node)
        workflow.add_node("scope", self._scope_node)
        workflow.add_node("scope_review", self._scope_review_node)
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
            ["clarify", "scope", "scope_review", "plan", "dispatch", "verify", "report", "finalize"],
        )
        workflow.add_conditional_edges(
            "clarify",
            self._route_after_clarify,
            ["clarify", "scope"],
        )
        workflow.add_edge("scope", "scope_review")
        workflow.add_conditional_edges(
            "scope_review",
            self._route_after_scope_review,
            ["scope", "plan"],
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
