"""
Unified web search orchestrator.

Implements multi-provider search with result aggregation, reliability controls,
and ranking for the public `web_search` runtime.
"""

import copy
import importlib
import importlib.util
import logging
import math
import re
import time
import warnings
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from agent.contracts.search_cache import get_search_cache
from common.config import settings
from tools.search.contracts import SearchProvider, SearchResult, SearchStrategy
from tools.search.providers import (
    bing_search,
    exa_search,
    firecrawl_search,
    google_cse_search,
    serpapi_search,
    serper_search,
    tavily_api_search,
)
from tools.search.reliability import ProviderReliabilityManager, ReliabilityPolicy

logger = logging.getLogger(__name__)

_DDGS_MODULE_NAMES = ("ddgs", "duckduckgo_search")
_LEGACY_DDG_WARNING_PATTERN = (
    r"This package \(`duckduckgo_search`\) has been renamed to `ddgs`! "
    r"Use `pip install ddgs` instead\."
)
_legacy_ddg_package_warning_logged = False


def _resolve_ddgs_module_name() -> str | None:
    for module_name in _DDGS_MODULE_NAMES:
        if importlib.util.find_spec(module_name) is not None:
            return module_name
    return None


def _load_ddgs_class() -> tuple[Any, str | None]:
    module_name = _resolve_ddgs_module_name()
    if not module_name:
        return None, None

    module = importlib.import_module(module_name)
    return getattr(module, "DDGS", None), module_name


def _log_legacy_ddg_package_once(module_name: str | None) -> None:
    global _legacy_ddg_package_warning_logged
    if module_name != "duckduckgo_search" or _legacy_ddg_package_warning_logged:
        return

    logger.warning("[DuckDuckGoProvider] Using legacy duckduckgo_search package; prefer ddgs")
    _legacy_ddg_package_warning_logged = True


