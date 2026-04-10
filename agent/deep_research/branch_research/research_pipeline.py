"""Search, document, and passage helpers for branch research."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from agent.deep_research.branch_research.shared import (
    canonical_url as _canonical_url,
)
from agent.deep_research.branch_research.shared import (
    clamp_text as _clamp_text,
)
from agent.deep_research.branch_research.shared import (
    source_domain as _source_domain,
)
from agent.deep_research.branch_research.shared import (
    task_texts as _task_texts,
)
from agent.deep_research.branch_research.shared import (
    tokenize as _tokenize,
)
from agent.deep_research.schema import ResearchTask
from agent.foundation.passages import split_into_passages

logger = logging.getLogger(__name__)


def _is_rag_result(item: dict[str, Any]) -> bool:
    return str(item.get("provider") or "").strip() == "milvus_rag" or str(item.get("source_type") or "").strip() == "knowledge_file"


def search_queries(
    search_func: Any,
    config: dict[str, Any],
    queries: list[str],
    *,
    max_results_per_query: int,
) -> list[dict[str, Any]]:
    all_results: list[dict[str, Any]] = []
    for query in queries:
        try:
            results = search_func(
                {"query": query, "max_results": max_results_per_query},
                config=config,
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


def rank_search_results(
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
    return sorted(
        deduped.values(),
        key=lambda item: (
            -float(item.get("rank_score", 0.0) or 0.0),
            -float(item.get("score", 0.0) or 0.0),
            str(item.get("title") or ""),
        ),
    )


def build_documents_and_sources(
    task: ResearchTask,
    ranked_results: list[dict[str, Any]],
    *,
    fetcher: Any,
    fetch_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_results = select_fetch_targets(ranked_results, limit=fetch_limit)
    selected_urls = [
        str(item.get("url") or "").strip()
        for item in selected_results
        if item.get("url") and not _is_rag_result(item)
    ]
    fetched_pages = {
        _canonical_url(page.url): page
        for page in fetcher.fetch_many(selected_urls)
        if getattr(page, "url", None)
    }

    documents: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for result in selected_results:
        url = str(result.get("url") or "").strip()
        if not url:
            continue
        if _is_rag_result(result):
            document = document_from_rag_result(task, result)
        else:
            fetched = fetched_pages.get(_canonical_url(url))
            if fetched and str(fetched.markdown or fetched.text or "").strip():
                document = document_from_page(task, result, fetched)
            else:
                document = document_from_search_snippet(task, result)
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


def select_fetch_targets(ranked_results: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    selected: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    deferred: list[dict[str, Any]] = []

    for item in ranked_results:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        if _is_rag_result(item):
            selected.append(item)
            if len(selected) >= limit:
                return selected[:limit]
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


def document_from_page(
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


def document_from_search_snippet(
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


def document_from_rag_result(
    task: ResearchTask,
    result: dict[str, Any],
) -> dict[str, Any]:
    url = str(result.get("url") or result.get("raw_url") or "").strip()
    content = str(result.get("content") or result.get("raw_excerpt") or result.get("summary") or "").strip()
    chunk_id = str(result.get("chunk_id") or "").strip()
    file_id = str(result.get("knowledge_file_id") or result.get("document_id") or "").strip()
    digest_seed = chunk_id or f"{file_id}:{url}"
    digest = hashlib.sha1(f"{task.id}:{digest_seed}:rag".encode()).hexdigest()[:12]
    return {
        "id": f"document_{digest}",
        "url": url,
        "raw_url": str(result.get("raw_url") or url).strip(),
        "title": str(result.get("title") or file_id or url).strip(),
        "excerpt": _clamp_text(content, 320),
        "content": _clamp_text(content, 4_000),
        "method": "milvus_rag",
        "published_date": result.get("published_date"),
        "retrieved_at": result.get("retrieved_at"),
        "http_status": None,
        "attempts": 1,
        "provider": "milvus_rag",
        "authoritative": True,
        "admissible": True,
    }


def build_passages(
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
