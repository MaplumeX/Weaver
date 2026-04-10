"""
Shared helpers for the branch-scoped researcher runtime.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from agent.deep_research.schema import ResearchTask

_TIME_SENSITIVE_MARKERS = (
    "latest",
    "recent",
    "today",
    "current",
    "update",
    "news",
    "最新",
    "近期",
    "今天",
    "动态",
    "新闻",
)


def clamp_text(text: str, limit: int) -> str:
    value = str(text or "").strip()
    return value[:limit] if limit > 0 else value


def dedupe_strings(values: list[Any], *, limit: int = 0) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if limit > 0 and len(deduped) >= limit:
            break
    return deduped


def tokenize(text: str) -> set[str]:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return set()
    return {
        token
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{1,6}", normalized)
        if len(token) >= 2 or re.fullmatch(r"[\u4e00-\u9fff]", token)
    }


def canonical_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    scheme = (parts.scheme or "").lower()
    netloc = (parts.netloc or "").lower()
    path = parts.path.rstrip("/")
    if not scheme or not netloc:
        return text.rstrip("/")
    return f"{scheme}://{netloc}{path}"


def source_domain(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except Exception:
        return ""


def task_texts(task: ResearchTask) -> list[str]:
    texts = [
        task.goal,
        task.objective,
        task.query,
        task.title,
        task.aspect,
        *list(task.acceptance_criteria or []),
        *list(task.query_hints or []),
        *list(task.coverage_targets or []),
        *list(task.source_preferences or []),
        *list(task.language_hints or []),
    ]
    return [str(item).strip() for item in texts if str(item).strip()]


def is_time_sensitive_task(task: ResearchTask) -> bool:
    candidates = [
        task.query,
        task.objective,
        task.goal,
        task.time_boundary,
        *(task.query_hints or []),
        *(task.coverage_targets or []),
    ]
    normalized = " ".join(str(item or "").strip().lower() for item in candidates if str(item or "").strip())
    return any(marker in normalized for marker in _TIME_SENSITIVE_MARKERS) or bool(re.search(r"\b20\d{2}\b", normalized))