class TavilyProvider(SearchProvider):
    """Tavily search provider (primary)."""

    def __init__(self):
        super().__init__("tavily", settings.tavily_api_key)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        start_time = time.time()
        try:
            raw_results = tavily_api_search(query=query, max_results=max_results)

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("summary", r.get("snippet", "")),
                    content=r.get("raw_excerpt", ""),
                    score=float(r.get("score", 0.5)),
                    published_date=r.get("published_date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.8)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[TavilyProvider] Search failed: {e}")
            return []


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo search provider (no API key required)."""

    def __init__(self):
        super().__init__("duckduckgo")

    def is_available(self) -> bool:
        return _resolve_ddgs_module_name() is not None

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        try:
            DDGS, module_name = _load_ddgs_class()
        except ImportError:
            logger.warning("[DuckDuckGoProvider] ddgs not installed")
            return []

        if DDGS is None:
            logger.warning("[DuckDuckGoProvider] DDGS class unavailable")
            return []

        start_time = time.time()
        try:
            _log_legacy_ddg_package_once(module_name)

            if module_name == "duckduckgo_search":
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=_LEGACY_DDG_WARNING_PATTERN,
                        category=RuntimeWarning,
                    )
                    with DDGS() as ddgs:
                        raw_results = list(ddgs.text(query, max_results=max_results))
            else:
                with DDGS() as ddgs:
                    raw_results = list(ddgs.text(query, max_results=max_results))

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", r.get("link", "")),
                    snippet=r.get("body", r.get("snippet", "")),
                    content="",
                    score=0.5,  # DDG doesn't provide scores
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.6)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[DuckDuckGoProvider] Search failed: {e}")
            return []


class BraveProvider(SearchProvider):
    """Brave Search provider."""

    def __init__(self):
        api_key = getattr(settings, "brave_api_key", None)
        super().__init__("brave", api_key)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        import requests

        start_time = time.time()
        try:
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            }
            params = {
                "q": query,
                "count": max_results,
            }
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for r in data.get("web", {}).get("results", []):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("description", ""),
                    content="",
                    score=0.6,
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.7)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[BraveProvider] Search failed: {e}")
            return []


class SerperProvider(SearchProvider):
    """Serper.dev Google Search provider."""

    def __init__(self):
        api_key = getattr(settings, "serper_api_key", None)
        super().__init__("serper", api_key)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        start_time = time.time()
        try:
            raw_results = serper_search(query=query, max_results=max_results)

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    content=r.get("content", ""),
                    score=float(r.get("score", 0.7) or 0.7),
                    published_date=r.get("published_date") or r.get("date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.8)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[SerperProvider] Search failed: {e}")
            return []


class ExaProvider(SearchProvider):
    """Exa.ai neural search provider."""

    def __init__(self):
        api_key = getattr(settings, "exa_api_key", None)
        super().__init__("exa", api_key)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        start_time = time.time()
        try:
            raw_results = exa_search(query=query, max_results=max_results)

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    content=r.get("content", r.get("snippet", "")),
                    score=float(r.get("score", 0.7) or 0.7),
                    published_date=r.get("published_date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.85)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[ExaProvider] Search failed: {e}")
            return []


class SerpApiProvider(SearchProvider):
    """SerpAPI search provider."""

    def __init__(self):
        super().__init__("serpapi", getattr(settings, "serpapi_api_key", None))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        start_time = time.time()
        try:
            raw_results = serpapi_search(query=query, max_results=max_results)

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    content=r.get("content", r.get("snippet", "")),
                    score=float(r.get("score", 0.65) or 0.65),
                    published_date=r.get("published_date") or r.get("date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.72)
            return results
        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[SerpApiProvider] Search failed: {e}")
            return []


class BingProvider(SearchProvider):
    """Bing Search API provider."""

    def __init__(self):
        super().__init__("bing", getattr(settings, "bing_api_key", None))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        start_time = time.time()
        try:
            raw_results = bing_search(query=query, max_results=max_results)

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    content=r.get("content", r.get("snippet", "")),
                    score=float(r.get("score", 0.64) or 0.64),
                    published_date=r.get("published_date") or r.get("date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.7)
            return results
        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[BingProvider] Search failed: {e}")
            return []


class GoogleCSEProvider(SearchProvider):
    """Google Custom Search provider."""

    def __init__(self):
        super().__init__("google_cse", getattr(settings, "google_search_api_key", None))

    def is_available(self) -> bool:
        return bool(self.api_key) and bool(getattr(settings, "google_search_engine_id", ""))

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        start_time = time.time()
        try:
            raw_results = google_cse_search(query=query, max_results=max_results)

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    content=r.get("content", r.get("snippet", "")),
                    score=float(r.get("score", 0.66) or 0.66),
                    published_date=r.get("published_date") or r.get("date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.74)
            return results
        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[GoogleCSEProvider] Search failed: {e}")
            return []


class FirecrawlProvider(SearchProvider):
    """Firecrawl search provider."""

    def __init__(self):
        super().__init__("firecrawl", getattr(settings, "firecrawl_api_key", None))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        start_time = time.time()
        try:
            raw_results = firecrawl_search(query=query, max_results=max_results)

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    content=r.get("markdown", r.get("content", r.get("snippet", ""))),
                    score=float(r.get("score", 0.68) or 0.68),
                    published_date=r.get("published_date") or r.get("date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.76)
            return results
        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[FirecrawlProvider] Search failed: {e}")
            return []


# Import feed providers (lazy to avoid circular imports)
def _get_feed_providers() -> list[SearchProvider]:
    """Get available real-time feed providers."""
    providers = []
    try:
        from tools.search.feeds.hackernews_provider import HackerNewsProvider
        hn = HackerNewsProvider()
        if hn.is_available():
            providers.append(hn)
    except ImportError:
        pass

    try:
        from tools.search.feeds.twitter_provider import TwitterProvider
        twitter = TwitterProvider()
        if twitter.is_available():
            providers.append(twitter)
    except ImportError:
        pass

    try:
        from tools.search.feeds.reddit_provider import RedditProvider
        reddit = RedditProvider()
        if reddit.is_available():
            providers.append(reddit)
    except ImportError:
        pass

    return providers


# Import academic providers (lazy to avoid circular imports)
def _get_academic_providers() -> list[SearchProvider]:
    """Get available academic search providers."""
    providers = []
    try:
        from tools.search.academic.arxiv_provider import ArxivProvider
        arxiv = ArxivProvider()
        if arxiv.is_available():
            providers.append(arxiv)
    except ImportError:
        pass

    try:
        from tools.search.academic.semantic_scholar_provider import SemanticScholarProvider
        ss = SemanticScholarProvider()
        if ss.is_available():
            providers.append(ss)
    except ImportError:
        pass

    try:
        from tools.search.academic.pubmed_provider import PubMedProvider
        pm = PubMedProvider()
        if pm.is_available():
            providers.append(pm)
    except ImportError:
        pass

    return providers


class SearchOrchestrator:
    """
    Orchestrates searches across multiple providers.

    Supports multiple strategies:
    - FALLBACK: Try providers sequentially until success
    - PARALLEL: Query all providers in parallel, merge results
    - ROUND_ROBIN: Distribute queries across providers
    - BEST_FIRST: Use best performing provider first
    """

    def __init__(
        self,
        providers: list[SearchProvider] | None = None,
        strategy: SearchStrategy = SearchStrategy.FALLBACK,
        similarity_threshold: float = 0.7,
        reliability_manager: ProviderReliabilityManager | None = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            providers: List of search providers to use
            strategy: Search execution strategy
            similarity_threshold: Threshold for content similarity deduplication
        """
        self.providers = providers or self._init_default_providers()
        self.strategy = strategy
        self.similarity_threshold = similarity_threshold
        self._round_robin_index = 0
        self.enable_freshness_ranking = bool(
            getattr(settings, "search_enable_freshness_ranking", True)
        )
        self.freshness_half_life_days = max(
            1.0, float(getattr(settings, "search_freshness_half_life_days", 30.0))
        )
        self.freshness_weight = min(
            1.0, max(0.0, float(getattr(settings, "search_freshness_weight", 0.35)))
        )
        self.parallel_timeout_seconds = max(
            0.0, float(getattr(settings, "search_parallel_timeout_seconds", 30.0))
        )
        self.parallel_max_workers = max(
            1, int(getattr(settings, "search_parallel_max_workers", 8))
        )

        policy = ReliabilityPolicy(
            max_retries=max(0, int(getattr(settings, "search_reliability_max_retries", 2))),
            retry_backoff_seconds=max(
                0.0, float(getattr(settings, "search_reliability_retry_backoff_seconds", 0.5))
            ),
            circuit_breaker_failures=max(
                1, int(getattr(settings, "search_reliability_circuit_breaker_failures", 3))
            ),
            circuit_breaker_reset_seconds=max(
                0.0,
                float(getattr(settings, "search_reliability_circuit_breaker_reset_seconds", 60.0)),
            ),
        )
        self.reliability_manager = reliability_manager or ProviderReliabilityManager(policy)

    def _init_default_providers(self) -> list[SearchProvider]:
        """Initialize default providers based on available API keys."""
        providers = []

        # Tavily (primary)
        tavily = TavilyProvider()
        if tavily.is_available():
            providers.append(tavily)

        # DuckDuckGo (fallback, no API key needed)
        ddg = DuckDuckGoProvider()
        if ddg.is_available():
            providers.append(ddg)

        # Brave
        brave = BraveProvider()
        if brave.is_available():
            providers.append(brave)

        # Serper
        serper = SerperProvider()
        if serper.is_available():
            providers.append(serper)

        serpapi = SerpApiProvider()
        if serpapi.is_available():
            providers.append(serpapi)

        bing = BingProvider()
        if bing.is_available():
            providers.append(bing)

        google_cse = GoogleCSEProvider()
        if google_cse.is_available():
            providers.append(google_cse)

        # Exa
        exa = ExaProvider()
        if exa.is_available():
            providers.append(exa)

        firecrawl = FirecrawlProvider()
        if firecrawl.is_available():
            providers.append(firecrawl)

        # Real-time feed providers
        feed_providers = _get_feed_providers()
        providers.extend(feed_providers)

        # Academic providers
        academic_providers = _get_academic_providers()
        providers.extend(academic_providers)

        logger.info(
            f"[SearchOrchestrator] Initialized {len(providers)} providers: {[p.name for p in providers]}"
        )
        return providers

    def get_available_providers(self) -> list[SearchProvider]:
        """Get list of currently healthy and available providers."""
        return [p for p in self.providers if p.is_available() and p.stats.is_healthy]

    def search(
        self,
        query: str,
        max_results: int = 10,
        strategy: SearchStrategy | None = None,
        provider_profile: list[str] | None = None,
    ) -> list[SearchResult]:
        """
        Execute a search using the configured strategy.

        Args:
            query: Search query
            max_results: Maximum number of results
            strategy: Override the default strategy

        Returns:
            List of deduplicated search results
        """
        strategy = strategy or self.strategy
        cache = get_search_cache()
        cache_key = self._cache_query_key(query, max_results, strategy, provider_profile)
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info(f"[SearchOrchestrator] cache hit for query='{query[:80]}'")
            return self._from_cached_results(cached)

        available = self.get_available_providers()
        available = self._apply_provider_profile(available, provider_profile)

        if not available:
            logger.error("[SearchOrchestrator] No available search providers")
            return []

        results: list[SearchResult]
        if strategy == SearchStrategy.FALLBACK:
            results = self._search_fallback(query, max_results, available)
        elif strategy == SearchStrategy.PARALLEL:
            results = self._search_parallel(query, max_results, available)
        elif strategy == SearchStrategy.ROUND_ROBIN:
            results = self._search_round_robin(query, max_results, available)
        elif strategy == SearchStrategy.BEST_FIRST:
            results = self._search_best_first(query, max_results, available)
        else:
            results = self._search_fallback(query, max_results, available)

        if results:
            cache.set(cache_key, [r.to_dict() for r in results])

        return results

    def _cache_query_key(
        self,
        query: str,
        max_results: int,
        strategy: SearchStrategy,
        provider_profile: list[str] | None,
    ) -> str:
        profile = ",".join(provider_profile or [])
        return f"web_search::{strategy.value}::{max_results}::{profile}::{query}"

    def _from_cached_results(self, cached: list[dict[str, Any]]) -> list[SearchResult]:
        results: list[SearchResult] = []
        for item in cached or []:
            if not isinstance(item, dict):
                continue
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    content=item.get("content", ""),
                    score=float(item.get("score", 0.0) or 0.0),
                    published_date=item.get("published_date"),
                    provider=item.get("provider", ""),
                    raw_data=copy.deepcopy(item),
                )
            )
        return results

    def _apply_provider_profile(
        self,
        providers: list[SearchProvider],
        provider_profile: list[str] | None,
    ) -> list[SearchProvider]:
        """Filter/reorder providers by requested profile while keeping safe fallback.

        Provider profiles are used as a preference signal (ordering + prioritization),
        not a hard allow-list. In practice, a narrow profile can accidentally exclude
        general providers (e.g., DuckDuckGo/Tavily) and cause empty results even when
        a safe fallback exists.

        To keep the system robust, we return:
        - profile-matched providers first (in requested order)
        - then append the remaining available providers (stable order)
        """
        if not provider_profile:
            return providers

        preferred = [str(name).strip().lower() for name in provider_profile if str(name).strip()]
        if not preferred:
            return providers

        providers_by_name = {p.name.lower(): p for p in providers}
        selected: list[SearchProvider] = []
        for name in preferred:
            provider = providers_by_name.get(name)
            if provider and provider not in selected:
                selected.append(provider)

        if selected:
            remaining = [p for p in providers if p not in selected]
            ordered = selected + remaining
            logger.info(
                f"[SearchOrchestrator] Provider profile selected: {[p.name for p in selected]}"
            )
            return ordered

        logger.warning(
            f"[SearchOrchestrator] Provider profile had no available matches: {preferred}, "
            "falling back to default provider pool"
        )
        return providers

    def _call_provider(
        self,
        provider: SearchProvider,
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        """Call provider through reliability layer (retry + circuit breaker)."""
        def call_once() -> list[SearchResult]:
            # Many provider adapters swallow exceptions and return [] while recording
            # error stats. Treat that as a failed attempt so the reliability layer can retry.
            before_errors = int(getattr(provider.stats, "error_count", 0) or 0)
            results = provider.search(query, max_results)
            after_errors = int(getattr(provider.stats, "error_count", 0) or 0)

            if isinstance(results, list) and not results and after_errors > before_errors:
                msg = provider.stats.last_error or f"{provider.name} returned empty results due to error"
                raise RuntimeError(msg)

            return results if isinstance(results, list) else []

        result = self.reliability_manager.call(provider.name, call_once)
        return result if isinstance(result, list) else []

    def _search_fallback(
        self,
        query: str,
        max_results: int,
        providers: list[SearchProvider],
    ) -> list[SearchResult]:
        """Try providers sequentially until success."""
        for provider in providers:
            results = self._call_provider(provider, query, max_results)
            if results:
                logger.info(
                    f"[SearchOrchestrator] Got {len(results)} results from {provider.name}"
                )
                return self._deduplicate_and_rank(results, max_results, query=query)
            logger.warning(
                f"[SearchOrchestrator] {provider.name} returned no results, trying next..."
            )

        logger.warning("[SearchOrchestrator] All providers failed")
        return []

    def _search_parallel(
        self,
        query: str,
        max_results: int,
        providers: list[SearchProvider],
    ) -> list[SearchResult]:
        """Query all providers in parallel and merge results."""
        import concurrent.futures

        all_results: list[SearchResult] = []

        max_workers = min(len(providers), int(getattr(self, "parallel_max_workers", len(providers))))
        max_workers = max(1, max_workers)
        timeout_s = float(getattr(self, "parallel_timeout_seconds", 30.0))
        timed_out = False
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        futures: dict[concurrent.futures.Future[list[SearchResult]], SearchProvider] = {}
        pending: set[concurrent.futures.Future[list[SearchResult]]] = set()

        try:
            futures = {
                executor.submit(self._call_provider, p, query, max_results): p
                for p in providers
            }
            pending = set(futures)
            deadline = time.monotonic() + max(0.0, timeout_s)

            while pending:
                remaining = max(0.0, deadline - time.monotonic())
                done, pending = concurrent.futures.wait(
                    pending,
                    timeout=remaining,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

                if not done:
                    timed_out = True
                    break

                for future in done:
                    provider = futures[future]
                    try:
                        results = future.result()
                        all_results.extend(results)
                        logger.info(
                            f"[SearchOrchestrator] {provider.name} returned {len(results)} results"
                        )
                    except Exception as e:
                        logger.error(f"[SearchOrchestrator] {provider.name} failed: {e}")
        finally:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

        if timed_out:
            logger.warning("[SearchOrchestrator] parallel search timed out; returning partial results")

        # Deduplicate and rank
        return self._deduplicate_and_rank(all_results, max_results, query=query)

    def _search_round_robin(
        self,
        query: str,
        max_results: int,
        providers: list[SearchProvider],
    ) -> list[SearchResult]:
        """Use round-robin to distribute queries."""
        if not providers:
            return []

        provider_index = self._round_robin_index % len(providers)
        provider = providers[provider_index]
        self._round_robin_index += 1

        results = self._call_provider(provider, query, max_results)
        if results:
            return self._deduplicate_and_rank(results, max_results, query=query)

        # Fallback to the remaining providers without retrying the same one twice.
        fallback_providers = providers[provider_index + 1:] + providers[:provider_index]
        return self._search_fallback(query, max_results, fallback_providers)

    def _search_best_first(
        self,
        query: str,
        max_results: int,
        providers: list[SearchProvider],
    ) -> list[SearchResult]:
        """Use best performing provider first."""
        # Sort by composite score: success_rate * quality / latency
        sorted_providers = sorted(
            providers,
            key=lambda p: (
                p.stats.success_rate *
                p.stats.avg_result_quality *
                (1000 / max(p.stats.avg_latency_ms, 100))
            ),
            reverse=True,
        )

        return self._search_fallback(query, max_results, sorted_providers)

    def _deduplicate_and_rank(
        self,
        results: list[SearchResult],
        max_results: int,
        query: str = "",
    ) -> list[SearchResult]:
        """Deduplicate results by URL and content similarity, then rank."""
        if not results:
            return []

        ranked = sorted(results, key=lambda r: self._ranking_score(r, query), reverse=True)
        seen_urls = set()
        deduplicated: list[SearchResult] = []

        for result in ranked:
            if result.url_hash in seen_urls:
                continue
            if self._is_content_duplicate(result, deduplicated):
                continue
            seen_urls.add(result.url_hash)
            deduplicated.append(result)
            if len(deduplicated) >= max_results:
                break

        return deduplicated[:max_results]

    def _is_content_duplicate(
        self,
        candidate: SearchResult,
        existing_results: list[SearchResult],
    ) -> bool:
        candidate_snippet = (candidate.snippet or "").strip().lower()[:200]
        if not candidate_snippet:
            return False

        for existing in existing_results:
            existing_snippet = (existing.snippet or "").strip().lower()[:200]
            if not existing_snippet:
                continue
            similarity = SequenceMatcher(None, candidate_snippet, existing_snippet).ratio()
            if similarity > self.similarity_threshold:
                return True

        return False

    def _is_time_sensitive_query(self, query: str) -> bool:
        q = (query or "").lower()
        if not q:
            return False

        markers = (
            "latest",
            "today",
            "recent",
            "current",
            "breaking",
            "this week",
            "this month",
            "update",
            "news",
        )
        if any(marker in q for marker in markers):
            return True

        return bool(re.search(r"\b20\d{2}\b", q))

    def _parse_published_date(self, value: str | None) -> datetime | None:
        if not value:
            return None

        text = str(value).strip()
        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in (
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%b-%d",
                "%Y-%B-%d",
                "%Y-%b",
                "%Y-%B",
                "%Y",
            ):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def _freshness_score(self, published_date: str | None) -> float:
        dt = self._parse_published_date(published_date)
        if dt is None:
            return 0.5

        now = datetime.now(UTC)
        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        return math.exp(-age_days / self.freshness_half_life_days)

    def _ranking_score(self, result: SearchResult, query: str) -> float:
        base_score = float(result.score or 0.0)
        if not self.enable_freshness_ranking or not self._is_time_sensitive_query(query):
            return base_score

        freshness = self._freshness_score(result.published_date)
        return (1.0 - self.freshness_weight) * base_score + self.freshness_weight * freshness

    def get_provider_stats(self) -> list[dict[str, Any]]:
        """Get statistics for all providers."""
        return [p.get_stats() for p in self.providers]

    def reset_provider_health(self) -> None:
        """Reset health status for all providers."""
        for provider in self.providers:
            provider.stats.is_healthy = True
            provider.stats.consecutive_failures = 0


# Global orchestrator instance
_global_orchestrator: SearchOrchestrator | None = None


def get_search_orchestrator() -> SearchOrchestrator:
    """Get or create the global search orchestrator."""
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = SearchOrchestrator()
    return _global_orchestrator


def reset_search_orchestrator() -> None:
    """Reset the global search orchestrator (provider health + reliability + stats)."""
    global _global_orchestrator
    _global_orchestrator = None


__all__ = [
    "BingProvider",
    "BraveProvider",
    "DuckDuckGoProvider",
    "ExaProvider",
    "FirecrawlProvider",
    "GoogleCSEProvider",
    "SearchOrchestrator",
    "SerpApiProvider",
    "SerperProvider",
    "TavilyProvider",
    "get_search_orchestrator",
    "reset_search_orchestrator",
]
