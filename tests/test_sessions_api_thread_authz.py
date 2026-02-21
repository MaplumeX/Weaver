import pytest
from httpx import ASGITransport, AsyncClient

import common.session_manager as session_manager_mod
import main


class _CheckpointTuple:
    def __init__(self, state):
        self.checkpoint = {"channel_values": state}
        self.metadata = {"created_at": "2026-02-21T00:00:00Z"}
        self.parent_config = None


class _FakeCheckpointer:
    def __init__(self, by_thread_id):
        self._by_thread_id = by_thread_id
        self.storage = {}
        for thread_id, state in by_thread_id.items():
            cfg = _Cfg(thread_id)
            self.storage[cfg] = {"channel_values": state}

    def get_tuple(self, config):
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        if not thread_id or thread_id not in self._by_thread_id:
            return None
        return _CheckpointTuple(self._by_thread_id[thread_id])


class _Cfg:
    def __init__(self, thread_id: str):
        self.configurable = {"thread_id": thread_id}

    def __hash__(self) -> int:  # pragma: no cover
        return hash(self.configurable["thread_id"])

    def __eq__(self, other: object) -> bool:  # pragma: no cover
        return isinstance(other, _Cfg) and other.configurable == self.configurable


@pytest.mark.asyncio
async def test_session_detail_forbidden_for_other_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")

    fake_checkpointer = _FakeCheckpointer(
        by_thread_id={
            "thread_alice": {"user_id": "alice", "input": "hello", "route": "direct"},
        }
    )
    monkeypatch.setattr(main, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(session_manager_mod, "_session_manager", None)

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
    monkeypatch.setattr(session_manager_mod, "_session_manager", None)

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
    monkeypatch.setattr(session_manager_mod, "_session_manager", None)

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
