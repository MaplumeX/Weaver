import types

from tools.research.content_fetcher import ContentFetcher


def test_content_fetcher_falls_back_to_reader(monkeypatch):
    class FakeRespFail:
        status_code = 403
        headers = {"content-type": "text/html"}
        content = b""
        text = ""

    class FakeRespReader:
        status_code = 200
        headers = {"content-type": "text/plain"}
        content = b"Reader text"
        text = "Reader text"

    calls = {"urls": []}

    def fake_get(url, timeout=None, headers=None, **kwargs):
        calls["urls"].append(url)
        if "r.jina.ai" in url:
            return FakeRespReader()
        return FakeRespFail()

    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    f = ContentFetcher(reader_mode="public", reader_public_base="https://r.jina.ai", reader_self_hosted_base="")
    page = f.fetch("https://example.com/")
    assert page.method == "reader_public"
    assert page.text == "Reader text"
    assert any("r.jina.ai" in u for u in calls["urls"])
