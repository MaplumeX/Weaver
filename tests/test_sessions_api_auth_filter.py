import pytest
from httpx import ASGITransport, AsyncClient

import main


class FakeSessionService:
    def __init__(self, sessions):
        self._sessions = sessions

    async def list_sessions(self, *, limit: int, user_id: str | None = None):
        items = list(self._sessions)
        if user_id:
            items = [item for item in items if item.get("user_id") == user_id]
        return items[:limit]


@pytest.mark.asyncio
async def test_sessions_list_is_filtered_by_principal_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(main, "session_service", FakeSessionService([
        {
            "thread_id": "thread_alice",
            "user_id": "alice",
            "title": "hello",
            "summary": "",
            "status": "running",
            "route": "agent",
            "created_at": "2026-04-06T00:00:00Z",
            "updated_at": "2026-04-06T00:00:00Z",
            "is_pinned": False,
            "tags": [],
        },
        {
            "thread_id": "thread_bob",
            "user_id": "bob",
            "title": "hi",
            "summary": "",
            "status": "running",
            "route": "agent",
            "created_at": "2026-04-06T00:00:00Z",
            "updated_at": "2026-04-06T00:00:00Z",
            "is_pinned": False,
            "tags": [],
        },
    ]), raising=False)
    monkeypatch.setattr(main, "checkpointer", None)

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


@pytest.mark.asyncio
async def test_sessions_list_returns_all_sessions_when_internal_auth_disabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")
    monkeypatch.setattr(
        main,
        "session_service",
        FakeSessionService([
            {
                "thread_id": "thread_one",
                "user_id": "alice",
                "title": "hello",
                "summary": "",
                "status": "running",
                "route": "agent",
                "created_at": "2026-04-06T00:00:00Z",
                "updated_at": "2026-04-06T00:00:00Z",
                "is_pinned": False,
                "tags": [],
            },
            {
                "thread_id": "thread_two",
                "user_id": "bob",
                "title": "hi",
                "summary": "",
                "status": "running",
                "route": "agent",
                "created_at": "2026-04-06T00:00:00Z",
                "updated_at": "2026-04-06T00:00:00Z",
                "is_pinned": False,
                "tags": [],
            },
        ]),
        raising=False,
    )
    monkeypatch.setattr(main, "checkpointer", None)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sessions")

    assert resp.status_code == 200
    payload = resp.json()
    assert [s.get("thread_id") for s in payload.get("sessions", [])] == ["thread_one", "thread_two"]
