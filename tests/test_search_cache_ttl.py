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
