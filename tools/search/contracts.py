from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}


def _canonicalize_result_url(raw_url: str) -> str:
    raw = str(raw_url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"

    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw

    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    if not netloc:
        return raw

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
        if not path:
            path = "/"

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = str(key).strip().lower()
        if normalized_key.startswith("utm_"):
            continue
        if normalized_key in _TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, value))
    query_items.sort()
    query = urlencode(query_items, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


class SearchStrategy(str, Enum):
    """Search execution strategy."""

    FALLBACK = "fallback"
    PARALLEL = "parallel"
    ROUND_ROBIN = "round_robin"
    BEST_FIRST = "best_first"


@dataclass
class SearchResult:
    """Normalized search result used by the unified web search runtime."""

    title: str
    url: str
    snippet: str
    content: str = ""
    score: float = 0.0
    published_date: str | None = None
    provider: str = ""
    summary: str = ""
    raw_excerpt: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.url = _canonicalize_result_url(self.url)

    @property
    def domain(self) -> str:
        """Extract domain from URL."""
        try:
            return urlparse(self.url).netloc
        except Exception:
            return ""

    @property
    def url_hash(self) -> str:
        """Get hash of URL for deduplication."""
        return hashlib.md5(self.url.encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        snippet = str(self.snippet or self.summary or "").strip()
        summary = str(self.summary or snippet).strip()
        raw_excerpt = str(self.raw_excerpt or self.content or snippet).strip()
        content = str(self.content or raw_excerpt or snippet).strip()
        return {
            "title": self.title,
            "url": self.url,
            "summary": summary,
            "snippet": snippet,
            "raw_excerpt": raw_excerpt,
            "content": content,
            "score": self.score,
            "published_date": self.published_date,
            "provider": self.provider,
        }


@dataclass
class ProviderStats:
    """Track provider performance statistics."""

    name: str
    total_calls: int = 0
    success_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0
    avg_result_quality: float = 0.5
    last_error: str | None = None
    last_error_time: str | None = None
    is_healthy: bool = True
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.success_count / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.success_count == 0:
            return 0
        return self.total_latency_ms / self.success_count

    def record_success(self, latency_ms: float, quality: float = 0.5) -> None:
        self.total_calls += 1
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.avg_result_quality = (self.avg_result_quality * 0.9) + (quality * 0.1)
        self.consecutive_failures = 0
        self.is_healthy = True

    def record_failure(self, error: str) -> None:
        self.total_calls += 1
        self.error_count += 1
        self.last_error = error
        self.last_error_time = datetime.now().isoformat()
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.is_healthy = False


class SearchProvider(ABC):
    """Abstract base class for search providers."""

    def __init__(self, name: str, api_key: str | None = None):
        self.name = name
        self.api_key = api_key
        self.stats = ProviderStats(name=name)

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Execute a search query and return normalized results."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available."""

    def get_stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "success_rate": self.stats.success_rate,
            "avg_latency_ms": self.stats.avg_latency_ms,
            "avg_result_quality": self.stats.avg_result_quality,
            "is_healthy": self.stats.is_healthy,
        }


__all__ = [
    "ProviderStats",
    "SearchProvider",
    "SearchResult",
    "SearchStrategy",
]
