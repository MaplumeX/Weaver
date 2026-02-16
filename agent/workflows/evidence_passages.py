from __future__ import annotations

import re
from typing import Dict, List, Tuple


def _paragraph_spans(text: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    if not text:
        return spans

    prev = 0
    for m in re.finditer(r"\n\s*\n+", text):
        end = m.start()
        if end > prev and text[prev:end].strip():
            spans.append((prev, end))
        prev = m.end()

    if prev < len(text) and text[prev:].strip():
        spans.append((prev, len(text)))
    return spans


def split_into_passages(text: str, *, max_chars: int = 1200) -> List[Dict[str, object]]:
    """
    Split a long text into passages with stable character offsets.

    Returns a list of dicts:
      - text: str
      - start_char: int (inclusive)
      - end_char: int (exclusive)
    """
    if not text:
        return []

    try:
        budget = int(max_chars)
    except Exception:
        budget = 0
    if budget <= 0:
        return []

    passages: List[Dict[str, object]] = []
    spans = _paragraph_spans(text)
    if not spans:
        spans = [(0, len(text))]

    chunk_start: int | None = None
    chunk_end: int | None = None

    def flush() -> None:
        nonlocal chunk_start, chunk_end
        if chunk_start is None or chunk_end is None:
            return
        snippet = text[chunk_start:chunk_end]
        if snippet.strip():
            passages.append({"text": snippet, "start_char": chunk_start, "end_char": chunk_end})
        chunk_start = None
        chunk_end = None

    for start, end in spans:
        span_len = end - start
        if span_len <= 0:
            continue

        if span_len > budget:
            flush()
            for sub_start in range(start, end, budget):
                sub_end = min(sub_start + budget, end)
                snippet = text[sub_start:sub_end]
                if snippet.strip():
                    passages.append({"text": snippet, "start_char": sub_start, "end_char": sub_end})
            continue

        if chunk_start is None:
            chunk_start = start
            chunk_end = end
            continue

        assert chunk_end is not None
        if end - chunk_start <= budget:
            chunk_end = end
            continue

        flush()
        chunk_start = start
        chunk_end = end

    flush()
    return passages
