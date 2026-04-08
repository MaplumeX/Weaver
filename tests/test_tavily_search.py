import sys
import types
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.search import providers


def test_tavily_api_search_only_summarizes_top_result(monkeypatch):
    class _DummyClient:
        def __init__(self, api_key):
            self.api_key = api_key

        def search(self, **kwargs):
            return {
                "results": [
                    {
                        "title": "Result 1",
                        "url": "https://example.com/1",
                        "content": "Snippet 1",
                        "raw_content": "Raw content 1",
                        "score": 0.9,
                    },
                    {
                        "title": "Result 2",
                        "url": "https://example.com/2",
                        "content": "Snippet 2",
                        "raw_content": "Raw content 2",
                        "score": 0.8,
                    },
                    {
                        "title": "Result 3",
                        "url": "https://example.com/3",
                        "content": "Snippet 3",
                        "raw_content": "Raw content 3",
                        "score": 0.7,
                    },
                ]
            }

    summarize_calls = []

    monkeypatch.setitem(sys.modules, "tavily", types.SimpleNamespace(TavilyClient=_DummyClient))
    monkeypatch.setattr(providers.settings, "tavily_api_key", "test-key")
    monkeypatch.setattr(
        providers,
        "_summarize_content",
        lambda raw: summarize_calls.append(raw) or f"summary:{raw}",
    )

    results = providers.tavily_api_search("capital of France", max_results=3)

    assert summarize_calls == ["Raw content 1"]
    assert results[0]["summary"] == "summary:Raw content 1"
    assert results[1]["summary"] == "Snippet 2"
    assert results[2]["summary"] == "Snippet 3"
