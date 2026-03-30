"""
Runtime entrypoints for the multi-agent deep runtime.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from agent.core.state import build_deep_runtime_snapshot
from agent.runtime.deep.multi_agent import dispatcher, events, support
from agent.runtime.deep.multi_agent.schema import (
    AgentRole,
    AgentRunRecord,
    BranchBrief,
    FinalReportArtifact,
    KnowledgeGap,
    ResearchTask,
    WorkerExecutionResult,
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


class MultiAgentDeepSearchRuntime:
    def __init__(self, state: Dict[str, Any], config: Dict[str, Any]):
        deps = _resolve_deps()
        self._deps = deps
        self.state = dict(state)
        self.config = dict(config or {})
        self.cfg = self.config.get("configurable") or {}
        if not isinstance(self.cfg, dict):
            self.cfg = {}

        self.topic = str(self.state.get("input") or self.state.get("topic") or "").strip()
        self.thread_id = str(
            self.cfg.get("thread_id") or self.state.get("cancel_token_id") or ""
        ).strip()
        self.emitter = deps.get_emitter_sync(self.thread_id) if self.thread_id else None

        self.start_ts = time.time()
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

        self.provider_profile = support._resolve_provider_profile(self.state)
        self.task_queue = ResearchTaskQueue()
        self.artifact_store = ArtifactStore()
        self.agent_runs: List[AgentRunRecord] = []
        self._agent_run_lock = threading.Lock()
        self._counter_lock = threading.Lock()
        self._role_counter: Dict[str, int] = {}

        self.searches_used = 0
        self.tokens_used = 0
        self.budget_stop_reason: Optional[str] = None

        planner_model = support._model_for_task("planning", self.config)
        researcher_model = support._model_for_task("research", self.config)
        reporter_model = support._model_for_task("writing", self.config)
        verifier_model = support._model_for_task("gap_analysis", self.config)
        coordinator_model = support._model_for_task("planning", self.config)

        self.planner = deps.ResearchPlanner(
            deps.create_chat_model(planner_model, temperature=0),
            self.config,
        )
        self.researcher = deps.ResearchAgent(
            deps.create_chat_model(researcher_model, temperature=0),
            self._search_with_tracking,
            self.config,
        )
        self.reporter = deps.ResearchReporter(
            deps.create_chat_model(reporter_model, temperature=0),
            self.config,
        )
        self.verifier = deps.KnowledgeGapAnalyzer(
            deps.create_chat_model(verifier_model, temperature=0),
            self.config,
        )
        self.coordinator = deps.ResearchCoordinator(
            deps.create_chat_model(coordinator_model, temperature=0),
            self.config,
        )

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
            id=support._new_id("brief"),
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

            if decision.action in {
                CoordinatorAction.PLAN,
                CoordinatorAction.RESEARCH,
                CoordinatorAction.REFLECT,
            }:
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
            id=support._new_id("agent_run"),
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
        results = support._search_query(query, max_results, config, self.provider_profile)
        if query:
            self._emit(
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

    def _build_tasks_from_plan(
        self,
        plan_items: List[Dict[str, Any]],
        *,
        context_id: str,
    ) -> List[ResearchTask]:
        return dispatcher.build_tasks_from_plan(self, plan_items, context_id=context_id)

    def _plan_tasks(self, *, reason: str, context_id: str) -> List[ResearchTask]:
        record = self._start_agent_run(role="planner", phase=reason)
        try:
            existing_queries = [task.query for task in self.task_queue.all_tasks() if task.query]
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
            existing_queries = [task.query for task in self.task_queue.all_tasks() if task.query]
            gap_labels = [gap.aspect for gap in gap_result.gaps]
            plan_items = self.planner.refine_plan(
                self.topic,
                gaps=gap_labels,
                existing_queries=existing_queries,
                num_queries=min(
                    self.query_num,
                    max(1, len(gap_result.suggested_queries) or len(gap_labels)),
                ),
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
            self._finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=current_iteration,
            )
            raise

    def _dispatch_ready_tasks(self, current_iteration: int) -> List[WorkerExecutionResult]:
        return dispatcher.dispatch_ready_tasks(self, current_iteration)

    def _run_worker_task(
        self,
        task: ResearchTask,
        current_iteration: int,
    ) -> WorkerExecutionResult:
        return dispatcher.run_worker_task(self, task, current_iteration)

    def _merge_worker_result(self, result: WorkerExecutionResult) -> None:
        dispatcher.merge_worker_result(self, result)

    def _verify_coverage(self, current_iteration: int) -> GapAnalysisResult:
        record = self._start_agent_run(
            role="verifier",
            phase="coverage_check",
            iteration=current_iteration,
        )
        try:
            knowledge = self._knowledge_summary()
            executed_queries = [
                task.query for task in self.task_queue.all_tasks() if task.status == "completed"
            ]
            gap_result = self.verifier.analyze(
                self.topic,
                executed_queries=executed_queries,
                collected_knowledge=knowledge,
            )
            gap_artifacts = [
                KnowledgeGap(
                    id=support._new_id("gap"),
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
            self._emit(events.ToolEventType.QUALITY_UPDATE, quality_summary)
            self._finish_agent_run(
                record,
                status="completed",
                summary=f"coverage={gap_result.overall_coverage:.2f}, gaps={len(gap_result.gaps)}",
                iteration=current_iteration,
            )
            return gap_result
        except Exception as exc:
            self._finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=current_iteration,
            )
            raise

    def _decide_next_action(self, current_iteration: int, gap_result: GapAnalysisResult):
        record = self._start_agent_run(
            role="coordinator",
            phase="loop_decision",
            iteration=current_iteration,
        )
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
            self._finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=current_iteration,
            )
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
                id=support._new_id("final_report"),
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
                events.ToolEventType.RESEARCH_NODE_COMPLETE,
                {
                    "node_id": "deepsearch_multi_agent",
                    "summary": executive_summary or final_report[:1200],
                    "sources": support._compact_sources(
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
                "deep_runtime": build_deep_runtime_snapshot(
                    engine="multi_agent",
                    task_queue=self.task_queue.snapshot(),
                    artifact_store=self.artifact_store.snapshot(),
                    runtime_state=self._runtime_state_snapshot(current_iteration),
                    agent_runs=[asdict(run) for run in self.agent_runs],
                ),
                "research_plan": [task.query for task in self.task_queue.all_tasks()],
                "scraped_content": self.state.get("scraped_content", []),
                "draft_report": final_report,
                "final_report": final_report,
                "quality_summary": quality_summary,
                "sources": support._compact_sources(
                    [asdict(card) for card in evidence_cards],
                    limit=max(5, min(20, len(evidence_cards))),
                ),
                "deepsearch_artifacts": deepsearch_artifacts,
                "deepsearch_mode": "multi_agent",
                "deepsearch_engine": "multi_agent",
                "deepsearch_task_queue": self.task_queue.snapshot(),
                "deepsearch_artifact_store": self.artifact_store.snapshot(),
                "deepsearch_runtime_state": self._runtime_state_snapshot(current_iteration),
                "deepsearch_agent_runs": [asdict(run) for run in self.agent_runs],
                "research_tree": self._research_tree_snapshot(),
                "messages": messages,
                "is_complete": False,
                "budget_stop_reason": self.budget_stop_reason,
                "deepsearch_tokens_used": self.tokens_used,
                "deepsearch_elapsed_seconds": elapsed,
            }
        except Exception as exc:
            self._finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=current_iteration,
            )
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
        }

    def _emit(self, event_type: events.ToolEventType | str, payload: Dict[str, Any]) -> None:
        events.emit(self.emitter, event_type, payload)

    def _emit_task_update(self, *, task: ResearchTask, status: str) -> None:
        events.emit_task_update(self, task=task, status=status)

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
        role: AgentRole,
        phase: str,
        task_id: Optional[str] = None,
        iteration: Optional[int] = None,
    ) -> None:
        events.emit_agent_start(
            self,
            agent_id=agent_id,
            role=role,
            phase=phase,
            task_id=task_id,
            iteration=iteration,
        )

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
        events.emit_agent_complete(
            self,
            agent_id=agent_id,
            role=role,
            phase=phase,
            status=status,
            task_id=task_id,
            iteration=iteration,
            summary=summary,
        )

    def _emit_decision(
        self,
        *,
        decision_type: str,
        reason: str,
        iteration: Optional[int] = None,
        coverage: Optional[float] = None,
        gap_count: Optional[int] = None,
    ) -> None:
        events.emit_decision(
            self,
            decision_type=decision_type,
            reason=reason,
            iteration=iteration,
            coverage=coverage,
            gap_count=gap_count,
        )

    def _emit_research_tree_update(self) -> None:
        events.emit_research_tree_update(self)


def run_multi_agent_deepsearch(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    runtime = MultiAgentDeepSearchRuntime(state, config)
    return runtime.run()


__all__ = ["GapAnalysisResult", "MultiAgentDeepSearchRuntime", "run_multi_agent_deepsearch"]
