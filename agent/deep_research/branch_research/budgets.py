"""Budget and source-compaction helpers for Deep Research."""

from __future__ import annotations

import time
from typing import Any


def _estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, len(str(text)) // 4)


def _estimate_tokens_from_results(results: list[dict[str, Any]]) -> int:
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
) -> str | None:
    if max_seconds > 0 and (time.time() - start_ts) >= max_seconds:
        return "time_budget_exceeded"
    if max_tokens > 0 and tokens_used >= max_tokens:
        return "token_budget_exceeded"
    if max_searches > 0 and searches_used >= max_searches:
        return "search_budget_exceeded"
    return None


def _compact_sources(results: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    seen: set[str] = set()
    compacted: list[dict[str, Any]] = []
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


__all__ = [
    "_budget_stop_reason",
    "_compact_sources",
    "_estimate_tokens_from_results",
    "_estimate_tokens_from_text",
]
