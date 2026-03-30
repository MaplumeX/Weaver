"""
Optimized DeepSearch implementation with enhanced features.

Key improvements:
1. URL deduplication mechanism
2. Detailed performance logging
3. Enhanced error handling
4. Better cancellation support
5. OOP encapsulation (optional)
6. Tree-based exploration (new)
7. Multi-model support (new)

Based on: deep_search-dev reference implementation
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agent.contracts.search_cache import get_search_cache
from agent.core.llm_factory import create_chat_model
from agent.runtime.deep.legacy_events import (
    _build_quality_diagnostics,
    _compact_search_results,
    _emit_event,
    _event_results_limit,
    _provider_breakdown,
    _resolve_event_emitter,
    _safe_filename,
    _save_deepsearch_data,
)
from agent.runtime.deep.legacy_linear import run_deepsearch_optimized as _run_deepsearch_optimized
from agent.runtime.deep.legacy_support import (
    _auto_mode_prefers_linear,
    _browser_visualization_enabled,
    _budget_stop_reason,
    _cache_query_key,
    _check_cancel,
    _configurable_float,
    _configurable_int,
    _configurable_value,
    _estimate_tokens_from_results,
    _estimate_tokens_from_text,
    _model_for_task,
    _normalize_deepsearch_engine,
    _normalize_deepsearch_mode,
    _normalize_multi_search_results,
    _resolve_deepsearch_engine,
    _resolve_deepsearch_mode,
    _resolve_provider_profile,
    _resolve_search_strategy,
    _search_query,
    _selected_model,
    _selected_reasoning_model,
)
from agent.runtime.deep.legacy_tree import run_deepsearch_tree as _run_deepsearch_tree
from agent.workflows.domain_router import ResearchDomain, build_provider_profile
from agent.workflows.evidence_passages import split_into_passages
from agent.workflows.knowledge_gap import KnowledgeGapAnalyzer
from agent.workflows.parsing_utils import format_search_results, parse_list_output
from agent.workflows.query_strategy import (
    analyze_query_coverage,
    backfill_diverse_queries,
    is_time_sensitive_topic,
    summarize_freshness,
)
from agent.workflows.research_tree import TreeExplorationBudgetExceeded, TreeExplorer
from agent.workflows.source_url_utils import canonicalize_source_url, compact_unique_sources
from common.config import settings
from prompts.templates.deepsearch import (
    final_summary_prompt,
    formulate_query_prompt,
    related_url_prompt,
    summary_crawl_prompt,
    summary_text_prompt,
)
from tools.crawl.crawler import crawl_urls
from tools.research.content_fetcher import ContentFetcher
from tools.search.multi_search import multi_search
from tools.search.search import tavily_search

logger = logging.getLogger(__name__)

# Use shared implementations
_chat_model = create_chat_model
_parse_list_output = parse_list_output
_format_results = format_search_results
_LEGACY_RUNTIME_COMPAT_EXPORTS = (
    _auto_mode_prefers_linear,
    _browser_visualization_enabled,
    _build_quality_diagnostics,
    _budget_stop_reason,
    _cache_query_key,
    _check_cancel,
    _compact_search_results,
    _configurable_float,
    _configurable_int,
    _configurable_value,
    _emit_event,
    _estimate_tokens_from_results,
    _estimate_tokens_from_text,
    _event_results_limit,
    KnowledgeGapAnalyzer,
    ResearchDomain,
    _model_for_task,
    _normalize_deepsearch_engine,
    _normalize_deepsearch_mode,
    _normalize_multi_search_results,
    _provider_breakdown,
    _resolve_deepsearch_engine,
    _resolve_deepsearch_mode,
    _resolve_event_emitter,
    _resolve_provider_profile,
    _resolve_search_strategy,
    _safe_filename,
    _save_deepsearch_data,
    _search_query,
    _selected_model,
    _selected_reasoning_model,
    TreeExplorationBudgetExceeded,
    TreeExplorer,
    analyze_query_coverage,
    build_provider_profile,
    compact_unique_sources,
    get_search_cache,
    is_time_sensitive_topic,
    multi_search,
    summarize_freshness,
    tavily_search,
)

def _generate_queries(
    llm: ChatOpenAI,
    topic: str,
    have_query: List[str],
    summary_notes: List[str],
    query_num: int,
    config: Dict[str, Any],
    missing_topics: Optional[List[str]] = None,
) -> List[str]:
    """Generate new search queries based on topic, existing knowledge, and knowledge gaps.

    If missing_topics is provided (from gap analysis), prioritizes those areas.
    """
    # If we have missing topics from gap analysis, incorporate them
    enhanced_topic = topic
    if missing_topics:
        gap_hint = f"\n\n注意：以下方面信息仍然不足，请优先覆盖：{', '.join(missing_topics[:3])}"
        enhanced_topic = topic + gap_hint

    prompt = ChatPromptTemplate.from_messages([("user", formulate_query_prompt)])
    msg = prompt.format_messages(
        topic=enhanced_topic,
        have_query=", ".join(have_query) or "[]",
        summary_search="\n\n".join(summary_notes) or "暂无",
        query_num=query_num,
    )
    response = llm.invoke(msg, config=config)
    content = getattr(response, "content", "") or ""
    queries = _parse_list_output(content)
    # Deduplicate and trim
    seen = set(q.lower() for q in have_query)
    clean: List[str] = []
    for q in queries:
        if not q:
            continue
        q_norm = q.strip()
        if not q_norm or q_norm.lower() in seen:
            continue
        seen.add(q_norm.lower())
        clean.append(q_norm)
        if len(clean) >= query_num:
            break
    return backfill_diverse_queries(
        topic=topic,
        existing_queries=clean,
        historical_queries=have_query,
        query_num=query_num,
    )


def _pick_relevant_urls(
    llm: ChatOpenAI,
    topic: str,
    summary_notes: List[str],
    results: List[Dict[str, Any]],
    max_urls: int,
    config: Dict[str, Any],
    selected_urls_set: set,  # Use set for O(1) lookup
) -> List[str]:
    """Pick relevant URLs from search results, excluding already selected ones."""
    if not results:
        return []

    # Filter already selected URLs with O(1) set lookup
    available_results = []
    for r in results:
        if not isinstance(r, dict):
            continue
        canonical_url = canonicalize_source_url(r.get("url"))
        if not canonical_url or canonical_url in selected_urls_set:
            continue
        enriched = dict(r)
        enriched["_canonical_url"] = canonical_url
        available_results.append(enriched)

    if not available_results:
        logger.info("All URLs have been selected, no new URLs available")
        return []

    formatted = _format_results(available_results)
    prompt = ChatPromptTemplate.from_messages([("user", related_url_prompt)])
    msg = prompt.format_messages(
        topic=topic,
        summary_search="\n\n".join(summary_notes) or "暂无",
        text=formatted,
    )
    response = llm.invoke(msg, config=config)
    urls = _parse_list_output(getattr(response, "content", "") or "")

    # Fallback: top scores
    if not urls:
        sorted_results = sorted(available_results, key=lambda r: r.get("score", 0), reverse=True)
        urls = [r.get("_canonical_url") for r in sorted_results if r.get("_canonical_url")]

    # Clamp and dedupe
    deduped: List[str] = []
    seen = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        u = canonicalize_source_url(u)
        if not u or u in seen or u in selected_urls_set:
            continue
        seen.add(u)
        deduped.append(u)
        if len(deduped) >= max_urls:
            break
    return deduped


def _summarize_new_knowledge(
    llm: ChatOpenAI,
    topic: str,
    summary_notes: List[str],
    chosen_results: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Tuple[bool, str]:
    """Summarize new knowledge and judge if information is sufficient."""
    if not chosen_results:
        return False, ""

    prompt = ChatPromptTemplate.from_messages([("user", summary_crawl_prompt)])
    msg = prompt.format_messages(
        summary_search="\n\n".join(summary_notes) or "暂无",
        crawl_res=_format_results(chosen_results),
        topic=topic,
    )
    response = llm.invoke(msg, config=config)
    content = getattr(response, "content", "") or ""
    lowered = content.lower()
    enough = "回答" in lowered and "yes" in lowered.split("回答", 1)[-1]

    # Extract summary after "总结:" if present
    summary_text = ""
    if "总结" in content:
        summary_text = content.split("总结", 1)[-1].strip(":： \n")
    if not summary_text:
        summary_text = content
    return enough, summary_text.strip()


def _final_report(
    llm: ChatOpenAI,
    topic: str,
    summary_notes: List[str],
    config: Dict[str, Any],
    *,
    sources: str = "",
) -> str:
    """Generate final report based on all summaries."""
    prompt = ChatPromptTemplate.from_messages([("user", final_summary_prompt)])
    msg = prompt.format_messages(
        topic=topic,
        summary_search="\n\n".join(summary_notes) or "暂无",
        sources=sources or "暂无",
    )
    response = llm.invoke(msg, config=config)
    return getattr(response, "content", "") or summary_text_prompt


def _reorder_search_runs_for_citations(
    search_runs: List[Dict[str, Any]],
    *,
    preferred_urls: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Stable reorder to improve citation/source relevance.

    We keep the same content, but move "preferred" URLs (typically the selected URLs that were
    summarized) earlier so that `extract_message_sources()` assigns lower citation numbers to them.

    This improves:
    - report citation usefulness ([1]..[N] are more likely to be the actually-used sources)
    - frontend SourceInspector alignment (since sources are extracted from `scraped_content`)
    """
    if not search_runs:
        return []
    if not preferred_urls:
        return list(search_runs)

    try:
        from agent.contracts.source_registry import SourceRegistry

        registry = SourceRegistry()
        preferred_canonical: set[str] = set()
        for raw in preferred_urls:
            canon = registry.canonicalize_url(str(raw or ""))
            if canon:
                preferred_canonical.add(canon)
        if not preferred_canonical:
            return list(search_runs)

        preferred_runs: List[Dict[str, Any]] = []
        other_runs: List[Dict[str, Any]] = []

        for run in search_runs:
            if not isinstance(run, dict):
                continue

            results = run.get("results") or []
            if not isinstance(results, list):
                results = []

            preferred_results: List[Any] = []
            other_results: List[Any] = []
            for r in results:
                if not isinstance(r, dict):
                    other_results.append(r)
                    continue
                url = str(r.get("url") or "").strip()
                canon = registry.canonicalize_url(url) if url else ""
                if canon and canon in preferred_canonical:
                    preferred_results.append(r)
                else:
                    other_results.append(r)

            new_run = {**run, "results": preferred_results + other_results}
            if preferred_results:
                preferred_runs.append(new_run)
            else:
                other_runs.append(new_run)

        # Preserve determinism: stable partition only.
        return preferred_runs + other_runs
    except Exception:
        return list(search_runs)


