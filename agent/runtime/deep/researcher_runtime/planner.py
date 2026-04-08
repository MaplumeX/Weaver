"""
Query planning helpers for branch-scoped researcher loops.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agent.prompts.runtime_templates import (
    DEEP_RESEARCHER_COUNTEREVIDENCE_PROMPT,
    DEEP_RESEARCHER_QUERY_REFINE_PROMPT,
)
from agent.runtime.deep.researcher_runtime.contracts import (
    BranchContradictionSummary,
    BranchQualitySummary,
    BranchQueryPlan,
)
from agent.runtime.deep.researcher_runtime.shared import dedupe_strings, is_time_sensitive_task
from agent.runtime.deep.schema import ResearchTask

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


class BranchQueryPlanner:
    def __init__(self, llm: BaseChatModel, config: dict[str, Any] | None = None):
        self.llm = llm
        self.config = config or {}

    def build_initial_queries(self, task: ResearchTask, *, topic: str, max_queries: int = 4) -> BranchQueryPlan:
        base_queries = dedupe_strings(
            [
                *(task.query_hints or []),
                task.query,
                f"{topic} {task.objective}".strip(),
            ],
            limit=max_queries,
        )
        suggestions: list[str] = []
        if task.source_preferences:
            suggestions.append(f"{task.objective or task.goal} {' '.join(task.source_preferences[:2])}".strip())
        if task.authority_preferences:
            suggestions.append(f"{task.objective or task.goal} {' '.join(task.authority_preferences[:2])}".strip())
        if is_time_sensitive_task(task):
            suggestions.append(f"{task.objective or task.goal} latest official update".strip())
        if len(task.acceptance_criteria or []) > 1:
            suggestions.append(f"{task.objective or task.goal} comparison data".strip())
        queries = dedupe_strings([*base_queries, *suggestions], limit=max_queries)
        return BranchQueryPlan(queries=queries or [task.query], reasoning="initial branch query set")

    def refine_queries(
        self,
        task: ResearchTask,
        *,
        topic: str,
        executed_queries: list[str],
        missing_topics: list[str],
        quality_summary: BranchQualitySummary,
        contradiction_summary: BranchContradictionSummary,
        max_queries: int = 2,
    ) -> BranchQueryPlan:
        llm_queries = self._llm_refine_queries(
            task,
            topic=topic,
            executed_queries=executed_queries,
            missing_topics=missing_topics,
            quality_summary=quality_summary,
            max_queries=max_queries,
        )
        fallback_queries = self._fallback_refine_queries(
            task,
            executed_queries=executed_queries,
            missing_topics=missing_topics,
            quality_summary=quality_summary,
            contradiction_summary=contradiction_summary,
            max_queries=max_queries,
        )
        counter_queries: list[str] = []
        if contradiction_summary.needs_counterevidence_query:
            counter_queries = self._llm_counterevidence_queries(
                task,
                topic=topic,
                max_queries=max_queries,
            )

        queries = dedupe_strings(
            [*llm_queries, *counter_queries, *fallback_queries],
            limit=max_queries,
        )
        return BranchQueryPlan(
            queries=queries,
            reasoning="refined follow-up queries" if queries else "no high-value follow-up queries",
        )

    def _llm_refine_queries(
        self,
        task: ResearchTask,
        *,
        topic: str,
        executed_queries: list[str],
        missing_topics: list[str],
        quality_summary: BranchQualitySummary,
        max_queries: int,
    ) -> list[str]:
        prompt = ChatPromptTemplate.from_messages([("user", DEEP_RESEARCHER_QUERY_REFINE_PROMPT)])
        messages = prompt.format_messages(
            topic=topic,
            branch_objective=task.objective or task.goal or task.query,
            acceptance_criteria="\n".join(f"- {item}" for item in task.acceptance_criteria) or "- 无",
            executed_queries="\n".join(f"- {item}" for item in executed_queries) or "- 无",
            missing_topics="\n".join(f"- {item}" for item in missing_topics) or "- 无显著缺口",
            quality_notes=quality_summary.notes or "; ".join(quality_summary.gaps) or "暂无",
            max_queries=max_queries,
        )
        return self._extract_queries(messages)

    def _llm_counterevidence_queries(
        self,
        task: ResearchTask,
        *,
        topic: str,
        max_queries: int,
    ) -> list[str]:
        prompt = ChatPromptTemplate.from_messages([("user", DEEP_RESEARCHER_COUNTEREVIDENCE_PROMPT)])
        messages = prompt.format_messages(
            topic=topic,
            branch_objective=task.objective or task.goal or task.query,
            key_findings="\n".join(f"- {item}" for item in (task.coverage_targets or task.acceptance_criteria[:2])) or "- 无",
            source_summary="\n".join(f"- {item}" for item in task.source_preferences[:3]) or "- 未指定",
        )
        return self._extract_queries(messages)[:max_queries]

    def _extract_queries(self, messages: list[Any]) -> list[str]:
        try:
            response = self.llm.invoke(messages, config=self.config)
        except Exception as exc:
            logger.debug("[deep-research-query-planner] llm query refinement failed: %s", exc)
            return []
        payload = self._extract_json_payload(getattr(response, "content", "") or "")
        queries = payload.get("queries") if isinstance(payload.get("queries"), list) else []
        return dedupe_strings(queries)

    def _extract_json_payload(self, content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            return {}
        match = _JSON_BLOCK_RE.search(text)
        if match:
            text = match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _fallback_refine_queries(
        self,
        task: ResearchTask,
        *,
        executed_queries: list[str],
        missing_topics: list[str],
        quality_summary: BranchQualitySummary,
        contradiction_summary: BranchContradictionSummary,
        max_queries: int,
    ) -> list[str]:
        candidates: list[str] = []
        objective = task.objective or task.goal or task.query
        if missing_topics:
            for item in missing_topics[:max_queries]:
                candidates.append(f"{objective} {item}".strip())
        if task.source_preferences:
            candidates.append(f"{objective} official {' '.join(task.source_preferences[:2])}".strip())
        if "freshness" in " ".join(quality_summary.gaps).lower() or is_time_sensitive_task(task):
            candidates.append(f"{objective} latest official data".strip())
        if contradiction_summary.needs_counterevidence_query:
            candidates.append(f"{objective} opposing view official source".strip())
        queries = [item for item in dedupe_strings(candidates, limit=max_queries * 2) if item.lower() not in {q.lower() for q in executed_queries}]
        return queries[:max_queries]
