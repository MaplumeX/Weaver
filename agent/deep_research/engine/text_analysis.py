"""Text normalization and overlap helpers for the Deep Research engine."""

from __future__ import annotations

import re
from typing import Any


def _dedupe_texts(values: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values or []:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _coverage_tokens(text: str) -> list[str]:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return []
    tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", normalized)
    return [token for token in tokens if len(token) >= 2]


def _text_overlap_score(left: str, right: str) -> float:
    left_tokens = set(_coverage_tokens(left))
    right_tokens = set(_coverage_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(1, min(len(left_tokens), len(right_tokens)))


def _needs_freshness_advisory(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    freshness_markers = (
        "latest",
        "current",
        "recent",
        "today",
        "newest",
        "最新",
        "当前",
        "近期",
        "最近",
        "今年",
        "本月",
    )
    return any(marker in normalized for marker in freshness_markers)


__all__ = [
    "_dedupe_texts",
    "_needs_freshness_advisory",
    "_text_overlap_score",
]
