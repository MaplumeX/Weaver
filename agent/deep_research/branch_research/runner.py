"""
Bounded multi-round branch runner for deep research.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from agent.deep_research.branch_research import assess
from agent.deep_research.branch_research.artifacts import build_branch_artifacts
from agent.deep_research.branch_research.contracts import (
    BranchContradictionSummary,
    BranchCoverageSummary,
    BranchGroundingSummary,
    BranchQualitySummary,
)
from agent.deep_research.branch_research.planner import BranchQueryPlanner
from agent.deep_research.branch_research.shared import canonical_url, dedupe_strings
from agent.deep_research.branch_research.state import BranchResearchState
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import (
    BranchDecisionArtifact,
    BranchQueryRoundArtifact,
    ResearchTask,
)


class BranchResearchRunner:
    def __init__(
        self,
        *,
        llm: Any,
        config: dict[str, Any],
        query_planner: BranchQueryPlanner,
        search_cb: Callable[[list[str], int], list[dict[str, Any]]],
        rank_cb: Callable[[ResearchTask, list[dict[str, Any]]], list[dict[str, Any]]],
        build_documents_cb: Callable[[ResearchTask, list[dict[str, Any]], int], tuple[list[dict[str, Any]], list[dict[str, Any]]]],
        build_passages_cb: Callable[[ResearchTask, list[dict[str, Any]]], list[dict[str, Any]]],
        synthesize_cb: Callable[[ResearchTask, str, list[dict[str, Any]], list[dict[str, Any]], str], dict[str, Any]],
        claim_builder_cb: Callable[[str, list[str], list[dict[str, Any]], list[dict[str, Any]]], list[dict[str, Any]]],
    ):
        self.llm = llm
        self.config = config or {}
        self.query_planner = query_planner
        self.search_cb = search_cb
        self.rank_cb = rank_cb
        self.build_documents_cb = build_documents_cb
        self.build_passages_cb = build_passages_cb
        self.synthesize_cb = synthesize_cb
        self.claim_builder_cb = claim_builder_cb

    def run(
        self,
        task: ResearchTask,
        *,
        topic: str,
        existing_summary: str,
        max_results_per_query: int,
    ) -> dict[str, Any]:
        state = BranchResearchState(
            task_id=task.id,
            section_id=task.section_id,
            branch_id=task.branch_id,
            topic=topic,
            objective=task.objective or task.goal or task.query,
            acceptance_criteria=list(task.acceptance_criteria or []),
            existing_summary=existing_summary,
            source_preferences=list(task.source_preferences or []),
            language_hints=list(task.language_hints or []),
            coverage_targets=list(task.coverage_targets or []),
            freshness_policy=str(task.freshness_policy or "").strip(),
            authority_preferences=list(task.authority_preferences or []),
            max_rounds=max(1, int((self.config.get("configurable") or {}).get("deep_research_branch_max_rounds") or 3)),
            max_results_per_query=max_results_per_query,
            max_follow_up_queries_per_round=max(
                1,
                int((self.config.get("configurable") or {}).get("deep_research_follow_up_queries_per_round") or 2),
            ),
        )

        query_plan = self.query_planner.build_initial_queries(
            task,
            topic=topic,
            max_queries=max(2, min(4, max_results_per_query)),
        )
        current_queries = list(query_plan.queries or [task.query])
        previous_source_urls: set[str] = set()
        ranked_results: list[dict[str, Any]] = []
        latest_sources: list[dict[str, Any]] = []

        latest_coverage = BranchCoverageSummary()
        latest_quality = BranchQualitySummary()
        latest_contradiction = BranchContradictionSummary()
        latest_grounding: BranchGroundingSummary | None = None

        while state.round_index < state.max_rounds:
            state.round_index += 1
            round_queries = [query for query in dedupe_strings(current_queries, limit=6) if query.lower() not in {item.lower() for item in state.executed_queries}]
            if not round_queries:
                state.stop_reason = "no_follow_up_queries"
                break

            state.executed_queries.extend(round_queries)
            fresh_results = self.search_cb(round_queries, max_results_per_query=max_results_per_query)
            state.search_results.extend(copy.deepcopy(fresh_results))
            ranked_results = self.rank_cb(task, state.search_results)
            documents, sources = self.build_documents_cb(
                task,
                ranked_results,
                fetch_limit=max(2, min(max_results_per_query + state.round_index - 1, 6)),
            )
            latest_sources = copy.deepcopy(sources)
            state.documents = documents
            state.passages = self.build_passages_cb(task, documents)

            latest_coverage = assess.evaluate_coverage(task, state.passages, state.documents)
            latest_quality = assess.evaluate_quality(task, sources, state.passages, latest_coverage)
            latest_contradiction = assess.evaluate_contradictions(sources, latest_quality)
            current_source_keys = {
                str(item.get("source_key") or "").strip() or canonical_url(str(item.get("url") or "").strip())
                for item in sources
                if str(item.get("source_key") or "").strip() or canonical_url(str(item.get("url") or "").strip())
            }
            new_source_urls = current_source_keys - previous_source_urls
            previous_source_urls = current_source_keys

            state.query_rounds.append(
                BranchQueryRoundArtifact(
                    id=_new_id("branch_round"),
                    task_id=task.id,
                    section_id=task.section_id,
                    branch_id=task.branch_id,
                    round_index=state.round_index,
                    queries=round_queries,
                    search_result_count=len(fresh_results),
                    source_count=len(sources),
                    document_count=len(documents),
                    passage_count=len(state.passages),
                    new_source_count=len(new_source_urls),
                    coverage_ready=latest_coverage.coverage_ready,
                    notes=query_plan.reasoning,
                ).to_dict()
            )

            query_plan = self.query_planner.refine_queries(
                task,
                topic=topic,
                executed_queries=state.executed_queries,
                missing_topics=latest_coverage.missing_topics,
                quality_summary=latest_quality,
                contradiction_summary=latest_contradiction,
                max_queries=state.max_follow_up_queries_per_round,
            )

            decision = assess.decide_next_action(
                coverage_summary=latest_coverage,
                quality_summary=latest_quality,
                contradiction_summary=latest_contradiction,
                grounding_summary=latest_grounding,
                round_index=state.round_index,
                max_rounds=state.max_rounds,
                new_source_count=len(new_source_urls),
                follow_up_queries=list(query_plan.queries or []),
            )
            state.research_decisions.append(
                BranchDecisionArtifact(
                    id=_new_id("branch_decision"),
                    task_id=task.id,
                    section_id=task.section_id,
                    branch_id=task.branch_id,
                    round_index=state.round_index,
                    action=decision.action,
                    reason=decision.reason,
                    follow_up_queries=list(decision.follow_up_queries or []),
                    stop_reason=decision.stop_reason,
                    notes=decision.notes,
                ).to_dict()
            )

            state.coverage_summary = latest_coverage.to_dict()
            state.quality_summary = latest_quality.to_dict()
            state.contradiction_summary = latest_contradiction.to_dict()
            state.open_gaps = list(latest_coverage.missing_topics)
            if decision.action in {"synthesize", "bounded_stop"}:
                state.stop_reason = decision.stop_reason
                break
            current_queries = list(decision.follow_up_queries or query_plan.queries)

        synthesis = self.synthesize_cb(
            task,
            topic=topic,
            passages=state.passages,
            documents=state.documents,
            existing_summary=existing_summary,
        )
        limitations = dedupe_strings(
            [
                *list(state.open_gaps or []),
                *(latest_quality.gaps or []),
                *(latest_contradiction.conflict_notes or []),
            ],
            limit=5,
        )
        claim_units = self.claim_builder_cb(
            synthesis.get("summary", ""),
            list(synthesis.get("key_findings") or []),
            state.passages,
            latest_sources,
        )
        latest_grounding = assess.evaluate_grounding(claim_units)
        state.grounding_summary = latest_grounding.to_dict()

        return {
            "queries": list(state.executed_queries),
            "search_results": copy.deepcopy(ranked_results),
            "sources": copy.deepcopy(latest_sources),
            "documents": copy.deepcopy(state.documents),
            "passages": copy.deepcopy(state.passages),
            "summary": synthesis.get("summary", ""),
            "key_findings": list(synthesis.get("key_findings") or []),
            "open_questions": list(synthesis.get("open_questions") or []),
            "confidence_note": synthesis.get("confidence_note", ""),
            "claim_units": claim_units,
            "coverage_summary": latest_coverage.to_dict(),
            "quality_summary": latest_quality.to_dict(),
            "contradiction_summary": latest_contradiction.to_dict(),
            "grounding_summary": latest_grounding.to_dict(),
            "research_decisions": copy.deepcopy(state.research_decisions),
            "limitations": limitations,
            "stop_reason": state.stop_reason,
            "branch_artifacts": {
                "query_rounds": copy.deepcopy(state.query_rounds),
                **build_branch_artifacts(
                    task,
                    coverage=latest_coverage,
                    quality=latest_quality,
                    contradiction=latest_contradiction,
                    grounding=latest_grounding,
                    decisions=copy.deepcopy(state.research_decisions),
                ),
            },
        }
