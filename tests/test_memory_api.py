import pytest
from httpx import ASGITransport, AsyncClient

import main


class FakeMemoryService:
    def __init__(self):
        self.list_calls = []
        self.invalidate_calls = []
        self.delete_calls = []

    def is_configured(self):
        return True

    def list_entries(self, *, user_id: str, limit: int, status=None, memory_type=None):
        self.list_calls.append(
            {
                "user_id": user_id,
                "limit": limit,
                "status": status,
                "memory_type": memory_type,
            }
        )
        return [
            {
                "id": "mem_1",
                "user_id": user_id,
                "memory_type": "preference",
                "content": "用户偏好: 用中文回答",
                "source_kind": "chat",
                "source_thread_id": "thread-1",
                "source_message": "请记住以后请用中文回答",
                "importance": 90,
                "status": "active",
                "retrieval_count": 0,
                "last_retrieved_at": None,
                "invalidated_at": None,
                "invalidation_reason": "",
                "metadata": {},
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:00Z",
            }
        ]

    def debug_context(self, *, user_id: str, query: str, limit: int):
        return {
            "stored": ["用户偏好: 用中文回答"],
            "relevant": ["用户偏好: 用中文回答"],
            "stored_entries": [],
            "relevant_entries": [],
        }

    def list_events(self, *, user_id: str, entry_id=None, limit=50):
        return []

    def invalidate_entry(self, *, user_id: str, entry_id: str, actor_id: str, reason: str):
        self.invalidate_calls.append(
            {
                "user_id": user_id,
                "entry_id": entry_id,
                "actor_id": actor_id,
                "reason": reason,
            }
        )
        return {
            "id": entry_id,
            "user_id": user_id,
            "memory_type": "preference",
            "content": "用户偏好: 用中文回答",
            "source_kind": "chat",
            "source_thread_id": "thread-1",
            "source_message": "请记住以后请用中文回答",
            "importance": 90,
            "status": "invalidated",
            "retrieval_count": 0,
            "last_retrieved_at": None,
            "invalidated_at": "2026-04-07T01:00:00Z",
            "invalidation_reason": reason,
            "metadata": {},
            "created_at": "2026-04-07T00:00:00Z",
            "updated_at": "2026-04-07T01:00:00Z",
        }

    def delete_entry(self, *, user_id: str, entry_id: str, actor_id: str, reason: str):
        self.delete_calls.append(
            {
                "user_id": user_id,
                "entry_id": entry_id,
                "actor_id": actor_id,
                "reason": reason,
            }
        )
        return True


@pytest.mark.asyncio
async def test_memory_entries_are_filtered_by_principal_when_internal_auth_enabled(monkeypatch):
    service = FakeMemoryService()
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(main, "memory_service", service, raising=False)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/memory/entries?user_id=bob",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
        )

    assert resp.status_code == 200
    assert service.list_calls[0]["user_id"] == "alice"


@pytest.mark.asyncio
async def test_memory_invalidate_and_delete_use_principal_identity(monkeypatch):
    service = FakeMemoryService()
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(main, "memory_service", service, raising=False)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        invalidate = await ac.post(
            "/api/memory/entries/mem_1/invalidate",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
            json={"reason": "wrong preference"},
        )
        delete = await ac.delete(
            "/api/memory/entries/mem_1?reason=cleanup",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
        )

    assert invalidate.status_code == 200
    assert delete.status_code == 200
    assert service.invalidate_calls == [
        {
            "user_id": "alice",
            "entry_id": "mem_1",
            "actor_id": "alice",
            "reason": "wrong preference",
        }
    ]
    assert service.delete_calls == [
        {
            "user_id": "alice",
            "entry_id": "mem_1",
            "actor_id": "alice",
            "reason": "cleanup",
        }
    ]
