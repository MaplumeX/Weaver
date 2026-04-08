from datetime import UTC, datetime, timedelta

from tools.search.contracts import SearchResult
from tools.search.orchestrator import SearchOrchestrator


def _days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def test_freshness_ranking_boosts_recent_results_for_time_sensitive_queries(monkeypatch):
    from common.config import settings

    monkeypatch.setattr(settings, "search_enable_freshness_ranking", True, raising=False)
    monkeypatch.setattr(settings, "search_freshness_half_life_days", 30.0, raising=False)
    monkeypatch.setattr(settings, "search_freshness_weight", 0.4, raising=False)

    orchestrator = SearchOrchestrator(providers=[])
    results = [
        SearchResult(
            title="Older high-score",
            url="https://example.com/old",
            snippet="old",
            score=0.9,
            published_date=_days_ago(400),
            provider="test",
        ),
        SearchResult(
            title="Recent medium-score",
            url="https://example.com/new",
            snippet="new",
            score=0.6,
            published_date=_days_ago(1),
            provider="test",
        ),
    ]

    ranked = orchestrator._deduplicate_and_rank(results, max_results=2, query="latest ai news")

    assert ranked[0].url == "https://example.com/new"


def test_non_time_sensitive_queries_keep_relevance_priority(monkeypatch):
    from common.config import settings

    monkeypatch.setattr(settings, "search_enable_freshness_ranking", True, raising=False)
    monkeypatch.setattr(settings, "search_freshness_half_life_days", 30.0, raising=False)
    monkeypatch.setattr(settings, "search_freshness_weight", 0.4, raising=False)

    orchestrator = SearchOrchestrator(providers=[])
    results = [
        SearchResult(
            title="Older high-score",
            url="https://example.com/old",
            snippet="old",
            score=0.9,
            published_date=_days_ago(400),
            provider="test",
        ),
        SearchResult(
            title="Recent medium-score",
            url="https://example.com/new",
            snippet="new",
            score=0.6,
            published_date=_days_ago(1),
            provider="test",
        ),
    ]

    ranked = orchestrator._deduplicate_and_rank(results, max_results=2, query="history of ai")

    assert ranked[0].url == "https://example.com/old"


def test_deduplication_canonicalizes_tracking_urls():
    orchestrator = SearchOrchestrator(providers=[])
    results = [
        SearchResult(
            title="A1",
            url="https://example.com/a?utm_source=x",
            snippet="a1",
            score=0.7,
            provider="test",
        ),
        SearchResult(
            title="A2",
            url="https://example.com/a?utm_source=y",
            snippet="a2",
            score=0.6,
            provider="test",
        ),
    ]

    ranked = orchestrator._deduplicate_and_rank(results, max_results=10, query="ai")

    assert len(ranked) == 1
    assert ranked[0].url == "https://example.com/a"


def test_content_similarity_deduplicates_even_when_under_result_limit():
    orchestrator = SearchOrchestrator(providers=[])
    results = [
        SearchResult(
            title="Higher score",
            url="https://example.com/a",
            snippet="same snippet for duplicate detection",
            score=0.9,
            provider="test",
        ),
        SearchResult(
            title="Lower score",
            url="https://example.com/b",
            snippet="same snippet for duplicate detection",
            score=0.5,
            provider="test",
        ),
    ]

    ranked = orchestrator._deduplicate_and_rank(results, max_results=10, query="ai")

    assert len(ranked) == 1
    assert ranked[0].url == "https://example.com/a"


def test_blank_snippets_do_not_collapse_distinct_results():
    orchestrator = SearchOrchestrator(providers=[])
    results = [
        SearchResult(
            title="A",
            url="https://example.com/a",
            snippet="",
            score=0.8,
            provider="test",
        ),
        SearchResult(
            title="B",
            url="https://example.com/b",
            snippet="",
            score=0.7,
            provider="test",
        ),
    ]

    ranked = orchestrator._deduplicate_and_rank(results, max_results=10, query="ai")

    assert len(ranked) == 2


def test_pubmed_style_dates_participate_in_freshness_ranking(monkeypatch):
    from common.config import settings

    monkeypatch.setattr(settings, "search_enable_freshness_ranking", True, raising=False)
    monkeypatch.setattr(settings, "search_freshness_half_life_days", 30.0, raising=False)
    monkeypatch.setattr(settings, "search_freshness_weight", 0.4, raising=False)

    orchestrator = SearchOrchestrator(providers=[])
    results = [
        SearchResult(
            title="Old",
            url="https://example.com/old",
            snippet="old",
            score=0.9,
            published_date="2024-Jan-01",
            provider="pubmed",
        ),
        SearchResult(
            title="Recent",
            url="https://example.com/new",
            snippet="new",
            score=0.6,
            published_date=_days_ago(1),
            provider="pubmed",
        ),
    ]

    ranked = orchestrator._deduplicate_and_rank(results, max_results=2, query="latest oncology update")

    assert ranked[0].url == "https://example.com/new"
