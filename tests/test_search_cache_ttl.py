import time

import tools.search.multi_search as multi_search_module
from agent.core.search_cache import SearchCache
from tools.search.multi_search import (
    MultiSearchOrchestrator,
    SearchProvider,
    SearchResult,
    SearchStrategy,
)


class _DummyProvider(SearchProvider):
    def __init__(self):
        super().__init__("dummy")
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        self.calls += 1
        return [
            SearchResult(
                title="Result",
                url="https://example.com/result",
                snippet="ok",
                score=0.6,
                provider=self.name,
            )
        ]


class _UnavailableProvider(SearchProvider):
    def __init__(self):
        super().__init__("unavailable")

    def is_available(self) -> bool:
        return False

    def search(self, query: str, max_results: int = 10):
        raise AssertionError("cached result should be returned before provider execution")


def test_multi_search_cache_respects_ttl(monkeypatch):
    provider = _DummyProvider()
    cache = SearchCache(max_size=10, ttl_seconds=0.01, similarity_threshold=1.0)

    monkeypatch.setattr(multi_search_module, "get_search_cache", lambda: cache)

    orchestrator = MultiSearchOrchestrator(
        providers=[provider],
        strategy=SearchStrategy.FALLBACK,
    )

    orchestrator.search("quantum chips", max_results=2, strategy=SearchStrategy.FALLBACK)
    orchestrator.search("quantum chips", max_results=2, strategy=SearchStrategy.FALLBACK)
    assert provider.calls == 1

    time.sleep(0.02)
    orchestrator.search("quantum chips", max_results=2, strategy=SearchStrategy.FALLBACK)
    assert provider.calls == 2


def test_multi_search_cache_hit_survives_unavailable_providers(monkeypatch):
    cache = SearchCache(max_size=10, ttl_seconds=60, similarity_threshold=1.0)
    query = "cached ai timeline"
    cache.set(
        "multi_search::fallback::2::::cached ai timeline",
        [
            {
                "title": "Cached",
                "url": "https://example.com/cached",
                "snippet": "cached",
                "content": "",
                "score": 0.8,
                "provider": "cache",
            }
        ],
    )

    monkeypatch.setattr(multi_search_module, "get_search_cache", lambda: cache)

    orchestrator = MultiSearchOrchestrator(
        providers=[_UnavailableProvider()],
        strategy=SearchStrategy.FALLBACK,
    )

    results = orchestrator.search(query, max_results=2, strategy=SearchStrategy.FALLBACK)

    assert len(results) == 1
    assert results[0].url == "https://example.com/cached"
