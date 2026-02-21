import pytest
from httpx import ASGITransport, AsyncClient

import common.session_manager as session_manager_mod
import main


class _FakeCheckpointer:
    def __init__(self, storage):
        self.storage = storage


class _Cfg:
    def __init__(self, thread_id: str):
        self.configurable = {"thread_id": thread_id}

    def __hash__(self) -> int:  # pragma: no cover
        return hash(self.configurable["thread_id"])

    def __eq__(self, other: object) -> bool:  # pragma: no cover
        return isinstance(other, _Cfg) and other.configurable == self.configurable


@pytest.mark.asyncio
async def test_sessions_list_is_filtered_by_principal_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")

    fake_checkpointer = _FakeCheckpointer(
        storage={
            _Cfg("thread_alice"): {
                "channel_values": {
                    "user_id": "alice",
                    "input": "hello",
                    "route": "direct",
                }
            },
            _Cfg("thread_bob"): {
                "channel_values": {
                    "user_id": "bob",
                    "input": "hi",
                    "route": "direct",
                }
            },
        }
    )

    monkeypatch.setattr(main, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(session_manager_mod, "_session_manager", None)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/sessions",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    thread_ids = [s.get("thread_id") for s in payload.get("sessions", [])]
    assert thread_ids == ["thread_alice"]