def _format_sources_for_writer(
    sources: List[Dict[str, Any]],
    search_runs: List[Dict[str, Any]],
    *,
    limit: int,
) -> str:
    """
    Render sources into a compact, numbered block for the writer prompt.

    Numbering must match `extract_message_sources()` ordering so the frontend can
    display the same `[n]` mapping.
    """
    if not sources:
        return "暂无可引用来源。"

    max_count = max(1, int(limit or 0)) if limit else len(sources)
    rendered_sources = sources[:max_count]

    snippet_by_canonical: Dict[str, str] = {}
    try:
        from agent.contracts.source_registry import SourceRegistry

        registry = SourceRegistry()
        for run in search_runs or []:
            if not isinstance(run, dict):
                continue
            results = run.get("results") or []
            if not isinstance(results, list):
                continue
            for item in results:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                canon = registry.canonicalize_url(url) or url
                if canon in snippet_by_canonical:
                    continue

                raw_snippet = (
                    item.get("raw_excerpt")
                    or item.get("summary")
                    or item.get("snippet")
                    or item.get("content")
                    or ""
                )
                snippet = re.sub(r"\s+", " ", str(raw_snippet)).strip()
                if snippet:
                    snippet_by_canonical[canon] = snippet[:280]
    except Exception:
        snippet_by_canonical = {}

    lines: List[str] = []
    for idx, src in enumerate(rendered_sources, 1):
        if not isinstance(src, dict):
            continue
        title = str(src.get("title") or "").strip() or "Untitled"
        canonical_url = str(src.get("url") or "").strip()
        raw_url = str(src.get("rawUrl") or "").strip()
        href = raw_url or canonical_url

        domain = str(src.get("domain") or "").strip()
        provider = str(src.get("provider") or "").strip()
        published = str(src.get("publishedDate") or "").strip()
        meta_parts = [p for p in (domain, provider, published) if p and p.lower() != "none"]
        meta = " | ".join(meta_parts)

        snippet = ""
        if canonical_url:
            snippet = snippet_by_canonical.get(canonical_url, "")
        if not snippet and href:
            snippet = snippet_by_canonical.get(href, "")

        header = f"[{idx}] {title}"
        if meta:
            header = f"{header} ({meta})"
        lines.append(header)
        if href:
            lines.append(f"URL: {href}")
        if snippet:
            lines.append(f"摘要片段: {snippet}")
        lines.append("")  # blank line between sources

    return "\n".join(lines).strip() or "暂无可引用来源。"


