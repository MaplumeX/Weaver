import types

import pytest

from tools.research.content_fetcher import ContentFetcher


def test_content_fetcher_uses_crawler_render_when_direct_text_too_small(monkeypatch):
    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod.settings, "research_fetch_cache_ttl_s", 0.0, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_mode", "auto", raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_min_chars", 10, raising=False)

    calls = {"direct": 0, "reader": 0}

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        content = b"<html><body><div id='app'></div></body></html>"
        text = "<html><body><div id='app'></div></body></html>"

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    def fake_get(url, timeout=None, headers=None, **kwargs):
        if "r.jina.ai" in url:
            calls["reader"] += 1
            raise AssertionError("reader should not be called when render succeeds")
        calls["direct"] += 1
        return FakeResp()

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    import tools.crawl.crawler as crawler

    def fake_crawl_urls(urls, timeout=10):
        assert urls == ["https://example.com/"]
        return [{"url": urls[0], "content": "Rendered content"}]

    monkeypatch.setattr(crawler, "crawl_urls", fake_crawl_urls)

    page = ContentFetcher().fetch("https://example.com/?utm_source=x")
    assert page.method == "render_crawler"
    assert page.text == "Rendered content"
    assert calls["direct"] == 1
    assert calls["reader"] == 0


@pytest.mark.parametrize(
    "html,expected_text_snippet",
    [
        ("<html><body><h1>Title</h1><p>Hello <b>world</b></p></body></html>", "Title Hello world"),
        ("<html><body><p>Hello</p></body></html>", "Hello"),
    ],
)
def test_content_fetcher_extracts_markdown_for_html(monkeypatch, html, expected_text_snippet):
    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod.settings, "research_fetch_cache_ttl_s", 0.0, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_mode", "off", raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_extract_markdown", True, raising=False)

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        content = html.encode("utf-8")
        text = html

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    def fake_get(url, timeout=None, headers=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    page = ContentFetcher().fetch("https://example.com/")
    assert expected_text_snippet in (page.text or "")
    assert page.markdown
    assert "hello" in page.markdown.lower()
