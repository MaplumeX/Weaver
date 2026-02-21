import pytest
from httpx import ASGITransport, AsyncClient

import main


class _CheckpointTuple:
    def __init__(self, state):
        self.checkpoint = {"channel_values": state}
        self.metadata = {"created_at": "2026-02-21T00:00:00Z"}
        self.parent_config = None


class _FakeCheckpointer:
    def __init__(self, by_thread_id):
        self._by_thread_id = by_thread_id

    def get_tuple(self, config):
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        if not thread_id or thread_id not in self._by_thread_id:
            return None
        return _CheckpointTuple(self._by_thread_id[thread_id])


@pytest.mark.asyncio
async def test_browser_info_forbidden_for_other_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")

    monkeypatch.setattr(
        main,
        "checkpointer",
        _FakeCheckpointer(by_thread_id={"thread_alice": {"user_id": "alice"}}),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/browser/thread_alice/info",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "bob",
            },
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_browser_screenshot_forbidden_for_other_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")

    monkeypatch.setattr(
        main,
        "checkpointer",
        _FakeCheckpointer(by_thread_id={"thread_alice": {"user_id": "alice"}}),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/browser/thread_alice/screenshot",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "bob",
            },
        )

    assert resp.status_code == 403

