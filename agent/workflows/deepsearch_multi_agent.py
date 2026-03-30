from __future__ import annotations

import asyncio
import copy
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import AIMessage

from agent.core.context import (
    ResearchWorkerContext,
    build_research_worker_context,
    merge_research_worker_context,
)
from agent.core.events import ToolEventType, get_emitter_sync
from agent.core.llm_factory import create_chat_model
from agent.workflows.agents.coordinator import CoordinatorAction, ResearchCoordinator
from agent.workflows.agents.planner import ResearchPlanner
from agent.workflows.agents.reporter import ResearchReporter
from agent.workflows.agents.researcher import ResearchAgent
from agent.workflows.domain_router import ResearchDomain, build_provider_profile
from agent.workflows.knowledge_gap import (
    GapAnalysisResult,
    KnowledgeGapAnalyzer,
)
from agent.workflows.search_cache import get_search_cache
from common.cancellation import check_cancellation as _check_cancel_token
from common.config import settings
from tools import tavily_search
from tools.search.multi_search import SearchStrategy, multi_search

logger = logging.getLogger(__name__)

TaskStatus = Literal["ready", "in_progress", "blocked", "completed", "failed", "cancelled"]
ArtifactStatus = Literal["created", "updated", "completed", "discarded"]
AgentRole = Literal["coordinator", "planner", "researcher", "verifier", "reporter"]


def _now_iso() -> str:
    return datetime.now().isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _configurable_value(config: Dict[str, Any], key: str) -> Any:
    cfg = config.get("configurable") or {}
    if isinstance(cfg, dict):
        return cfg.get(key)
    return None


def _configurable_int(config: Dict[str, Any], key: str, default: int) -> int:
    value = _configurable_value(config, key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _configurable_float(config: Dict[str, Any], key: str, default: float) -> float:
    value = _configurable_value(config, key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _selected_model(config: Dict[str, Any], fallback: str) -> str:
    value = _configurable_value(config, "model")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _selected_reasoning_model(config: Dict[str, Any], fallback: str) -> str:
    value = _configurable_value(config, "reasoning_model")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _model_for_task(task_type: str, config: Dict[str, Any]) -> str:
    try:
        from agent.core.multi_model import TaskType, get_model_router

        task = TaskType(task_type)
        return get_model_router().get_model_name(task, config)
    except Exception:
        if task_type in {"planning", "query_gen", "critique", "gap_analysis"}:
            return _selected_reasoning_model(config, settings.reasoning_model)
        return _selected_model(config, settings.primary_model)


def _resolve_provider_profile(state: Dict[str, Any]) -> Optional[List[str]]:
    domain_config = state.get("domain_config") or {}
    suggested_sources = domain_config.get("suggested_sources", [])
    domain_value = state.get("domain") or domain_config.get("domain") or "general"
    try:
        domain = ResearchDomain(str(domain_value).strip().lower())
    except ValueError:
        domain = ResearchDomain.GENERAL
    profile = build_provider_profile(suggested_sources=suggested_sources, domain=domain)
    return profile or None


def _resolve_search_strategy() -> SearchStrategy:
    raw = str(getattr(settings, "search_strategy", "fallback") or "fallback").strip().lower()
    try:
        return SearchStrategy(raw)
    except ValueError:
        logger.warning("[deepsearch-multi-agent] invalid search_strategy=%s, fallback to fallback", raw)
        return SearchStrategy.FALLBACK


def _normalize_multi_search_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "summary": item.get("summary") or item.get("snippet", ""),
                "raw_excerpt": item.get("raw_excerpt") or item.get("content", ""),
                "score": float(item.get("score", 0.5) or 0.5),
                "published_date": item.get("published_date"),
                "provider": item.get("provider", ""),
            }
        )
    return normalized


def _cache_query_key(
    query: str,
    max_results: int,
    strategy: SearchStrategy,
    provider_profile: Optional[List[str]],
) -> str:
    joined_profile = ",".join(provider_profile or [])
    return f"deepsearch-multi-agent::{strategy.value}::{max_results}::{joined_profile}::{query}"


def _search_query(
    query: str,
    max_results: int,
    config: Dict[str, Any],
    provider_profile: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    strategy = _resolve_search_strategy()
    cache = get_search_cache()
    cache_key = _cache_query_key(query, max_results, strategy, provider_profile)
    cached = cache.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    try:
        kwargs: Dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "strategy": strategy,
        }
        if provider_profile:
            kwargs["provider_profile"] = provider_profile
        multi_results = multi_search(**kwargs)
        normalized = _normalize_multi_search_results(multi_results)
        if normalized:
            cache.set(cache_key, copy.deepcopy(normalized))
            return normalized
    except Exception as exc:
        logger.warning("[deepsearch-multi-agent] multi_search failed, falling back: %s", exc)

    try:
        fallback_results = tavily_search.invoke(
            {"query": query, "max_results": max_results},
            config=config,
        )
        if fallback_results:
            cache.set(cache_key, copy.deepcopy(fallback_results))
        return fallback_results or []
    except Exception as exc:
        logger.warning("[deepsearch-multi-agent] tavily_search failed: %s", exc)
        return []


