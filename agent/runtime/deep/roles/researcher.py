"""
Evidence-first Research Agent for Deep Research branches.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agent.prompts.runtime_templates import (
    DEEP_RESEARCHER_CLAIM_GROUNDING_PROMPT,
    DEEP_RESEARCHER_EVIDENCE_SYNTHESIS_PROMPT,
)
from agent.research.evidence_passages import split_into_passages
from agent.runtime.deep.researcher_runtime import BranchResearchRunner
from agent.runtime.deep.researcher_runtime.planner import BranchQueryPlanner
from agent.runtime.deep.researcher_runtime.shared import (
    canonical_url as _shared_canonical_url,
)
from agent.runtime.deep.researcher_runtime.shared import (
    clamp_text as _shared_clamp_text,
)
from agent.runtime.deep.researcher_runtime.shared import (
    dedupe_strings as _shared_dedupe_strings,
)
from agent.runtime.deep.researcher_runtime.shared import (
    source_domain as _shared_source_domain,
)
from agent.runtime.deep.researcher_runtime.shared import (
    task_texts as _shared_task_texts,
)
from agent.runtime.deep.researcher_runtime.shared import (
    tokenize as _shared_tokenize,
)
from agent.runtime.deep.schema import ClaimUnit, ResearchTask
from tools.research.content_fetcher import ContentFetcher

logger = logging.getLogger(__name__)


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


def _task_texts(task: ResearchTask) -> list[str]:
    return _shared_task_texts(task)


def _tokenize(text: str) -> set[str]:
    return _shared_tokenize(text)


def _canonical_url(url: str) -> str:
    return _shared_canonical_url(url)


def _source_domain(url: str) -> str:
    return _shared_source_domain(url)


def _clamp_text(text: str, limit: int) -> str:
    return _shared_clamp_text(text, limit)


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
    ):
        self.llm = llm
        self.search_func = search_func
        self.config = config or {}
        self.fetcher = fetcher or ContentFetcher()
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
        all_results: list[dict[str, Any]] = []
        for query in queries:
            try:
                results = self.search_func(
                    {"query": query, "max_results": max_results_per_query},
                    config=self.config,
                )
            except Exception as exc:
                logger.warning("[deep-research-researcher] query failed %s: %s", query, exc)
                continue
            for item in results or []:
                if not isinstance(item, dict):
                    continue
                normalized = {
                    "query": query,
                    "title": str(item.get("title") or "").strip(),
                    "url": str(item.get("url") or "").strip(),
                    "summary": str(item.get("summary") or item.get("snippet") or "").strip(),
                    "raw_excerpt": str(item.get("raw_excerpt") or item.get("content") or "").strip(),
                    "score": float(item.get("score", 0.0) or 0.0),
                    "provider": str(item.get("provider") or "").strip(),
                    "published_date": item.get("published_date"),
                }
                if normalized["url"]:
                    all_results.append(normalized)
        return all_results

    def _rank_search_results(
        self,
        task: ResearchTask,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        task_tokens = _tokenize("\n".join(_task_texts(task)))
        preferred_sources = [
            str(item).strip().lower()
            for item in [*(task.source_preferences or []), *(task.authority_preferences or [])]
            if str(item).strip()
        ]
        deduped: dict[str, dict[str, Any]] = {}
        for item in results:
            url = _canonical_url(item.get("url") or "")
            if not url:
                continue
            text = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("summary") or ""),
                    str(item.get("raw_excerpt") or "")[:400],
                ]
            )
            overlap = len(task_tokens & _tokenize(text))
            lowered_url = url.lower()
            authority_bonus = 0.0
            if any(preference in lowered_url for preference in preferred_sources):
                authority_bonus += 0.25
            if lowered_url.startswith("https://") and any(marker in lowered_url for marker in (".gov", ".edu", ".org")):
                authority_bonus += 0.1
            freshness_bonus = 0.1 if str(item.get("published_date") or "").strip() else 0.0
            rank_score = float(item.get("score", 0.0) or 0.0) + (overlap * 0.15) + authority_bonus + freshness_bonus
            candidate = {
                **item,
                "url": url,
                "rank_score": round(rank_score, 4),
                "overlap_tokens": overlap,
            }
            previous = deduped.get(url)
            if previous is None or candidate["rank_score"] > float(previous.get("rank_score", 0.0)):
                deduped[url] = candidate
        ranked = sorted(
            deduped.values(),
            key=lambda item: (
                -float(item.get("rank_score", 0.0) or 0.0),
                -float(item.get("score", 0.0) or 0.0),
                str(item.get("title") or ""),
            ),
        )
        return ranked

    def _build_documents_and_sources(
        self,
        task: ResearchTask,
        ranked_results: list[dict[str, Any]],
        *,
        fetch_limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        selected_results = self._select_fetch_targets(ranked_results, limit=fetch_limit)
        selected_urls = [str(item.get("url") or "").strip() for item in selected_results if item.get("url")]
        fetched_pages = {
            _canonical_url(page.url): page
            for page in self.fetcher.fetch_many(selected_urls)
            if getattr(page, "url", None)
        }

        documents: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []

        for result in selected_results:
            url = str(result.get("url") or "").strip()
            if not url:
                continue
            fetched = fetched_pages.get(_canonical_url(url))
            if fetched and (str(fetched.markdown or fetched.text or "").strip()):
                document = self._document_from_page(task, result, fetched)
            else:
                document = self._document_from_search_snippet(task, result)
            documents.append(document)
            sources.append(
                {
                    "title": document.get("title") or url,
                    "url": url,
                    "provider": result.get("provider", ""),
                    "published_date": document.get("published_date") or result.get("published_date"),
                    "method": document.get("method"),
                    "authoritative": bool(document.get("authoritative", False)),
                    "rank_score": float(result.get("rank_score", 0.0) or 0.0),
                }
            )

        return documents, sources

    def _select_fetch_targets(self, ranked_results: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        selected: list[dict[str, Any]] = []
        seen_domains: set[str] = set()
        deferred: list[dict[str, Any]] = []

        for item in ranked_results:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            domain = _source_domain(url)
            if domain and domain not in seen_domains:
                selected.append(item)
                seen_domains.add(domain)
            else:
                deferred.append(item)
            if len(selected) >= limit:
                return selected[:limit]

        for item in deferred:
            selected.append(item)
            if len(selected) >= limit:
                break
        return selected[:limit]

    def _document_from_page(
        self,
        task: ResearchTask,
        result: dict[str, Any],
        page: Any,
    ) -> dict[str, Any]:
        content = str(getattr(page, "markdown", None) or getattr(page, "text", None) or "").strip()
        page_url = str(getattr(page, "url", "") or result.get("url") or "").strip()
        title = str(getattr(page, "title", None) or result.get("title") or page_url).strip()
        raw_url = str(getattr(page, "raw_url", None) or result.get("url") or page_url).strip()
        digest = hashlib.sha1(f"{task.id}:{page_url}".encode()).hexdigest()[:12]
        excerpt = _clamp_text(str(getattr(page, "text", None) or content), 320)
        return {
            "id": f"document_{digest}",
            "url": page_url,
            "raw_url": raw_url,
            "title": title,
            "excerpt": excerpt,
            "content": _clamp_text(content, 8_000),
            "method": str(getattr(page, "method", None) or "direct_http"),
            "published_date": getattr(page, "published_date", None) or result.get("published_date"),
            "retrieved_at": getattr(page, "retrieved_at", None),
            "http_status": getattr(page, "http_status", None),
            "attempts": getattr(page, "attempts", None),
            "provider": result.get("provider", ""),
            "authoritative": True,
            "admissible": True,
        }

    def _document_from_search_snippet(
        self,
        task: ResearchTask,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        url = str(result.get("url") or "").strip()
        content = str(result.get("raw_excerpt") or result.get("summary") or "").strip()
        digest = hashlib.sha1(f"{task.id}:{url}:snippet".encode()).hexdigest()[:12]
        return {
            "id": f"document_{digest}",
            "url": url,
            "raw_url": url,
            "title": str(result.get("title") or url).strip(),
            "excerpt": _clamp_text(content, 320),
            "content": _clamp_text(content, 1_600),
            "method": "search_result",
            "published_date": result.get("published_date"),
            "retrieved_at": None,
            "http_status": None,
            "attempts": 1,
            "provider": result.get("provider", ""),
            "authoritative": False,
            "admissible": False,
        }

    def _build_passages(
        self,
        task: ResearchTask,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        task_tokens = _tokenize("\n".join(_task_texts(task)))
        ranked_passages: list[tuple[float, dict[str, Any]]] = []

        for document in documents:
            content = str(document.get("content") or "").strip()
            if not content:
                continue
            authoritative = bool(document.get("authoritative", False))
            base_passages = (
                split_into_passages(content, max_chars=900)
                if authoritative
                else [{"text": content, "start_char": 0, "end_char": len(content)}]
            )
            local_ranked: list[tuple[float, dict[str, Any]]] = []
            for item in base_passages:
                text = str(item.get("text") or "").strip()
                if len(text) < 40:
                    continue
                overlap = len(task_tokens & _tokenize(text))
                if authoritative and overlap == 0 and len(base_passages) > 1:
                    continue
                score = float(document.get("authoritative", False)) * 0.5 + overlap
                snippet_hash = hashlib.sha1(
                    f"{document['id']}:{item.get('start_char', 0)}:{item.get('end_char', 0)}".encode()
                ).hexdigest()[:16]
                passage = {
                    "id": f"passage_{snippet_hash}",
                    "document_id": document["id"],
                    "url": document["url"],
                    "text": text,
                    "quote": _clamp_text(text, 260),
                    "source_title": document.get("title", ""),
                    "snippet_hash": snippet_hash,
                    "heading": item.get("heading"),
                    "heading_path": list(item.get("heading_path") or []),
                    "page_title": document.get("title"),
                    "start_char": item.get("start_char"),
                    "end_char": item.get("end_char"),
                    "retrieved_at": document.get("retrieved_at"),
                    "method": document.get("method"),
                    "locator": {},
                    "source_published_date": document.get("published_date"),
                    "passage_kind": "quote" if authoritative else "search_snippet",
                    "admissible": bool(document.get("admissible", authoritative)),
                    "authoritative": authoritative,
                }
                local_ranked.append((score, passage))

            local_ranked.sort(key=lambda row: (-row[0], str(row[1].get("source_title") or "")))
            for score, passage in local_ranked[:2]:
                ranked_passages.append((score, passage))

        ranked_passages.sort(
            key=lambda row: (
                -row[0],
                not bool(row[1].get("authoritative", False)),
                str(row[1].get("source_title") or ""),
            )
        )
        return [item for _score, item in ranked_passages[:8]]

    def _synthesize(
        self,
        task: ResearchTask,
        *,
        topic: str,
        passages: list[dict[str, Any]],
        documents: list[dict[str, Any]],
        existing_summary: str,
    ) -> dict[str, Any]:
        evidence_lines: list[str] = []
        for index, item in enumerate(passages[:8], 1):
            title = str(item.get("source_title") or item.get("page_title") or item.get("url") or "").strip()
            evidence_lines.append(
                "\n".join(
                    [
                        f"[{index}] 标题: {title}",
                        f"URL: {item.get('url', '')}",
                        f"Heading: {' > '.join(item.get('heading_path') or []) or 'N/A'}",
                        f"Authoritative: {bool(item.get('authoritative', False))}",
                        f"Quote: {_clamp_text(item.get('quote') or item.get('text') or '', 280)}",
                    ]
                )
            )

        if not evidence_lines:
            for index, item in enumerate(documents[:4], 1):
                evidence_lines.append(
                    "\n".join(
                        [
                            f"[{index}] 标题: {item.get('title', '')}",
                            f"URL: {item.get('url', '')}",
                            f"Authoritative: {bool(item.get('authoritative', False))}",
                            f"Excerpt: {_clamp_text(item.get('excerpt') or item.get('content') or '', 280)}",
                        ]
                    )
                )

        prompt = ChatPromptTemplate.from_messages([("user", DEEP_RESEARCHER_EVIDENCE_SYNTHESIS_PROMPT)])
        messages = prompt.format_messages(
            topic=topic,
            branch_title=task.title or task.objective or task.goal,
            branch_objective=task.objective or task.goal or task.query,
            acceptance_criteria="\n".join(f"- {item}" for item in task.acceptance_criteria) or "- 无显式验收标准",
            existing_summary=_clamp_text(existing_summary, 1_200) or "暂无",
            evidence="\n\n".join(evidence_lines),
        )
        response = self.llm.invoke(messages, config=self.config)
        payload = self._parse_synthesis(getattr(response, "content", "") or "")

        summary = str(payload.get("summary") or "").strip()
        key_findings = _dedupe_strings(payload.get("key_findings") or [], limit=5)
        open_questions = _dedupe_strings(payload.get("open_questions") or [], limit=3)
        confidence_note = str(payload.get("confidence_note") or "").strip()

        if not summary:
            summary = self._fallback_summary(task, passages, documents)
        if not key_findings:
            key_findings = self._fallback_findings(passages, documents)

        return {
            "summary": summary,
            "key_findings": key_findings,
            "open_questions": open_questions,
            "confidence_note": confidence_note,
        }

    def _parse_synthesis(self, content: str) -> dict[str, Any]:
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
            logger.warning("[deep-research-researcher] failed to parse synthesis payload")
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _fallback_summary(
        self,
        task: ResearchTask,
        passages: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> str:
        if passages:
            top = passages[0]
            return (
                f"{task.objective or task.goal}: 基于 {top.get('source_title') or top.get('url')} 的证据, "
                f"{_clamp_text(top.get('quote') or top.get('text') or '', 160)}"
            )
        if documents:
            top = documents[0]
            return (
                f"{task.objective or task.goal}: 已收集到 {top.get('title') or top.get('url')} 的相关材料, "
                f"但结构化综合结果生成失败。"
            )
        return f"{task.objective or task.goal}: 未形成有效证据摘要。"

    def _fallback_findings(
        self,
        passages: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> list[str]:
        findings: list[str] = []
        for item in passages[:3]:
            text = _clamp_text(item.get("quote") or item.get("text") or "", 120)
            if text:
                findings.append(text)
        if findings:
            return _dedupe_strings(findings, limit=3)
        for item in documents[:2]:
            text = _clamp_text(item.get("excerpt") or item.get("content") or "", 120)
            if text:
                findings.append(text)
        return _dedupe_strings(findings, limit=3)

    def _build_claim_units(
        self,
        *,
        summary: str,
        key_findings: list[str],
        passages: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        grounded_claims = self._build_claim_units_with_llm(
            summary=summary,
            key_findings=key_findings,
            passages=passages,
        )
        if grounded_claims:
            finalized = self._finalize_claim_units(grounded_claims, passages, sources)
            if finalized:
                return finalized

        claims: list[tuple[str, str]] = []
        summary_text = str(summary or "").strip()
        if summary_text:
            claims.append((summary_text, "primary"))
        for index, finding in enumerate(_dedupe_strings(key_findings or [], limit=4), 1):
            importance = "primary" if index <= 2 else "secondary"
            claims.append((finding, importance))

        source_urls = [
            str(item.get("url") or "").strip()
            for item in sources or []
            if str(item.get("url") or "").strip()
        ]
        built: list[dict[str, Any]] = []
        for index, (claim_text, importance) in enumerate(claims, 1):
            claim_tokens = _tokenize(claim_text)
            matched_passages: list[dict[str, Any]] = []
            for passage in passages or []:
                passage_text = str(passage.get("text") or passage.get("quote") or "").strip()
                if not passage_text:
                    continue
                overlap = len(claim_tokens & _tokenize(passage_text))
                if overlap <= 0:
                    continue
                matched_passages.append(
                    {
                        "overlap": overlap,
                        "id": str(passage.get("id") or "").strip(),
                        "url": str(passage.get("url") or "").strip(),
                    }
                )
            matched_passages.sort(key=lambda item: (-int(item["overlap"]), item["id"]))
            evidence_passage_ids = [
                str(item["id"]).strip()
                for item in matched_passages[:2]
                if str(item["id"]).strip()
            ]
            evidence_urls = list(
                dict.fromkeys(
                    [
                        str(item["url"]).strip()
                        for item in matched_passages[:2]
                        if str(item["url"]).strip()
                    ]
                    or source_urls[:1]
                )
            )
            built.append(
                ClaimUnit(
                    id=f"claim_{index}",
                    text=claim_text,
                    importance=importance,
                    evidence_passage_ids=evidence_passage_ids,
                    evidence_urls=evidence_urls,
                    grounded=bool(evidence_passage_ids),
                ).to_dict()
            )
        return built

    def _build_claim_units_with_llm(
        self,
        *,
        summary: str,
        key_findings: list[str],
        passages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not passages:
            return []

        claims: list[dict[str, Any]] = []
        summary_text = str(summary or "").strip()
        if summary_text:
            claims.append({"text": summary_text, "importance": "primary"})
        for index, finding in enumerate(_dedupe_strings(key_findings or [], limit=4), 1):
            claims.append({"text": finding, "importance": "primary" if index <= 2 else "secondary"})
        if not claims:
            return []

        passage_lines: list[dict[str, Any]] = []
        for item in passages[:8]:
            passage_id = str(item.get("id") or "").strip()
            if not passage_id:
                continue
            passage_lines.append(
                {
                    "id": passage_id,
                    "url": str(item.get("url") or "").strip(),
                    "source_title": str(item.get("source_title") or item.get("page_title") or "").strip(),
                    "quote": _clamp_text(item.get("quote") or item.get("text") or "", 200),
                }
            )
        if not passage_lines:
            return []

        prompt = ChatPromptTemplate.from_messages([("user", DEEP_RESEARCHER_CLAIM_GROUNDING_PROMPT)])
        messages = prompt.format_messages(
            claims=json.dumps(claims, ensure_ascii=False, indent=2),
            passages=json.dumps(passage_lines, ensure_ascii=False, indent=2),
        )
        try:
            response = self.llm.invoke(messages, config=self.config)
        except Exception as exc:
            logger.debug("[deep-research-researcher] claim grounding prompt failed: %s", exc)
            return []
        payload = self._parse_synthesis(getattr(response, "content", "") or "")
        items = payload.get("claims")
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _finalize_claim_units(
        self,
        grounded_claims: list[dict[str, Any]],
        passages: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        passage_index = {
            str(item.get("id") or "").strip(): item
            for item in passages or []
            if str(item.get("id") or "").strip()
        }
        source_urls = [
            str(item.get("url") or "").strip()
            for item in sources or []
            if str(item.get("url") or "").strip()
        ]
        built: list[dict[str, Any]] = []
        for index, claim in enumerate(grounded_claims, 1):
            text = str(claim.get("text") or "").strip()
            if not text:
                continue
            evidence_passage_ids = [
                str(item).strip()
                for item in list(claim.get("evidence_passage_ids") or [])
                if str(item).strip() in passage_index
            ][:2]
            evidence_urls = list(
                dict.fromkeys(
                    [
                        str(passage_index[passage_id].get("url") or "").strip()
                        for passage_id in evidence_passage_ids
                        if str(passage_index[passage_id].get("url") or "").strip()
                    ] or source_urls[:1]
                )
            )
            built.append(
                ClaimUnit(
                    id=f"claim_{index}",
                    text=text,
                    importance=str(claim.get("importance") or "secondary").strip() or "secondary",
                    evidence_passage_ids=evidence_passage_ids,
                    evidence_urls=evidence_urls,
                    grounded=bool(evidence_passage_ids),
                ).to_dict()
            )
        return built
