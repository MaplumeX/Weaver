import types

from tools.research.content_fetcher import ContentFetcher


def test_content_fetcher_extracts_title_and_sets_retrieved_at(monkeypatch):
    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod.settings, "research_fetch_cache_ttl_s", 0.0, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_mode", "off", raising=False)

    html = "<html><head><title>My Page</title></head><body><h1>Hello</h1></body></html>"

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
    assert page.title == "My Page"
    assert isinstance(page.retrieved_at, str)
    assert len(page.retrieved_at) >= 10