def _append_auto_references(
    report: str,
    sources: List[Dict[str, Any]],
    *,
    limit: int,
) -> str:
    if not report:
        return report

    heading = "## 参考来源（自动生成）"
    if heading in report:
        return report

    max_count = max(1, int(limit or 0)) if limit else len(sources)
    rendered_sources = sources[:max_count]

    items: List[str] = []
    for idx, src in enumerate(rendered_sources, 1):
        if not isinstance(src, dict):
            continue
        title = str(src.get("title") or "").strip() or "Untitled"
        url = str(src.get("rawUrl") or src.get("url") or "").strip()
        if not url:
            continue
        items.append(f"- [{idx}] {title} — {url}")

    if not items:
        return report

    block = "\n".join([heading, "", *items]).rstrip()
    return report.rstrip() + "\n\n" + block + "\n"


def _hydrate_with_crawler(results: List[Dict[str, Any]]) -> None:
    """Enrich results in-place with crawled content when Tavily lacks body text."""
    if not settings.deepsearch_enable_crawler or not results:
        return

    # Pick URLs that need content
    targets = []
    for r in results:
        body = r.get("raw_excerpt") or r.get("summary") or ""
        if len(body) < 200 and r.get("url"):
            targets.append(r["url"])
    if not targets:
        return

    crawled = {item["url"]: item for item in crawl_urls(targets)}
    for r in results:
        url = r.get("url")
        if not url or url not in crawled:
            continue
        content = crawled[url].get("content") or ""
        if content:
            r["raw_excerpt"] = content[:1200]
            if not r.get("summary"):
                r["summary"] = content[:400]


