"""Source, page, and passage adapters for public Deep Research artifacts."""

from __future__ import annotations

from typing import Any

from agent.foundation.source_urls import canonicalize_source_url, compact_unique_sources


def _sorted_tasks(task_queue: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = task_queue.get("tasks", []) if isinstance(task_queue, dict) else []
    if not isinstance(tasks, list):
        return []
    return sorted(
        (task for task in tasks if isinstance(task, dict)),
        key=lambda item: (
            int(item.get("priority", 0) or 0),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )


def _build_queries(task_queue: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for task in _sorted_tasks(task_queue):
        text = str(task.get("query") or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        queries.append(text)
    return queries


def _coerce_queries(value: Any) -> list[str]:
    if isinstance(value, list):
        queries: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            queries.append(text)
        return queries
    text = str(value or "").strip()
    return [text] if text else []


def _normalize_public_sources(items: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "title": item.get("title", ""),
                "url": item.get("raw_url") or item.get("rawUrl") or item.get("url") or "",
                "provider": item.get("provider", ""),
                "published_date": item.get("published_date") or item.get("publishedDate"),
            }
        )
    return compact_unique_sources(candidates, limit=max(5, len(candidates) or 5))


def _normalize_public_fetched_pages(items: Any) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = canonicalize_source_url(item.get("url") or item.get("raw_url") or item.get("rawUrl"))
        if not url:
            continue
        pages.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "section_id": item.get("section_id"),
                "branch_id": item.get("branch_id"),
                "url": url,
                "raw_url": str(item.get("raw_url") or item.get("rawUrl") or item.get("url") or ""),
                "title": str(item.get("title") or "").strip(),
                "excerpt": str(item.get("excerpt") or "").strip(),
                "content": str(item.get("content") or ""),
                "text": item.get("text"),
                "method": item.get("method"),
                "published_date": item.get("published_date"),
                "retrieved_at": item.get("retrieved_at"),
                "markdown": item.get("markdown"),
                "http_status": item.get("http_status"),
                "error": item.get("error"),
                "attempts": item.get("attempts"),
                "source_candidate_id": item.get("source_candidate_id"),
            }
        )
    return pages


def _normalize_public_passages(items: Any) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = canonicalize_source_url(item.get("url"))
        if not url:
            continue
        heading_path = item.get("heading_path")
        heading_items = heading_path if isinstance(heading_path, list) else []
        passages.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "section_id": item.get("section_id"),
                "branch_id": item.get("branch_id"),
                "document_id": item.get("document_id"),
                "url": url,
                "text": str(item.get("text") or ""),
                "quote": str(item.get("quote") or "").strip(),
                "source_title": str(item.get("source_title") or "").strip(),
                "snippet_hash": str(item.get("snippet_hash") or "").strip(),
                "heading": item.get("heading") or (heading_items[0] if heading_items else None),
                "heading_path": list(heading_items),
                "page_title": item.get("page_title"),
                "start_char": item.get("start_char"),
                "end_char": item.get("end_char"),
                "retrieved_at": item.get("retrieved_at"),
                "method": item.get("method"),
                "locator": dict(item.get("locator") or {}),
                "source_published_date": item.get("source_published_date"),
                "passage_kind": str(item.get("passage_kind") or "quote").strip(),
                "admissible": bool(item.get("admissible", True)),
                "authoritative": bool(item.get("authoritative", item.get("admissible", True))),
            }
        )
    return passages


def _normalize_lightweight_sources(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    bundles = artifact_store.get("evidence_bundles", []) if isinstance(artifact_store, dict) else []
    for bundle in bundles if isinstance(bundles, list) else []:
        if not isinstance(bundle, dict):
            continue
        for source in bundle.get("sources", []) or []:
            if not isinstance(source, dict):
                continue
            candidates.append(
                {
                    "title": source.get("title", ""),
                    "url": source.get("url", ""),
                    "provider": source.get("provider", ""),
                    "published_date": source.get("published_date"),
                }
            )
    final_report = artifact_store.get("final_report", {}) if isinstance(artifact_store, dict) else {}
    citation_urls = final_report.get("citation_urls", []) if isinstance(final_report, dict) else []
    for url in citation_urls if isinstance(citation_urls, list) else []:
        candidates.append({"title": str(url or ""), "url": url})
    return compact_unique_sources(candidates, limit=max(5, len(candidates) or 5))


def _normalize_lightweight_fetched_pages(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    bundles = artifact_store.get("evidence_bundles", []) if isinstance(artifact_store, dict) else []
    for bundle in bundles if isinstance(bundles, list) else []:
        if not isinstance(bundle, dict):
            continue
        for item in bundle.get("documents", []) or []:
            if not isinstance(item, dict):
                continue
            url = canonicalize_source_url(item.get("url"))
            if not url:
                continue
            pages.append(
                {
                    "id": item.get("id"),
                    "task_id": bundle.get("task_id"),
                    "section_id": bundle.get("section_id"),
                    "branch_id": bundle.get("branch_id"),
                    "url": url,
                    "raw_url": item.get("raw_url"),
                    "title": str(item.get("title") or "").strip(),
                    "excerpt": str(item.get("excerpt") or "").strip(),
                    "content": str(item.get("content") or ""),
                    "text": item.get("content"),
                    "method": item.get("method"),
                    "published_date": item.get("published_date"),
                    "retrieved_at": item.get("retrieved_at"),
                    "markdown": item.get("markdown"),
                    "http_status": item.get("http_status"),
                    "error": item.get("error"),
                    "attempts": item.get("attempts"),
                }
            )
    return pages


def _normalize_lightweight_passages(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    bundles = artifact_store.get("evidence_bundles", []) if isinstance(artifact_store, dict) else []
    for bundle in bundles if isinstance(bundles, list) else []:
        if not isinstance(bundle, dict):
            continue
        for item in bundle.get("passages", []) or []:
            if not isinstance(item, dict):
                continue
            url = canonicalize_source_url(item.get("url"))
            if not url:
                continue
            passages.append(
                {
                    "id": item.get("id"),
                    "task_id": bundle.get("task_id"),
                    "section_id": bundle.get("section_id"),
                    "branch_id": bundle.get("branch_id"),
                    "document_id": item.get("document_id"),
                    "url": url,
                    "text": str(item.get("text") or ""),
                    "quote": str(item.get("quote") or "").strip(),
                    "source_title": str(item.get("source_title") or "").strip(),
                    "snippet_hash": str(item.get("snippet_hash") or "").strip(),
                    "heading": (list(item.get("heading_path") or []) or [None])[0],
                    "heading_path": list(item.get("heading_path") or []),
                    "page_title": item.get("page_title"),
                    "start_char": item.get("start_char"),
                    "end_char": item.get("end_char"),
                    "retrieved_at": item.get("retrieved_at"),
                    "method": item.get("method"),
                    "locator": dict(item.get("locator") or {}),
                    "source_published_date": item.get("source_published_date"),
                    "passage_kind": str(item.get("passage_kind") or "quote").strip(),
                    "admissible": bool(item.get("admissible", True)),
                    "authoritative": bool(item.get("authoritative", item.get("admissible", True))),
                }
            )
    return passages


__all__ = [
    "_build_queries",
    "_coerce_queries",
    "_normalize_lightweight_fetched_pages",
    "_normalize_lightweight_passages",
    "_normalize_lightweight_sources",
    "_normalize_public_fetched_pages",
    "_normalize_public_passages",
    "_normalize_public_sources",
    "_sorted_tasks",
]
