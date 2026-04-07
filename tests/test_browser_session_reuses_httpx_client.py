from __future__ import annotations

from urllib.parse import urlparse


class _FakeResponse:
    def __init__(self, url: str):
        self._url = url
        self.text = "<html><title>t</title><body>Hello</body></html>"

    @property
    def url(self) -> str:
        # Match httpx.Response.url-ish behavior (stringified in the code).
        return self._url

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    instances = 0

    def __init__(self, *args, **kwargs):
        _FakeClient.instances += 1
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self) -> None:
        return None

    def get(self, url: str):
        parsed = urlparse(url)
        assert parsed.scheme in {"http", "https"}
        return _FakeResponse(url)


def test_browser_session_reuses_httpx_client(monkeypatch):
    from tools.browser import browser_session as mod

    monkeypatch.setattr(mod.httpx, "Client", _FakeClient)

    session = mod.BrowserSession(timeout_s=1.0)
    session.navigate("https://example.com")
    session.navigate("https://example.org")

    assert _FakeClient.instances == 1

