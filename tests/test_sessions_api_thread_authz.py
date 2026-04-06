import pytest
from httpx import ASGITransport, AsyncClient

import main


class FakeSessionService:
    def __init__(self, session_by_thread_id):
        self._session_by_thread_id = session_by_thread_id

    async def get_session(self, thread_id: str):
        return self._session_by_thread_id.get(thread_id)


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
async def test_session_detail_forbidden_for_other_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(
        main,
        "session_service",
        FakeSessionService(
            {
                "thread_alice": {
                    "thread_id": "thread_alice",
                    "user_id": "alice",
                    "title": "hello",
                    "summary": "",
                    "status": "running",
                    "route": "agent",
                    "created_at": "2026-04-06T00:00:00Z",
                    "updated_at": "2026-04-06T00:00:00Z",
                }
            }
        ),
        raising=False,
    )
    monkeypatch.setattr(main, "checkpointer", _FakeCheckpointer({"thread_alice": {"user_id": "alice"}}))

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        forbidden = await ac.get(
            "/api/sessions/thread_alice",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "bob",
            },
        )

    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_session_state_forbidden_for_other_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")

    fake_checkpointer = _FakeCheckpointer(
        by_thread_id={
            "thread_alice": {"user_id": "alice", "input": "hello", "route": "direct"},
        }
    )
    monkeypatch.setattr(main, "checkpointer", fake_checkpointer)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        forbidden = await ac.get(
            "/api/sessions/thread_alice/state",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "bob",
            },
        )

    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_session_evidence_forbidden_for_other_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")

    fake_checkpointer = _FakeCheckpointer(
        by_thread_id={
            "thread_alice": {"user_id": "alice", "input": "hello", "route": "direct"},
        }
    )
    monkeypatch.setattr(main, "checkpointer", fake_checkpointer)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        forbidden = await ac.get(
            "/api/sessions/thread_alice/evidence",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "bob",
            },
        )

    assert forbidden.status_code == 403
