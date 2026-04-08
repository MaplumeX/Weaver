
from agent.runtime.deep.support import runtime_support as deep_research_support


def test_search_query_uses_web_search_runtime(monkeypatch):
    calls = {"web_search": 0}

    def fake_run_web_search(*, query, max_results=10, strategy=None, provider_profile=None):
        calls["web_search"] += 1
        assert query == "latest ai news"
        assert max_results == 5
        return [
            {
                "title": "Result",
                "url": "https://example.com/a",
                "summary": "snippet text",
                "snippet": "snippet text",
                "raw_excerpt": "full content",
                "content": "full content",
                "score": 0.72,
                "published_date": "2026-02-05",
                "provider": "duckduckgo",
            }
        ]

    monkeypatch.setattr(deep_research_support, "run_web_search", fake_run_web_search)
    monkeypatch.setattr(deep_research_support.settings, "search_strategy", "fallback")

    results = deep_research_support._search_query("latest ai news", 5, {})

    assert calls["web_search"] == 1
    assert len(results) == 1
    assert results[0]["summary"] == "snippet text"
    assert results[0]["raw_excerpt"] == "full content"


def test_search_query_does_not_add_extra_outer_cache(monkeypatch):
    calls = {"web_search": 0}

    def fake_run_web_search(*, query, max_results=10, strategy=None, provider_profile=None):
        calls["web_search"] += 1
        return [
            {
                "title": "Result",
                "url": f"https://example.com/{calls['web_search']}",
                "summary": "snippet text",
                "snippet": "snippet text",
                "raw_excerpt": "full content",
                "content": "full content",
                "score": 0.72,
                "published_date": "2026-02-05",
                "provider": "duckduckgo",
            }
        ]

    monkeypatch.setattr(deep_research_support, "run_web_search", fake_run_web_search)
    monkeypatch.setattr(deep_research_support.settings, "search_strategy", "fallback")

    first = deep_research_support._search_query("latest ai news", 5, {})
    second = deep_research_support._search_query("latest ai news", 5, {})

    assert calls["web_search"] == 2
    assert first[0]["url"] != second[0]["url"]


def test_search_query_returns_empty_on_web_search_error(monkeypatch):
    calls = {"web_search": 0}

    def fake_run_web_search(*, query, max_results=10, strategy=None, provider_profile=None):
        calls["web_search"] += 1
        raise RuntimeError("search backend unavailable")

    monkeypatch.setattr(deep_research_support, "run_web_search", fake_run_web_search)
    monkeypatch.setattr(deep_research_support.settings, "search_strategy", "fallback")

    results = deep_research_support._search_query("ai chips", 3, {})

    assert calls["web_search"] == 1
    assert results == []