def _estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, len(str(text)) // 4)


def _estimate_tokens_from_results(results: List[Dict[str, Any]]) -> int:
    total = 0
    for item in results or []:
        if not isinstance(item, dict):
            continue
        total += _estimate_tokens_from_text(item.get("title", ""))
        total += _estimate_tokens_from_text(
            str(
                item.get("raw_excerpt")
                or item.get("summary")
                or item.get("snippet")
                or item.get("content")
                or ""
            )[:600]
        )
    return total


def _budget_stop_reason(
    *,
    start_ts: float,
    searches_used: int,
    tokens_used: int,
    max_seconds: float,
    max_tokens: int,
    max_searches: int,
) -> Optional[str]:
    if max_seconds > 0 and (time.time() - start_ts) >= max_seconds:
        return "time_budget_exceeded"
    if max_tokens > 0 and tokens_used >= max_tokens:
        return "token_budget_exceeded"
    if max_searches > 0 and searches_used >= max_searches:
        return "search_budget_exceeded"
    return None


def _compact_sources(results: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    compacted: List[Dict[str, Any]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        compacted.append(
            {
                "title": item.get("title", "") or url,
                "url": url,
                "provider": item.get("provider", ""),
                "published_date": item.get("published_date"),
            }
        )
        if len(compacted) >= limit:
            break
    return compacted


@dataclass
class BranchBrief:
    id: str
    topic: str
    summary: str
    context_id: Optional[str] = None
    status: ArtifactStatus = "created"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class ResearchTask:
    id: str
    goal: str
    query: str
    priority: int
    status: TaskStatus = "ready"
    title: str = ""
    aspect: str = ""
    parent_task_id: Optional[str] = None
    parent_context_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    attempts: int = 0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    completed_at: Optional[str] = None
    last_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceCard:
    id: str
    task_id: str
    source_title: str
    source_url: str
    summary: str
    excerpt: str
    source_provider: str = ""
    published_date: Optional[str] = None
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGap:
    id: str
    aspect: str
    importance: str
    reason: str
    suggested_queries: List[str] = field(default_factory=list)
    related_task_ids: List[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class ReportSectionDraft:
    id: str
    task_id: str
    title: str
    summary: str
    evidence_ids: List[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class FinalReportArtifact:
    id: str
    report_markdown: str
    executive_summary: str
    citation_urls: List[str] = field(default_factory=list)
    status: ArtifactStatus = "completed"
    created_by: str = "reporter"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class AgentRunRecord:
    id: str
    role: AgentRole
    phase: str
    status: str
    agent_id: str
    task_id: Optional[str] = None
    started_at: str = field(default_factory=_now_iso)
    ended_at: str = ""
    summary: str = ""


@dataclass
class WorkerExecutionResult:
    task: ResearchTask
    context: ResearchWorkerContext
    evidence_cards: List[EvidenceCard]
    section_draft: Optional[ReportSectionDraft]
    raw_results: List[Dict[str, Any]]
    tokens_used: int


class ResearchTaskQueue:
    def __init__(self) -> None:
        self._tasks: Dict[str, ResearchTask] = {}
        self._lock = threading.Lock()

    def enqueue(self, tasks: List[ResearchTask]) -> None:
        with self._lock:
            for task in tasks:
                task.updated_at = _now_iso()
                self._tasks[task.id] = task

    def claim_ready_tasks(self, *, limit: int, agent_ids: List[str]) -> List[ResearchTask]:
        claimed: List[ResearchTask] = []
        with self._lock:
            ready = sorted(
                (task for task in self._tasks.values() if task.status == "ready"),
                key=lambda task: (task.priority, task.created_at),
            )
            for idx, task in enumerate(ready[: max(0, limit)]):
                task.status = "in_progress"
                task.assigned_agent_id = agent_ids[idx] if idx < len(agent_ids) else None
                task.attempts += 1
                task.updated_at = _now_iso()
                claimed.append(copy.deepcopy(task))
        return claimed

    def update_status(self, task_id: str, status: TaskStatus, *, reason: str = "") -> Optional[ResearchTask]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = status
            task.updated_at = _now_iso()
            if status == "completed":
                task.completed_at = task.updated_at
            if reason:
                task.last_error = reason
            return copy.deepcopy(task)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            tasks = [task.to_dict() for task in self._tasks.values()]
        return {
            "tasks": tasks,
            "stats": {
                "total": len(tasks),
                "ready": sum(1 for task in tasks if task["status"] == "ready"),
                "in_progress": sum(1 for task in tasks if task["status"] == "in_progress"),
                "completed": sum(1 for task in tasks if task["status"] == "completed"),
                "failed": sum(1 for task in tasks if task["status"] == "failed"),
                "blocked": sum(1 for task in tasks if task["status"] == "blocked"),
            },
        }

    def all_tasks(self) -> List[ResearchTask]:
        with self._lock:
            return [copy.deepcopy(task) for task in self._tasks.values()]

    def ready_count(self) -> int:
        with self._lock:
            return sum(1 for task in self._tasks.values() if task.status == "ready")

    def completed_count(self) -> int:
        with self._lock:
            return sum(1 for task in self._tasks.values() if task.status == "completed")


class ArtifactStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._briefs: Dict[str, BranchBrief] = {}
        self._evidence_cards: Dict[str, EvidenceCard] = {}
        self._knowledge_gaps: Dict[str, KnowledgeGap] = {}
        self._section_drafts: Dict[str, ReportSectionDraft] = {}
        self._final_report: Optional[FinalReportArtifact] = None

    def put_brief(self, brief: BranchBrief) -> None:
        with self._lock:
            brief.updated_at = _now_iso()
            self._briefs[brief.id] = brief

    def add_evidence(self, evidence_cards: List[EvidenceCard]) -> None:
        with self._lock:
            for card in evidence_cards:
                card.updated_at = _now_iso()
                self._evidence_cards[card.id] = card

    def replace_gaps(self, gaps: List[KnowledgeGap]) -> None:
        with self._lock:
            self._knowledge_gaps = {}
            for gap in gaps:
                gap.updated_at = _now_iso()
                self._knowledge_gaps[gap.id] = gap

    def add_section_draft(self, section: ReportSectionDraft) -> None:
        with self._lock:
            section.updated_at = _now_iso()
            self._section_drafts[section.id] = section

    def set_final_report(self, artifact: FinalReportArtifact) -> None:
        with self._lock:
            artifact.updated_at = _now_iso()
            self._final_report = artifact

    def get_related_artifacts(self, task_id: str) -> Dict[str, List[Dict[str, Any]]]:
        with self._lock:
            evidence = [asdict(card) for card in self._evidence_cards.values() if card.task_id == task_id]
            sections = [
                asdict(section)
                for section in self._section_drafts.values()
                if section.task_id == task_id
            ]
            gaps = [asdict(gap) for gap in self._knowledge_gaps.values()]
        return {
            "evidence_cards": evidence,
            "section_drafts": sections,
            "knowledge_gaps": gaps,
        }

    def evidence_cards(self) -> List[EvidenceCard]:
        with self._lock:
            return [copy.deepcopy(card) for card in self._evidence_cards.values()]

    def gap_artifacts(self) -> List[KnowledgeGap]:
        with self._lock:
            return [copy.deepcopy(gap) for gap in self._knowledge_gaps.values()]

    def section_drafts(self) -> List[ReportSectionDraft]:
        with self._lock:
            return [copy.deepcopy(section) for section in self._section_drafts.values()]

    def final_report(self) -> Optional[FinalReportArtifact]:
        with self._lock:
            return copy.deepcopy(self._final_report)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "branch_briefs": [asdict(brief) for brief in self._briefs.values()],
                "evidence_cards": [asdict(card) for card in self._evidence_cards.values()],
                "knowledge_gaps": [asdict(gap) for gap in self._knowledge_gaps.values()],
                "report_section_drafts": [asdict(section) for section in self._section_drafts.values()],
                "final_report": asdict(self._final_report) if self._final_report else None,
            }


class MultiAgentDeepSearchRuntime:
    def __init__(self, state: Dict[str, Any], config: Dict[str, Any]):
        self.state = dict(state)
        self.config = dict(config or {})
        self.cfg = self.config.get("configurable") or {}
        if not isinstance(self.cfg, dict):
            self.cfg = {}

        self.topic = str(self.state.get("input") or self.state.get("topic") or "").strip()
        self.thread_id = str(self.cfg.get("thread_id") or self.state.get("cancel_token_id") or "").strip()
        self.emitter = get_emitter_sync(self.thread_id) if self.thread_id else None

        self.start_ts = time.time()
        self.max_epochs = max(1, _configurable_int(self.config, "deepsearch_max_epochs", settings.deepsearch_max_epochs))
        self.query_num = max(1, _configurable_int(self.config, "deepsearch_query_num", settings.deepsearch_query_num))
        self.results_per_query = max(
            1,
            _configurable_int(
                self.config,
                "deepsearch_results_per_query",
                settings.deepsearch_results_per_query,
            ),
        )
        self.parallel_workers = max(
            1,
            _configurable_int(self.config, "tree_parallel_branches", settings.tree_parallel_branches),
        )
        self.max_seconds = max(0.0, _configurable_float(self.config, "deepsearch_max_seconds", settings.deepsearch_max_seconds))
        self.max_tokens = max(0, _configurable_int(self.config, "deepsearch_max_tokens", settings.deepsearch_max_tokens))
        self.max_searches = max(
            0,
            _configurable_int(
                self.config,
                "deepsearch_tree_max_searches",
                settings.deepsearch_tree_max_searches,
            ),
        )

        self.provider_profile = _resolve_provider_profile(self.state)
        self.task_queue = ResearchTaskQueue()
        self.artifact_store = ArtifactStore()
        self.agent_runs: List[AgentRunRecord] = []
        self._agent_run_lock = threading.Lock()
        self._counter_lock = threading.Lock()
        self._role_counter: Dict[str, int] = {}

        self.searches_used = 0
        self.tokens_used = 0
        self.budget_stop_reason: Optional[str] = None

        planner_model = _model_for_task("planning", self.config)
        researcher_model = _model_for_task("research", self.config)
        reporter_model = _model_for_task("writing", self.config)
        verifier_model = _model_for_task("gap_analysis", self.config)
        coordinator_model = _model_for_task("planning", self.config)

        self.planner = ResearchPlanner(create_chat_model(planner_model, temperature=0), self.config)
        self.researcher = ResearchAgent(
            create_chat_model(researcher_model, temperature=0),
            self._search_with_tracking,
            self.config,
        )
        self.reporter = ResearchReporter(create_chat_model(reporter_model, temperature=0), self.config)
        self.verifier = KnowledgeGapAnalyzer(create_chat_model(verifier_model, temperature=0), self.config)
        self.coordinator = ResearchCoordinator(create_chat_model(coordinator_model, temperature=0), self.config)

    def run(self) -> Dict[str, Any]:
        try:
            return self._run()
        except asyncio.CancelledError:
            return {
                "is_cancelled": True,
                "is_complete": True,
                "errors": ["DeepSearch was cancelled"],
                "final_report": "任务已被取消",
            }

    def _run(self) -> Dict[str, Any]:
        self._check_cancel()
        root_brief = BranchBrief(
            id=_new_id("brief"),
            topic=self.topic,
            summary=f"围绕主题“{self.topic}”开展多 agent Deep Research。",
        )
        self.artifact_store.put_brief(root_brief)
        self._emit_artifact_update(
            artifact_id=root_brief.id,
            artifact_type="branch_brief",
            status=root_brief.status,
            summary=root_brief.summary,
        )

        self._plan_tasks(reason="initial_plan", context_id=root_brief.id)

        latest_gap_result: Optional[GapAnalysisResult] = None
        current_iteration = 0

        while current_iteration < self.max_epochs:
            self._check_cancel()
            current_iteration += 1

            self._emit_decision(
                decision_type="research",
                reason="执行当前可调度的研究任务",
                iteration=current_iteration,
                coverage=latest_gap_result.overall_coverage if latest_gap_result else None,
                gap_count=len(latest_gap_result.gaps) if latest_gap_result else None,
            )

            worker_results = self._dispatch_ready_tasks(current_iteration)
            if worker_results:
                for result in worker_results:
                    self._merge_worker_result(result)

            latest_gap_result = self._verify_coverage(current_iteration)
            decision = self._decide_next_action(current_iteration, latest_gap_result)

            if self.budget_stop_reason:
                self._emit_decision(
                    decision_type="budget_stop",
                    reason=self.budget_stop_reason,
                    iteration=current_iteration,
                    coverage=latest_gap_result.overall_coverage,
                    gap_count=len(latest_gap_result.gaps),
                )
                break

            if decision.action in {CoordinatorAction.COMPLETE, CoordinatorAction.SYNTHESIZE}:
                break

            if decision.action in {CoordinatorAction.PLAN, CoordinatorAction.RESEARCH, CoordinatorAction.REFLECT}:
                if latest_gap_result and latest_gap_result.gaps:
                    created = self._replan_from_gaps(
                        current_iteration=current_iteration,
                        gap_result=latest_gap_result,
                    )
                    if not created:
                        break
                elif self.task_queue.ready_count() == 0:
                    break

            if self.task_queue.ready_count() == 0:
                break

        return self._generate_final_result(current_iteration, latest_gap_result)

    def _check_cancel(self) -> None:
        if self.state.get("is_cancelled"):
            raise asyncio.CancelledError("Task was cancelled (flag)")
        token_id = self.state.get("cancel_token_id")
        if token_id:
            _check_cancel_token(token_id)

    def _next_agent_id(self, role: AgentRole) -> str:
        with self._counter_lock:
            self._role_counter[role] = self._role_counter.get(role, 0) + 1
            return f"{role}-{self._role_counter[role]}"

    def _start_agent_run(
        self,
        *,
        role: AgentRole,
        phase: str,
        task_id: Optional[str] = None,
        iteration: Optional[int] = None,
    ) -> AgentRunRecord:
        record = AgentRunRecord(
            id=_new_id("agent_run"),
            role=role,
            phase=phase,
            status="running",
            agent_id=self._next_agent_id(role),
            task_id=task_id,
        )
        with self._agent_run_lock:
            self.agent_runs.append(record)
        self._emit_agent_start(
            agent_id=record.agent_id,
            role=record.role,
            phase=phase,
            task_id=task_id,
            iteration=iteration,
        )
        return record

    def _finish_agent_run(
        self,
        record: AgentRunRecord,
        *,
        status: str,
        summary: str = "",
        iteration: Optional[int] = None,
    ) -> None:
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
        )

    def _search_with_tracking(self, payload: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        query = str(payload.get("query") or "").strip()
        max_results = int(payload.get("max_results") or self.results_per_query)
        results = _search_query(query, max_results, config, self.provider_profile)
        if query:
            self._emit(
                ToolEventType.SEARCH,
                {
                    "query": query,
                    "provider": "multi_search",
                    "results": _compact_sources(results, limit=min(len(results), 5)),
                    "count": len(results),
                    "engine": "multi_agent",
                },
            )
        return results

    def _plan_tasks(self, *, reason: str, context_id: str) -> List[ResearchTask]:
        record = self._start_agent_run(role="planner", phase=reason)
        try:
            existing_queries = [
                task.query
                for task in self.task_queue.all_tasks()
                if task.query
            ]
            knowledge = self._knowledge_summary()
            plan_items = self.planner.create_plan(
                self.topic,
                num_queries=self.query_num,
                existing_knowledge=knowledge,
                existing_queries=existing_queries,
            )
            tasks = self._build_tasks_from_plan(plan_items, context_id=context_id)
            self.task_queue.enqueue(tasks)
            for task in tasks:
                self._emit_task_update(task=task, status=task.status)
            self._emit_research_tree_update()
            self._finish_agent_run(
                record,
                status="completed",
                summary=f"生成 {len(tasks)} 个研究任务",
            )
            return tasks
        except Exception as exc:
            self._finish_agent_run(record, status="failed", summary=str(exc))
            raise

    def _replan_from_gaps(
        self,
        *,
        current_iteration: int,
        gap_result: GapAnalysisResult,
    ) -> int:
        record = self._start_agent_run(role="planner", phase="replan", iteration=current_iteration)
        try:
            existing_queries = [
                task.query
                for task in self.task_queue.all_tasks()
                if task.query
            ]
            gap_labels = [gap.aspect for gap in gap_result.gaps]
            plan_items = self.planner.refine_plan(
                self.topic,
                gaps=gap_labels,
                existing_queries=existing_queries,
                num_queries=min(self.query_num, max(1, len(gap_result.suggested_queries) or len(gap_labels))),
            )
            tasks = self._build_tasks_from_plan(
                plan_items,
                context_id=f"replan-{current_iteration}",
            )
            if tasks:
                self.task_queue.enqueue(tasks)
                for task in tasks:
                    self._emit_task_update(task=task, status=task.status)
                self._emit_research_tree_update()
            self._finish_agent_run(
                record,
                status="completed",
                summary=f"针对知识缺口补充 {len(tasks)} 个任务",
                iteration=current_iteration,
            )
            return len(tasks)
        except Exception as exc:
            self._finish_agent_run(record, status="failed", summary=str(exc), iteration=current_iteration)
            raise

    def _build_tasks_from_plan(
        self,
        plan_items: List[Dict[str, Any]],
        *,
        context_id: str,
    ) -> List[ResearchTask]:
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
                    id=_new_id("task"),
                    goal=title,
                    query=query,
                    priority=priority,
                    title=title,
                    aspect=aspect,
                    parent_context_id=context_id,
                )
            )
        return tasks

    def _dispatch_ready_tasks(self, current_iteration: int) -> List[WorkerExecutionResult]:
        self.budget_stop_reason = _budget_stop_reason(
            start_ts=self.start_ts,
            searches_used=self.searches_used,
            tokens_used=self.tokens_used,
            max_seconds=self.max_seconds,
            max_tokens=self.max_tokens,
            max_searches=self.max_searches,
        )
        if self.budget_stop_reason:
            return []

        remaining_search_slots = self.parallel_workers
        if self.max_searches > 0:
            remaining_search_slots = min(
                remaining_search_slots,
                max(0, self.max_searches - self.searches_used),
            )
        if remaining_search_slots <= 0:
            self.budget_stop_reason = "search_budget_exceeded"
            return []

        agent_ids = [self._next_agent_id("researcher") for _ in range(remaining_search_slots)]
        claimed = self.task_queue.claim_ready_tasks(limit=remaining_search_slots, agent_ids=agent_ids)
        if not claimed:
            return []

        for task in claimed:
            self._emit_task_update(task=task, status=task.status)

        results: List[WorkerExecutionResult] = []
        with ThreadPoolExecutor(max_workers=min(len(claimed), self.parallel_workers)) as executor:
            futures = {
                executor.submit(self._run_worker_task, task, current_iteration): task
                for task in claimed
            }
            for future in as_completed(futures):
                results.append(future.result())
        return results

    def _run_worker_task(
        self,
        task: ResearchTask,
        current_iteration: int,
    ) -> WorkerExecutionResult:
        agent_id = task.assigned_agent_id or self._next_agent_id("researcher")
        record = AgentRunRecord(
            id=_new_id("agent_run"),
            role="researcher",
            phase="research",
            status="running",
            agent_id=agent_id,
            task_id=task.id,
        )
        with self._agent_run_lock:
            self.agent_runs.append(record)
        self._emit_agent_start(
            agent_id=agent_id,
            role="researcher",
            phase="research",
            task_id=task.id,
            iteration=current_iteration,
        )

        worker_context = build_research_worker_context(
            self.state,
            task_id=task.id,
            agent_id=agent_id,
            query=task.query,
            topic=self.topic,
            brief={
                "topic": self.topic,
                "goal": task.goal,
                "aspect": task.aspect,
                "iteration": current_iteration,
            },
            related_artifacts=self.artifact_store.get_related_artifacts(task.id),
        )

        try:
            self._check_cancel()
            results = self.researcher.execute_queries(
                [task.query],
                max_results_per_query=self.results_per_query,
            )
            summary = self.researcher.summarize_findings(
                self.topic,
                results,
                existing_summary=self._knowledge_summary(),
            )
            evidence_cards: List[EvidenceCard] = []
            for item in results[: min(3, len(results))]:
                evidence_cards.append(
                    EvidenceCard(
                        id=_new_id("evidence"),
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
                id=_new_id("section"),
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
            worker_context.sources.extend(_compact_sources(results, limit=10))
            worker_context.artifacts_created.extend(
                [asdict(card) for card in evidence_cards] + [asdict(section_draft)]
            )
            worker_context.is_complete = True

            record.status = "completed"
            record.summary = section_draft.summary[:240]
            record.ended_at = _now_iso()
            self._emit_agent_complete(
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
                tokens_used=_estimate_tokens_from_results(results) + _estimate_tokens_from_text(summary),
            )
        except Exception as exc:
            worker_context.errors.append(str(exc))
            worker_context.is_complete = True
            record.status = "failed"
            record.summary = str(exc)
            record.ended_at = _now_iso()
            self._emit_agent_complete(
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

    def _merge_worker_result(self, result: WorkerExecutionResult) -> None:
        updates = merge_research_worker_context(self.state, result.context)
        self.state.update(updates)
        self.searches_used += 1
        self.tokens_used += max(0, result.tokens_used)

        if result.evidence_cards:
            self.artifact_store.add_evidence(result.evidence_cards)
            for card in result.evidence_cards:
                self._emit_artifact_update(
                    artifact_id=card.id,
                    artifact_type="evidence_card",
                    status=card.status,
                    task_id=card.task_id,
                    agent_id=card.created_by,
                    summary=card.summary[:180],
                    source_url=card.source_url,
                )

        if result.section_draft:
            self.artifact_store.add_section_draft(result.section_draft)
            self._emit_artifact_update(
                artifact_id=result.section_draft.id,
                artifact_type="report_section_draft",
                status=result.section_draft.status,
                task_id=result.section_draft.task_id,
                agent_id=result.section_draft.created_by,
                summary=result.section_draft.summary[:180],
            )

        if result.raw_results:
            updated_task = self.task_queue.update_status(result.task.id, "completed")
        else:
            updated_task = self.task_queue.update_status(
                result.task.id,
                "failed",
                reason="researcher returned no results",
            )
        if updated_task:
            self._emit_task_update(task=updated_task, status=updated_task.status)

        self._emit_research_tree_update()

    def _verify_coverage(self, current_iteration: int) -> GapAnalysisResult:
        record = self._start_agent_run(role="verifier", phase="coverage_check", iteration=current_iteration)
        try:
            knowledge = self._knowledge_summary()
            executed_queries = [task.query for task in self.task_queue.all_tasks() if task.status == "completed"]
            gap_result = self.verifier.analyze(
                self.topic,
                executed_queries=executed_queries,
                collected_knowledge=knowledge,
            )
            gap_artifacts = [
                KnowledgeGap(
                    id=_new_id("gap"),
                    aspect=gap.aspect,
                    importance=gap.importance,
                    reason=gap.reason,
                    suggested_queries=gap_result.suggested_queries,
                )
                for gap in gap_result.gaps
            ]
            self.artifact_store.replace_gaps(gap_artifacts)
            for gap in gap_artifacts:
                self._emit_artifact_update(
                    artifact_id=gap.id,
                    artifact_type="knowledge_gap",
                    status=gap.status,
                    summary=f"{gap.aspect}: {gap.reason}",
                )

            quality_summary = self._quality_summary(gap_result)
            self._emit(ToolEventType.QUALITY_UPDATE, quality_summary)
            self._finish_agent_run(
                record,
                status="completed",
                summary=f"coverage={gap_result.overall_coverage:.2f}, gaps={len(gap_result.gaps)}",
                iteration=current_iteration,
            )
            return gap_result
        except Exception as exc:
            self._finish_agent_run(record, status="failed", summary=str(exc), iteration=current_iteration)
            raise

    def _decide_next_action(
        self,
        current_iteration: int,
        gap_result: GapAnalysisResult,
    ):
        record = self._start_agent_run(role="coordinator", phase="loop_decision", iteration=current_iteration)
        try:
            evidence_count = len(self.artifact_store.evidence_cards())
            section_count = len(self.artifact_store.section_drafts())
            unique_urls = {
                card.source_url
                for card in self.artifact_store.evidence_cards()
                if card.source_url
            }
            citation_accuracy = min(1.0, len(unique_urls) / max(1, evidence_count))
            decision = self.coordinator.decide_next_action(
                topic=self.topic,
                num_queries=self.task_queue.completed_count(),
                num_sources=len(unique_urls),
                num_summaries=section_count,
                current_epoch=current_iteration,
                max_epochs=self.max_epochs,
                knowledge_summary=self._knowledge_summary(),
                quality_score=gap_result.overall_coverage,
                quality_gap_count=len(gap_result.gaps),
                citation_accuracy=citation_accuracy,
            )
            self._emit_decision(
                decision_type=decision.action.value,
                reason=decision.reasoning,
                iteration=current_iteration,
                coverage=gap_result.overall_coverage,
                gap_count=len(gap_result.gaps),
            )
            self._finish_agent_run(
                record,
                status="completed",
                summary=f"{decision.action.value}: {decision.reasoning}",
                iteration=current_iteration,
            )
            return decision
        except Exception as exc:
            self._finish_agent_run(record, status="failed", summary=str(exc), iteration=current_iteration)
            raise

    def _generate_final_result(
        self,
        current_iteration: int,
        gap_result: Optional[GapAnalysisResult],
    ) -> Dict[str, Any]:
        record = self._start_agent_run(role="reporter", phase="final_report", iteration=current_iteration)
        try:
            section_drafts = self.artifact_store.section_drafts()
            findings = [section.summary for section in section_drafts if section.summary]
            evidence_cards = self.artifact_store.evidence_cards()
            citation_urls = [card.source_url for card in evidence_cards if card.source_url]

            final_report = self.reporter.generate_report(
                self.topic,
                findings=findings or [self._knowledge_summary() or "暂无充分结论"],
                sources=citation_urls[: max(5, min(20, len(citation_urls)))],
            )
            executive_summary = self.reporter.generate_executive_summary(final_report, self.topic)
            final_artifact = FinalReportArtifact(
                id=_new_id("final_report"),
                report_markdown=final_report,
                executive_summary=executive_summary,
                citation_urls=citation_urls,
            )
            self.artifact_store.set_final_report(final_artifact)
            self._emit_artifact_update(
                artifact_id=final_artifact.id,
                artifact_type="final_report",
                status=final_artifact.status,
                agent_id=final_artifact.created_by,
                summary=executive_summary[:180],
            )
            self._finish_agent_run(
                record,
                status="completed",
                summary=executive_summary[:240] or "完成最终报告生成",
                iteration=current_iteration,
            )

            elapsed = max(0.0, time.time() - self.start_ts)
            quality_summary = self._quality_summary(gap_result)
            deepsearch_artifacts = {
                "mode": "multi_agent",
                "engine": "multi_agent",
                "task_queue": self.task_queue.snapshot(),
                "artifact_store": self.artifact_store.snapshot(),
                "research_tree": self._research_tree_snapshot(),
                "quality_summary": quality_summary,
                "runtime_state": self._runtime_state_snapshot(current_iteration),
            }

            self._emit(
                ToolEventType.RESEARCH_NODE_COMPLETE,
                {
                    "node_id": "deepsearch_multi_agent",
                    "summary": executive_summary or final_report[:1200],
                    "sources": _compact_sources(
                        [asdict(card) for card in evidence_cards],
                        limit=max(5, min(20, len(evidence_cards))),
                    ),
                    "quality": quality_summary,
                    "engine": "multi_agent",
                    "iteration": current_iteration,
                },
            )

            messages = [AIMessage(content=final_report)]
            if executive_summary:
                messages.append(AIMessage(content=f"执行摘要：{executive_summary}"))
            if self.budget_stop_reason:
                messages.append(AIMessage(content=f"（预算限制提示：{self.budget_stop_reason}）"))

            return {
                "research_plan": [task.query for task in self.task_queue.all_tasks()],
                "scraped_content": self.state.get("scraped_content", []),
                "draft_report": final_report,
                "final_report": final_report,
                "quality_summary": quality_summary,
                "sources": _compact_sources(
                    [asdict(card) for card in evidence_cards],
                    limit=max(5, min(20, len(evidence_cards))),
                ),
                "deepsearch_artifacts": deepsearch_artifacts,
                "deepsearch_mode": "multi_agent",
                "deepsearch_engine": "multi_agent",
                "deepsearch_task_queue": self.task_queue.snapshot(),
                "deepsearch_artifact_store": self.artifact_store.snapshot(),
                "deepsearch_runtime_state": self._runtime_state_snapshot(current_iteration),
                "deepsearch_agent_runs": [asdict(record) for record in self.agent_runs],
                "research_tree": self._research_tree_snapshot(),
                "messages": messages,
                "is_complete": False,
                "budget_stop_reason": self.budget_stop_reason,
                "deepsearch_tokens_used": self.tokens_used,
                "deepsearch_elapsed_seconds": elapsed,
            }
        except Exception as exc:
            self._finish_agent_run(record, status="failed", summary=str(exc), iteration=current_iteration)
            raise

    def _runtime_state_snapshot(self, current_iteration: int) -> Dict[str, Any]:
        return {
            "engine": "multi_agent",
            "current_iteration": current_iteration,
            "max_iterations": self.max_epochs,
            "searches_used": self.searches_used,
            "tokens_used": self.tokens_used,
            "max_searches": self.max_searches,
            "max_tokens": self.max_tokens,
            "max_seconds": self.max_seconds,
            "budget_stop_reason": self.budget_stop_reason,
            "elapsed_seconds": round(max(0.0, time.time() - self.start_ts), 3),
        }

    def _research_tree_snapshot(self) -> Dict[str, Any]:
        tasks = sorted(self.task_queue.all_tasks(), key=lambda task: (task.priority, task.created_at))
        return {
            "id": "deepsearch_multi_agent",
            "topic": self.topic,
            "engine": "multi_agent",
            "children": [
                {
                    "id": task.id,
                    "title": task.title or task.goal,
                    "query": task.query,
                    "status": task.status,
                    "priority": task.priority,
                    "parent_context_id": task.parent_context_id,
                }
                for task in tasks
            ],
        }

    def _knowledge_summary(self) -> str:
        sections = [section.summary for section in self.artifact_store.section_drafts() if section.summary]
        if sections:
            return "\n\n".join(sections[:8])
        notes = self.state.get("summary_notes", [])
        if isinstance(notes, list) and notes:
            return "\n\n".join(str(note) for note in notes[:8])
        return ""

    def _quality_summary(self, gap_result: Optional[GapAnalysisResult]) -> Dict[str, Any]:
        evidence_cards = self.artifact_store.evidence_cards()
        unique_urls = {
            card.source_url
            for card in evidence_cards
            if card.source_url
        }
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
        }

    def _emit(self, event_type: ToolEventType | str, payload: Dict[str, Any]) -> None:
        if not self.emitter:
            return
        try:
            self.emitter.emit_sync(event_type, payload)
        except Exception as exc:
            logger.debug("[deepsearch-multi-agent] failed to emit %s: %s", event_type, exc)

    def _emit_task_update(self, *, task: ResearchTask, status: str) -> None:
        payload = {
            "task_id": task.id,
            "status": status,
            "title": task.title or task.goal,
            "query": task.query,
            "parent_context_id": task.parent_context_id,
            "agent_id": task.assigned_agent_id,
            "priority": task.priority,
        }
        self._emit(ToolEventType.RESEARCH_TASK_UPDATE, payload)
        self._emit(
            ToolEventType.TASK_UPDATE,
            {
                "id": task.id,
                "status": status,
                "title": task.title or task.goal,
            },
        )

    def _emit_artifact_update(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        status: str,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        summary: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "status": status,
        }
        if task_id:
            payload["task_id"] = task_id
        if agent_id:
            payload["agent_id"] = agent_id
        if summary:
            payload["summary"] = summary
        if source_url:
            payload["source_url"] = source_url
        self._emit(ToolEventType.RESEARCH_ARTIFACT_UPDATE, payload)

    def _emit_agent_start(
        self,
        *,
        agent_id: str,
        role: AgentRole,
        phase: str,
        task_id: Optional[str] = None,
        iteration: Optional[int] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "agent_id": agent_id,
            "role": role,
            "phase": phase,
        }
        if task_id:
            payload["task_id"] = task_id
        if iteration is not None:
            payload["iteration"] = iteration
        self._emit(ToolEventType.RESEARCH_AGENT_START, payload)

    def _emit_agent_complete(
        self,
        *,
        agent_id: str,
        role: AgentRole,
        phase: str,
        status: str,
        task_id: Optional[str] = None,
        iteration: Optional[int] = None,
        summary: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "agent_id": agent_id,
            "role": role,
            "phase": phase,
            "status": status,
        }
        if task_id:
            payload["task_id"] = task_id
        if iteration is not None:
            payload["iteration"] = iteration
        if summary:
            payload["summary"] = summary
        self._emit(ToolEventType.RESEARCH_AGENT_COMPLETE, payload)

    def _emit_decision(
        self,
        *,
        decision_type: str,
        reason: str,
        iteration: Optional[int] = None,
        coverage: Optional[float] = None,
        gap_count: Optional[int] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "decision_type": decision_type,
            "reason": reason,
        }
        if iteration is not None:
            payload["iteration"] = iteration
        if coverage is not None:
            payload["coverage"] = coverage
        if gap_count is not None:
            payload["gap_count"] = gap_count
        self._emit(ToolEventType.RESEARCH_DECISION, payload)

    def _emit_research_tree_update(self) -> None:
        self._emit(
            ToolEventType.RESEARCH_TREE_UPDATE,
            {
                "tree": self._research_tree_snapshot(),
                "engine": "multi_agent",
                "quality": self._quality_summary(None),
            },
        )


def run_multi_agent_deepsearch(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    runtime = MultiAgentDeepSearchRuntime(state, config)
    return runtime.run()
