"""
Evidence-first Research Agent for Deep Research branches.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel

from agent.deep_research.branch_research import BranchResearchRunner, research_pipeline
from agent.deep_research.branch_research import claims as branch_claims
from agent.deep_research.branch_research import synthesis as branch_synthesis
from agent.deep_research.branch_research.planner import BranchQueryPlanner
from agent.deep_research.branch_research.shared import (
    dedupe_strings as _shared_dedupe_strings,
)
from agent.deep_research.schema import ResearchTask
from tools.rag import KnowledgeSearchScope, get_knowledge_service
from tools.research.content_fetcher import ContentFetcher

logger = logging.getLogger(__name__)


def _dedupe_strings(values: list[Any], *, limit: int = 0) -> list[str]:
    return _shared_dedupe_strings(values, limit=limit)


@dataclass
class BranchResearchOutcome:
    queries: list[str]
    search_results: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    passages: list[dict[str, Any]]
    summary: str
    key_findings: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    confidence_note: str = ""
    claim_units: list[dict[str, Any]] = field(default_factory=list)
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    quality_summary: dict[str, Any] = field(default_factory=dict)
    contradiction_summary: dict[str, Any] = field(default_factory=dict)
    grounding_summary: dict[str, Any] = field(default_factory=dict)
    research_decisions: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    stop_reason: str = ""
    branch_artifacts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchAgent:
    """
    Branch-scoped researcher that builds an evidence set before synthesizing.

    Flow:
    1. Search queries
    2. Rank and select candidate URLs
    3. Fetch full pages when possible
    4. Extract passages
    5. Synthesize a branch result from authoritative evidence
    """

    def __init__(
        self,
        llm: BaseChatModel,
        search_func: Callable,
        config: dict[str, Any] | None = None,
        *,
        fetcher: ContentFetcher | None = None,
        knowledge_service: Any | None = None,
    ):
        self.llm = llm
        self.search_func = search_func
        self.config = config or {}
        self.fetcher = fetcher or ContentFetcher()
        self.knowledge_service = knowledge_service or get_knowledge_service()
        self.query_planner = BranchQueryPlanner(llm, self.config)

    def research_branch(
        self,
        task: ResearchTask | dict[str, Any],
        *,
        topic: str,
        existing_summary: str = "",
        max_results_per_query: int = 5,
    ) -> dict[str, Any]:
        normalized_task = task if isinstance(task, ResearchTask) else ResearchTask(**task)
        outcome = BranchResearchOutcome(
            **BranchResearchRunner(
                llm=self.llm,
                config=self.config,
                query_planner=self.query_planner,
                search_cb=self._search,
                rank_cb=self._rank_search_results,
                build_documents_cb=lambda branch_task, ranked_results, fetch_limit: self._build_documents_and_sources(
                    branch_task,
                    ranked_results,
                    fetch_limit=fetch_limit,
                ),
                build_passages_cb=self._build_passages,
                synthesize_cb=lambda branch_task, *, topic, passages, documents, existing_summary: self._synthesize(
                    branch_task,
                    topic=topic,
                    passages=passages,
                    documents=documents,
                    existing_summary=existing_summary,
                ),
                claim_builder_cb=lambda summary, key_findings, passages, sources: self._build_claim_units(
                    summary=summary,
                    key_findings=key_findings,
                    passages=passages,
                    sources=sources,
                ),
            ).run(
                normalized_task,
                topic=topic,
                existing_summary=existing_summary,
                max_results_per_query=max_results_per_query,
            )
        )
        return outcome.to_dict()

    def _search(self, queries: list[str], *, max_results_per_query: int) -> list[dict[str, Any]]:
        web_results = research_pipeline.search_queries(
            self.search_func,
            self.config,
            queries,
            max_results_per_query=max_results_per_query,
        )
        rag_results: list[dict[str, Any]] = []
        configurable = self.config.get("configurable") if isinstance(self.config, dict) else {}
        if not isinstance(configurable, dict):
            configurable = {}
        user_id = str(configurable.get("user_id") or "").strip()
        agent_profile = configurable.get("agent_profile") or {}
        if not isinstance(agent_profile, dict):
            agent_profile = {}
        agent_id = str(agent_profile.get("id") or configurable.get("agent_id") or "").strip()
        scope = KnowledgeSearchScope(user_id=user_id, agent_id=agent_id) if user_id else None
        try:
            for query in queries:
                try:
                    results = self.knowledge_service.search(
                        query=query,
                        limit=max_results_per_query,
                        scope=scope,
                    )
                except TypeError:
                    results = self.knowledge_service.search(
                        query=query,
                        limit=max_results_per_query,
                    )
                rag_results.extend(results)
        except Exception as exc:
            logger.warning("[deep-research-researcher] rag search failed: %s", exc)
        return [*web_results, *rag_results]

    def _rank_search_results(
        self,
        task: ResearchTask,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return research_pipeline.rank_search_results(task, results)

    def _build_documents_and_sources(
        self,
        task: ResearchTask,
        ranked_results: list[dict[str, Any]],
        *,
        fetch_limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return research_pipeline.build_documents_and_sources(
            task,
            ranked_results,
            fetcher=self.fetcher,
            fetch_limit=fetch_limit,
        )

    def _select_fetch_targets(self, ranked_results: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        return research_pipeline.select_fetch_targets(ranked_results, limit=limit)

    def _document_from_page(
        self,
        task: ResearchTask,
        result: dict[str, Any],
        page: Any,
    ) -> dict[str, Any]:
        return research_pipeline.document_from_page(task, result, page)

    def _document_from_search_snippet(
        self,
        task: ResearchTask,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return research_pipeline.document_from_search_snippet(task, result)

    def _build_passages(
        self,
        task: ResearchTask,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return research_pipeline.build_passages(task, documents)

    def _synthesize(
        self,
        task: ResearchTask,
        *,
        topic: str,
        passages: list[dict[str, Any]],
        documents: list[dict[str, Any]],
        existing_summary: str,
    ) -> dict[str, Any]:
        return branch_synthesis.synthesize(
            self.llm,
            self.config,
            task,
            topic=topic,
            passages=passages,
            documents=documents,
            existing_summary=existing_summary,
        )

    def _parse_synthesis(self, content: str) -> dict[str, Any]:
        return branch_synthesis.parse_synthesis_payload(content)

    def _fallback_summary(
        self,
        task: ResearchTask,
        passages: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> str:
        return branch_synthesis.fallback_summary(task, passages, documents)

    def _fallback_findings(
        self,
        passages: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> list[str]:
        return branch_synthesis.fallback_findings(passages, documents)

    def _build_claim_units(
        self,
        *,
        summary: str,
        key_findings: list[str],
        passages: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return branch_claims.build_claim_units(
            self.llm,
            self.config,
            summary=summary,
            key_findings=key_findings,
            passages=passages,
            sources=sources,
        )

    def _build_claim_units_with_llm(
        self,
        *,
        summary: str,
        key_findings: list[str],
        passages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return branch_claims._build_claim_units_with_llm(
            self.llm,
            self.config,
            summary=summary,
            key_findings=key_findings,
            passages=passages,
        )

    def _finalize_claim_units(
        self,
        grounded_claims: list[dict[str, Any]],
        passages: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return branch_claims._finalize_claim_units(grounded_claims, passages, sources)
