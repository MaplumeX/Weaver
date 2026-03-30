"""
Compatibility adapter for workflow code that still imports search-cache helpers
from the historical `agent.workflows.search_cache` location.
"""

from agent.contracts.search_cache import QueryDeduplicator, get_search_cache


class WorkflowSearchCacheAdapter:
    """Explicit adapter name to avoid introducing a second core SearchCache type."""

    def __init__(self):
        self._cache = get_search_cache()

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value) -> None:
        self._cache.set(key, value)

    def clear(self) -> None:
        self._cache.clear()


__all__ = ["WorkflowSearchCacheAdapter", "QueryDeduplicator", "get_search_cache"]
