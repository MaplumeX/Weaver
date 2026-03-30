"""
Stable search cache contracts for external callers.
"""

from agent.core.search_cache import (
    QueryDeduplicator,
    SearchCache,
    clear_search_cache,
    get_search_cache,
)

__all__ = [
    "QueryDeduplicator",
    "SearchCache",
    "clear_search_cache",
    "get_search_cache",
]
