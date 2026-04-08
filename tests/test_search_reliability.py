import concurrent.futures
import time
import warnings

import tools.search.orchestrator as orchestrator_module
from agent.core.search_cache import clear_search_cache
from tools.search.contracts import SearchProvider, SearchResult, SearchStrategy
from tools.search.orchestrator import (
    DuckDuckGoProvider,
    SearchOrchestrator,
)
from tools.search.reliability import ProviderReliabilityManager, ReliabilityPolicy


class FlakyProvider(SearchProvider):
    def __init__(self, name: str, fail_times: int):
        super().__init__(name)
        self.fail_times = fail_times
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("temporary failure")
        return [
            SearchResult(
                title="Recovered",
                url="https://example.com/recovered",
                snippet="ok",
                score=0.8,
                provider=self.name,
            )
        ]


class _EmptyProvider(SearchProvider):
    def __init__(self, name: str):
        super().__init__(name=name, api_key="test")
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        self.calls += 1
        return []


class _FixedProvider(SearchProvider):
    def __init__(self, name: str, url: str = "https://example.com/a"):
        super().__init__(name=name, api_key="test")
        self._url = url
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        self.calls += 1
        return [
            SearchResult(
                title="Result",
                url=self._url,
                snippet="snippet",
                content="",
                score=0.7,
                published_date="2026-02-01",
                provider=self.name,
            )
        ]


class _SlowProvider(SearchProvider):
    def __init__(self, name: str, delay_seconds: float):
        super().__init__(name=name, api_key="test")
        self.delay_seconds = delay_seconds

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        time.sleep(self.delay_seconds)
        return [
            SearchResult(
                title="Slow result",
                url=f"https://example.com/{self.name}",
                snippet="slow",
                score=0.4,
                provider=self.name,
            )
        ]


def test_reliability_manager_retries_until_success():
    manager = ProviderReliabilityManager(
        ReliabilityPolicy(
            max_retries=2,
            retry_backoff_seconds=0.0,
            circuit_breaker_failures=3,
            circuit_breaker_reset_seconds=60.0,
        )
    )

    attempts = {"n": 0}

    def flaky_call():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("temporary")
        return [1]

    result = manager.call("test-provider", flaky_call)

    assert result == [1]
    assert attempts["n"] == 3
    assert manager.is_open("test-provider") is False


def test_reliability_manager_opens_circuit_after_failures():
    manager = ProviderReliabilityManager(
        ReliabilityPolicy(
            max_retries=0,
            retry_backoff_seconds=0.0,
            circuit_breaker_failures=2,
            circuit_breaker_reset_seconds=60.0,
        )
    )

    attempts = {"n": 0}

    def always_fail():
        attempts["n"] += 1
        raise RuntimeError("down")

    assert manager.call("down-provider", always_fail) == []
    assert manager.call("down-provider", always_fail) == []
    assert manager.is_open("down-provider") is True

    calls_before_block = attempts["n"]
    assert manager.call("down-provider", always_fail) == []
    assert attempts["n"] == calls_before_block


def test_orchestrator_retries_transient_provider_errors():
    provider = FlakyProvider("tavily", fail_times=2)
    orchestrator = SearchOrchestrator(
        providers=[provider],
        strategy=SearchStrategy.FALLBACK,
    )

    results = orchestrator.search(
        query="ai chips",
        max_results=2,
        strategy=SearchStrategy.FALLBACK,
    )

    assert provider.calls == 3
    assert len(results) == 1
    assert results[0].title == "Recovered"


def test_orchestrator_provider_profile_keeps_safe_fallback_when_selected_provider_empty():
    providers = [
        _EmptyProvider("semantic_scholar"),
        _FixedProvider("duckduckgo"),
    ]
    orchestrator = SearchOrchestrator(
        providers=providers,
        strategy=SearchStrategy.FALLBACK,
    )

    clear_search_cache()
    results = orchestrator.search(
        query="test safe fallback",
        max_results=3,
        provider_profile=["semantic_scholar"],
    )

    assert results, "expected safe fallback provider to be tried when profile provider is empty"
    assert results[0].provider == "duckduckgo"