def _build_fetcher_evidence(urls: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not bool(getattr(settings, "deepsearch_enable_research_fetcher", False)):
        return [], []

    def _looks_like_cookie_banner(text: str) -> bool:
        if not text:
            return False
        lowered = str(text).lower()
        if "cookie" not in lowered:
            return False
        return bool(
            "accept" in lowered
            or "consent" in lowered
            or "preferences" in lowered
            or "manage cookies" in lowered
            or "cookie settings" in lowered
            or "reject" in lowered
        )

    def _looks_like_interstitial(text: str) -> bool:
        if not text:
            return False
        lowered = str(text).lower()
        if "please enable javascript" in lowered:
            return True
        if "enable javascript" in lowered and ("cookies" in lowered or "continue" in lowered):
            return True
        if "checking your browser" in lowered:
            return True
        if "verify you are human" in lowered:
            return True
        if "just a moment" in lowered and "checking your browser" in lowered:
            return True
        return False

    def _passage_quality_score(passage: Dict[str, Any]) -> float:
        text = passage.get("text") or ""
        if not isinstance(text, str):
            text = str(text)
        stripped = text.strip()
        if not stripped:
            return -1e9
        if _looks_like_interstitial(stripped) or _looks_like_cookie_banner(stripped):
            return -1e9

        length = len(stripped)
        sentence_marks = sum(stripped.count(ch) for ch in (".", "?", "!", "。", "？", "！"))
        pipes = stripped.count("|")
        score = min(length, 800) / 800.0
        score += min(sentence_marks, 12) / 12.0
        if pipes >= 10:
            score -= 0.5
        return float(score)

    def _select_passages(passages: List[Dict[str, Any]], *, max_count: int) -> List[Dict[str, Any]]:
        if not passages:
            return []
        scored: List[tuple[float, Dict[str, Any]]] = [(_passage_quality_score(p), p) for p in passages]
        candidates = [(s, p) for s, p in scored if s > -1e8]
        if not candidates:
            return passages[:max(1, max_count)]
        candidates.sort(
            key=lambda pair: (
                -pair[0],
                int((pair[1].get("start_char") or 0) if isinstance(pair[1], dict) else 0),
            )
        )
        best = [p for _s, p in candidates[: max(1, max_count)]]
        best.sort(key=lambda p: int((p.get("start_char") or 0) if isinstance(p, dict) else 0))
        return best

    def _collapse_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _quote_for_passage(text: str, *, max_chars: int = 240) -> str:
        normalized = _collapse_whitespace(text)
        if not normalized:
            return ""
        return normalized[: max(1, int(max_chars))]

    def _snippet_hash_for_passage(text: str) -> str:
        normalized = _collapse_whitespace(text)
        if not normalized:
            return ""
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    fetcher = ContentFetcher()
    fetched_pages: List[Dict[str, Any]] = []
    passages: List[Dict[str, Any]] = []
    canonical_urls: List[str] = []
    seen: set = set()
    for url in urls or []:
        canonical_url = canonicalize_source_url(url)
        if not canonical_url or canonical_url in seen:
            continue
        seen.add(canonical_url)
        canonical_urls.append(canonical_url)

    for page in fetcher.fetch_many(canonical_urls):
        fetched_pages.append(page.to_dict())

        text = page.markdown or page.text or ""
        if not isinstance(text, str) or not text.strip():
            continue

        page_passages = split_into_passages(text, max_chars=800)
        for passage in _select_passages(page_passages, max_count=10):
            enriched = {"url": page.url, **passage}
            page_title = getattr(page, "title", None)
            if page_title:
                enriched["page_title"] = page_title
            retrieved_at = getattr(page, "retrieved_at", None)
            if retrieved_at:
                enriched["retrieved_at"] = retrieved_at
            method = getattr(page, "method", None)
            if method:
                enriched["method"] = method

            quote = _quote_for_passage(enriched.get("text") or "")
            if quote:
                enriched["quote"] = quote
            snippet_hash = _snippet_hash_for_passage(enriched.get("text") or "")
            if snippet_hash:
                enriched["snippet_hash"] = snippet_hash
            passages.append(enriched)

    return fetched_pages, passages


def run_deepsearch_optimized(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    return _run_deepsearch_optimized(state, config)


def run_deepsearch_tree(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    return _run_deepsearch_tree(state, config)


def run_deepsearch_auto(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auto-select between tree and linear deep search based on settings.

    Uses tree-based exploration if enabled in settings, otherwise falls back
    to the optimized linear approach.
    """
    from agent.runtime.deep.selector import run_deepsearch_auto as _run_deepsearch_auto

    return _run_deepsearch_auto(state, config)


def run_multi_agent_deepsearch(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compatibility wrapper for callers that still patch or import the legacy
    multi-agent entrypoint from this module.
    """
    from agent.runtime.deep.multi_agent.runtime import (
        run_multi_agent_deepsearch as _run_multi_agent_deepsearch,
    )

    return _run_multi_agent_deepsearch(state, config)
