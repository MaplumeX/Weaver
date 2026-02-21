import pytest
from httpx import ASGITransport, AsyncClient

import main


class _FakeTrigger:
    require_auth = False


class _FakeTriggerManager:
    def __init__(self):
        self.calls = 0

    def get_trigger(self, trigger_id: str):
        return _FakeTrigger()

    async def handle_webhook(
        self,
        *,
        trigger_id: str,
        method: str,
        body=None,
        query_params=None,
        headers=None,
        auth_header=None,
    ):
        self.calls += 1
        return {"success": True, "status_code": 200}


@pytest.mark.asyncio
async def test_webhook_requires_auth_when_internal_api_key_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")

    manager = _FakeTriggerManager()
    monkeypatch.setattr(main, "get_trigger_manager", lambda: manager)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/webhook/trigger123", json={"hello": "world"})
        assert resp.status_code == 401

        resp2 = await ac.post(
            "/api/webhook/trigger123",
            headers={"Authorization": "Bearer test-key"},
            json={"hello": "world"},
        )
        assert resp2.status_code == 200

