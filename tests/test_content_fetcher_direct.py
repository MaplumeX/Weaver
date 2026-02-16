import types

from tools.research.content_fetcher import ContentFetcher


def test_content_fetcher_direct_uses_requests(monkeypatch):
    calls = {"get": 0}

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<html><body>Hello</body></html>"
        text = "<html><body>Hello</body></html>"

    def fake_get(url, timeout=None, headers=None):
        calls["get"] += 1
        return FakeResp()

    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    f = ContentFetcher()
    page = f.fetch("https://example.com/")
    assert page.method == "direct_http"
    assert "Hello" in (page.text or page.markdown or "")
    assert calls["get"] == 1
