from importlib import import_module

from tools.search.contracts import SearchResult
from tools.search.web_search import infer_search_source_label, run_web_search
from tools.search.web_search import web_search as web_search_tool

web_search_module = import_module("tools.search.web_search")


def test_run_web_search_returns_public_result_schema(monkeypatch):
    class DummyOrchestrator:
        def search(self, *, query, max_results=10, strategy=None, provider_profile=None):
            assert query == "schema test"
            assert max_results == 2
            return [
                SearchResult(
                    title="Result",
                    url="https://example.com",
                    snippet="short snippet",
                    content="full content",
                    score=0.8,
                    published_date="2026-04-08",
                    provider="serper",
                )
            ]

    monkeypatch.setattr(web_search_module, "get_search_orchestrator", lambda: DummyOrchestrator())

    results = run_web_search(query="schema test", max_results=2)

    assert results == [
        {
            "title": "Result",
            "url": "https://example.com/",
            "summary": "short snippet",
            "snippet": "short snippet",
            "raw_excerpt": "full content",
            "content": "full content",
            "score": 0.8,
            "published_date": "2026-04-08",
            "provider": "serper",
        }
    ]


def test_run_web_search_uses_configured_provider_preference(monkeypatch):
    captured = {}

    class DummyOrchestrator:
        def search(self, *, query, max_results=10, strategy=None, provider_profile=None):
            captured["query"] = query
            captured["max_results"] = max_results
            captured["strategy"] = strategy
            captured["provider_profile"] = provider_profile
            return [
                SearchResult(
                    title="Result",
                    url="https://example.com",
                    snippet="ok",
                    content="full",
                    provider="tavily",
                )
            ]

    monkeypatch.setattr(web_search_module, "get_search_orchestrator", lambda: DummyOrchestrator())
    monkeypatch.setattr(web_search_module.settings, "search_strategy", "parallel")
    monkeypatch.setattr(web_search_module.settings, "search_engines", "serper, tavily")

    results = run_web_search(query="OpenAI", max_results=4)

    assert captured["query"] == "OpenAI"
    assert captured["max_results"] == 4
    assert captured["strategy"].value == "parallel"
    assert captured["provider_profile"] == ["serper", "tavily"]
    assert results[0]["summary"] == "ok"
    assert results[0]["raw_excerpt"] == "full"


def test_web_search_tool_invokes_unified_runtime(monkeypatch):
    monkeypatch.setattr(
        web_search_module,
        "run_web_search",
        lambda **kwargs: [
            {
                "title": "Result",
                "url": "https://example.com",
                "summary": "summary",
                "snippet": "summary",
                "raw_excerpt": "full",
                "content": "full",
                "score": 0.5,
                "published_date": None,
                "provider": "duckduckgo",
            }
        ],
    )

    results = web_search_tool.invoke({"query": "OpenAI", "max_results": 2})

    assert len(results) == 1
    assert results[0]["provider"] == "duckduckgo"


def test_infer_search_source_label_handles_mixed_providers():
    assert infer_search_source_label(
        [{"provider": "tavily"}, {"provider": "serper"}]
    ) == "web_search"
    assert infer_search_source_label([{"provider": "tavily"}]) == "tavily"