def test_orchestrator_retries_when_provider_records_error_and_returns_empty():
    """
    Providers often swallow exceptions and return [] while recording stats.error_count.
    The orchestrator should treat that as a failed attempt so the reliability manager
    can retry once before falling back.
    """

    class FlakyRecordedFailureProvider(SearchProvider):
        def __init__(self):
            super().__init__("flaky", api_key="test")
            self.calls = 0

        def is_available(self) -> bool:
            return True

        def search(self, query: str, max_results: int = 10):
            self.calls += 1
            if self.calls == 1:
                self.stats.record_failure("transient error")
                return []

            self.stats.record_success(latency_ms=1.0, quality=0.7)
            return [
                SearchResult(
                    title="OK",
                    url="https://example.com/ok",
                    snippet="ok",
                    score=0.7,
                    provider=self.name,
                )
            ]

    provider = FlakyRecordedFailureProvider()
    reliability = ProviderReliabilityManager(
        ReliabilityPolicy(
            max_retries=1,
            retry_backoff_seconds=0.0,
            circuit_breaker_failures=999,
            circuit_breaker_reset_seconds=0.0,
        )
    )
    orchestrator = SearchOrchestrator(
        providers=[provider],
        strategy=SearchStrategy.FALLBACK,
        reliability_manager=reliability,
    )

    clear_search_cache()
    results = orchestrator.search(query="test reliability retry", max_results=5)

    assert results
    assert provider.calls == 2


def test_orchestrator_parallel_search_timeout_is_handled(monkeypatch):
    def fake_wait(pending, timeout=None, return_when=None):
        return set(), pending

    monkeypatch.setattr(concurrent.futures, "wait", fake_wait)

    orchestrator = SearchOrchestrator(
        providers=[_FixedProvider("duckduckgo")],
        strategy=SearchStrategy.PARALLEL,
    )

    clear_search_cache()
    results = orchestrator.search(query="test parallel timeout", max_results=5)
    assert isinstance(results, list)


def test_orchestrator_parallel_timeout_does_not_block_until_slow_provider_finishes():
    orchestrator = SearchOrchestrator(
        providers=[
            _FixedProvider("fast"),
            _SlowProvider("slow", delay_seconds=0.2),
        ],
        strategy=SearchStrategy.PARALLEL,
    )
    orchestrator.parallel_timeout_seconds = 0.01

    clear_search_cache()
    started = time.perf_counter()
    results = orchestrator.search(query="test real timeout", max_results=5)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.15
    assert results
    assert results[0].provider == "fast"


def test_duckduckgo_provider_prefers_ddgs_module(monkeypatch):
    calls = []

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results=10):
            calls.append((query, max_results))
            return [
                {
                    "title": "Result",
                    "href": "example.com/result",
                    "body": "snippet",
                }
            ]

    monkeypatch.setattr(orchestrator_module, "_resolve_ddgs_module_name", lambda: "ddgs")
    monkeypatch.setattr(orchestrator_module, "_load_ddgs_class", lambda: (FakeDDGS, "ddgs"))

    provider = DuckDuckGoProvider()

    assert provider.is_available() is True
    results = provider.search("agent memory", max_results=4)

    assert calls == [("agent memory", 4)]
    assert len(results) == 1
    assert results[0].url == "https://example.com/result"
    assert results[0].provider == "duckduckgo"


def test_duckduckgo_provider_supports_legacy_module_without_runtime_warning(monkeypatch):
    warning_message = (
        "This package (`duckduckgo_search`) has been renamed to `ddgs`! "
        "Use `pip install ddgs` instead."
    )

    class LegacyDDGS:
        def __init__(self):
            warnings.warn(warning_message, RuntimeWarning, stacklevel=2)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results=10):
            return [
                {
                    "title": "Legacy Result",
                    "href": "legacy.example.com/result",
                    "body": "snippet",
                }
            ]

    monkeypatch.setattr(
        orchestrator_module,
        "_resolve_ddgs_module_name",
        lambda: "duckduckgo_search",
    )
    monkeypatch.setattr(
        orchestrator_module,
        "_load_ddgs_class",
        lambda: (LegacyDDGS, "duckduckgo_search"),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "_legacy_ddg_package_warning_logged",
        False,
    )

    provider = DuckDuckGoProvider()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        results = provider.search("legacy package", max_results=2)

    assert len(results) == 1
    assert not [item for item in captured if warning_message in str(item.message)]


def test_round_robin_fallback_skips_failed_provider_on_second_try():
    first = _EmptyProvider("first")
    second = _FixedProvider("second")
    orchestrator = SearchOrchestrator(
        providers=[first, second],
        strategy=SearchStrategy.ROUND_ROBIN,
    )

    clear_search_cache()
    results = orchestrator.search(
        query="round robin fallback",
        max_results=3,
        strategy=SearchStrategy.ROUND_ROBIN,
    )

    assert results
    assert results[0].provider == "second"
    assert first.calls == 1
    assert second.calls == 1
