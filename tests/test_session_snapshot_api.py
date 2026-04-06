import pytest
from httpx import ASGITransport, AsyncClient

import main


class FakeSessionService:
    def __init__(self, *, snapshot=None, updated=None):
        self._snapshot = snapshot
        self._updated = updated

    async def load_snapshot(self, thread_id: str):
        return self._snapshot

    async def update_session_metadata(self, thread_id: str, payload: dict[str, object]):
        return self._updated

    async def get_session(self, thread_id: str):
        return self._updated

    async def delete_session(self, thread_id: str):
        return {"success": True, "message": f"Session {thread_id} deleted", "checkpoint_cleanup_pending": False}


@pytest.mark.asyncio
async def test_session_snapshot_returns_messages_and_resume_flags(monkeypatch):
    fake_service = FakeSessionService(
        snapshot={
            "session": {
                "thread_id": "thread-api",
                "title": "hello",
                "status": "interrupted",
                "route": "agent",
                "created_at": "2026-04-06T00:00:00Z",
                "updated_at": "2026-04-06T00:01:00Z",
            },
            "messages": [{"id": "m1", "role": "user", "content": "hello"}],
            "pending_interrupt": {"kind": "scope_review"},
            "can_resume": True,
        }
    )
    monkeypatch.setattr(main, "session_service", fake_service, raising=False)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sessions/thread-api/snapshot")

    assert resp.status_code == 200
    data = resp.json()
    assert data["can_resume"] is True
    assert data["messages"][0]["content"] == "hello"


@pytest.mark.asyncio
async def test_patch_session_updates_title_and_pin(monkeypatch):
    fake_service = FakeSessionService(
        updated={
            "thread_id": "thread-api",
            "title": "Renamed",
            "summary": "",
            "status": "running",
            "route": "agent",
            "is_pinned": True,
            "tags": [],
            "created_at": "2026-04-06T00:00:00Z",
            "updated_at": "2026-04-06T00:01:00Z",
        }
    )
    monkeypatch.setattr(main, "session_service", fake_service, raising=False)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch("/api/sessions/thread-api", json={"title": "Renamed", "is_pinned": True})

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Renamed"
    assert data["is_pinned"] is True


@pytest.mark.asyncio
async def test_get_session_detail_uses_session_service(monkeypatch):
    fake_service = FakeSessionService(
        updated={
            "thread_id": "thread-api",
            "user_id": "alice",
            "title": "Renamed",
            "summary": "",
            "status": "running",
            "route": "agent",
            "is_pinned": True,
            "tags": [],
            "created_at": "2026-04-06T00:00:00Z",
            "updated_at": "2026-04-06T00:01:00Z",
        }
    )
    monkeypatch.setattr(main, "session_service", fake_service, raising=False)
    monkeypatch.setattr(main, "checkpointer", None)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sessions/thread-api")

    assert resp.status_code == 200
    assert resp.json()["topic"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_session_uses_session_service(monkeypatch):
    fake_service = FakeSessionService()
    monkeypatch.setattr(main, "session_service", fake_service, raising=False)
    monkeypatch.setattr(main, "checkpointer", None)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.delete("/api/sessions/thread-api")

    assert resp.status_code == 200
    assert resp.json()["success"] is True
