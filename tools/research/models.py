from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def truncate_bytes(data: bytes, *, max_bytes: int) -> bytes:
    """Truncate a bytes payload to at most max_bytes (0 disables truncation)."""
    try:
        limit = int(max_bytes)
    except Exception:
        limit = 0

    if limit <= 0:
        return data

    return data[:limit]


@dataclass
class FetchedPage:
    url: str
    raw_url: str
    method: str
    text: str | None = None
    title: str | None = None
    published_date: str | None = None
    retrieved_at: str | None = None
    markdown: str | None = None
    http_status: int | None = None
    error: str | None = None
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": _json_safe(self.url),
            "raw_url": _json_safe(self.raw_url),
            "title": _json_safe(self.title),
            "published_date": _json_safe(self.published_date),
            "retrieved_at": _json_safe(self.retrieved_at),
            "method": _json_safe(self.method),
            "text": _json_safe(self.text),
            "markdown": _json_safe(self.markdown),
            "http_status": _json_safe(self.http_status),
            "error": _json_safe(self.error),
            "attempts": _json_safe(self.attempts),
        }
