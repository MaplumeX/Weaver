import json
from concurrent.futures import TimeoutError as FutureTimeout

import main


def _receive_json_with_timeout(ws, *, timeout_s: float = 1.5):
    fut = ws.portal.start_task_soon(ws._send_rx.receive)
    try:
        message = fut.result(timeout=timeout_s)
    except FutureTimeout:
        try:
            ws.close()
        except Exception:
            pass
        try:
            fut.result(timeout=2.0)
        except Exception:
            pass
        raise AssertionError("Timed out waiting for WebSocket message")

    ws._raise_on_close(message)
    return json.loads(message["text"])


class _DummyPage:
    def __init__(self):
        self.url = "about:blank"

    def title(self):
        return "Dummy"

    def set_content(self, _html):
        return None

    def goto(self, url, **_kwargs):
        self.url = str(url)


class _DummyBrowserSession:
    def __init__(self):
        self.page = _DummyPage()
        self.meta: dict[str, str] = {"url": self.page.url, "title": self.page.title()}

    def get_page(self):
        return self.page

    def start_screencast(self, **_kwargs):
        return True

    def stop_screencast(self):
        return None

    def set_page_meta(self, *, url=None, title=None):
        if isinstance(url, str) and url.strip():
            self.meta["url"] = url.strip()
        if isinstance(title, str) and title.strip():
            self.meta["title"] = title.strip()


class _MetaFrameSandboxBrowserSessions:
    def __init__(self):
        self.session = _DummyBrowserSession()
        self._frame_id = 0

    def get(self, _thread_id: str):
        return self.session

    async def run_async(self, thread_id: str, fn, *args, **kwargs):
        _ = thread_id
        return fn(*args, **kwargs)

    def peek_screencast_frame(self, _thread_id: str):
        self._frame_id += 1
        return {
            "frame_id": self._frame_id,
            "data": "ZmFrZV9qcGVn",
            "timestamp": 123.456,
            "metadata": dict(self.session.meta),
        }


def test_browser_stream_ws_updates_cdp_frame_metadata_after_navigate(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")
    monkeypatch.setitem(main.settings.__dict__, "e2b_api_key", "e2b_test_key")
    monkeypatch.setitem(main.settings.__dict__, "sandbox_template_browser", "sandbox_template_test_browser")

    dummy = _MetaFrameSandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_cdp_metadata_updates"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws, timeout_s=1.0)
        assert initial["type"] == "status"

        ws.send_json({"action": "start", "quality": 70, "max_fps": 10})
        started = _receive_json_with_timeout(ws, timeout_s=1.5)
        assert started["type"] == "status"
        assert started["message"] == "Screencast started"

        frame0 = _receive_json_with_timeout(ws, timeout_s=0.5)
        assert frame0["type"] == "frame"
        assert frame0.get("metadata", {}).get("url") == "about:blank"

        ws.send_json({"action": "navigate", "url": "https://example.com", "id": "n1"})

        ack = None
        for _ in range(10):
            msg = _receive_json_with_timeout(ws, timeout_s=0.5)
            if msg.get("type") == "ack" and msg.get("action") == "navigate":
                ack = msg
                break
        assert ack is not None
        assert ack["ok"] is True
        assert ack["id"] == "n1"

        updated = None
        for _ in range(20):
            msg = _receive_json_with_timeout(ws, timeout_s=0.5)
            if msg.get("type") != "frame":
                continue
            if msg.get("metadata", {}).get("url") == "https://example.com":
                updated = msg
                break

    assert updated is not None

