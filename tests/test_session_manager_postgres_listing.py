from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.base import CheckpointTuple

import common.session_manager as session_manager_mod
import main
from common.session_manager import SessionManager


def _checkpoint_tuple(
    *,
    thread_id: str,
    checkpoint_id: str,
    state: dict,
    ts: str,
) -> CheckpointTuple:
    return CheckpointTuple(
        config={
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
                "checkpoint_id": checkpoint_id,
            }
        },
        checkpoint={
            "v": 1,
            "id": checkpoint_id,
            "ts": ts,
            "channel_values": state,
            "channel_versions": {},
            "versions_seen": {},
            "updated_channels": [],
        },
        metadata={},
        parent_config=None,
        pending_writes=None,
    )


class _FakePostgresCheckpointer:
    def __init__(self, checkpoints):
        self._checkpoints = list(checkpoints)
        self.last_alist_config = object()

    async def alist(self, config, **kwargs):
        self.last_alist_config = config
        for checkpoint in self._checkpoints:
            yield checkpoint


@pytest.mark.asyncio
async def test_alist_sessions_supports_langgraph_checkpoint_tuple_shape():
    fake_checkpointer = _FakePostgresCheckpointer(
        checkpoints=[
            _checkpoint_tuple(
                thread_id="thread_alice",
                checkpoint_id="cp-003",
                state={"user_id": "alice", "input": "latest alice", "route": "agent"},
                ts="2026-04-04T10:00:00Z",
            ),
            _checkpoint_tuple(
                thread_id="thread_alice",
                checkpoint_id="cp-002",
                state={"user_id": "alice", "input": "older alice", "route": "agent"},
                ts="2026-04-04T09:00:00Z",
            ),
            _checkpoint_tuple(
                thread_id="thread_bob",
                checkpoint_id="cp-001",
                state={"user_id": "bob", "input": "latest bob", "route": "deep"},
                ts="2026-04-04T08:00:00Z",
            ),
        ]
    )

    manager = SessionManager(fake_checkpointer)
    sessions = await manager.alist_sessions(limit=10)

    assert fake_checkpointer.last_alist_config is None
    assert [session.thread_id for session in sessions] == ["thread_alice", "thread_bob"]
    assert sessions[0].topic == "latest alice"
    assert sessions[0].created_at == "2026-04-04T10:00:00Z"
    assert sessions[0].updated_at == "2026-04-04T10:00:00Z"


@pytest.mark.asyncio
async def test_sessions_api_lists_postgres_backed_sessions(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    fake_checkpointer = _FakePostgresCheckpointer(
        checkpoints=[
            _checkpoint_tuple(
                thread_id="thread_postgres",
                checkpoint_id="cp-100",
                state={"user_id": "alice", "input": "postgres session", "route": "agent"},
                ts="2026-04-04T12:00:00Z",
            )
        ]
    )

    monkeypatch.setattr(main, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(session_manager_mod, "_session_manager", None)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["sessions"][0]["thread_id"] == "thread_postgres"
    assert payload["sessions"][0]["topic"] == "postgres session"
    assert payload["sessions"][0]["created_at"] == "2026-04-04T12:00:00Z"
