import pytest

from common.session_service import SessionService


class FakeSessionStore:
    def __init__(self):
        self.sessions = {}
        self.messages = []

    async def get_snapshot(self, thread_id: str):
        return {}

    async def update_session_metadata(self, thread_id: str, updates: dict):
        session = self.sessions.setdefault(thread_id, {"thread_id": thread_id})
        session.update(updates)
        return session

    async def list_sessions(self, *, user_id=None, limit=50):
        return []

    async def get_session(self, thread_id: str):
        return self.sessions.get(thread_id)

    async def create_session(self, *, thread_id: str, user_id: str, title: str, route: str, status: str):
        self.sessions[thread_id] = {
            "thread_id": thread_id,
            "user_id": user_id,
            "title": title,
            "route": route,
            "status": status,
        }

    async def append_message(self, *, thread_id: str, role: str, content: str, created_at: str, **payload):
        self.messages.append(
            {
                "thread_id": thread_id,
                "role": role,
                "content": content,
                "created_at": created_at,
                **payload,
            }
        )

    async def delete_session(self, thread_id: str):
        self.sessions.pop(thread_id, None)


class FakeMemoryService:
    def __init__(self):
        self.calls = []

    def ingest_user_message(self, **kwargs):
        self.calls.append(kwargs)
        return []


@pytest.mark.asyncio
async def test_start_session_run_ingests_user_memory_through_memory_service():
    store = FakeSessionStore()
    memory_service = FakeMemoryService()
    service = SessionService(store=store, checkpointer=None, memory_service=memory_service)

    await service.start_session_run(
        thread_id="thread-1",
        user_id="alice",
        route="agent",
        initial_user_message="请记住我喜欢简洁回答",
    )

    assert len(memory_service.calls) == 1
    assert memory_service.calls[0] == {
        "user_id": "alice",
        "text": "请记住我喜欢简洁回答",
        "source_kind": "chat",
        "thread_id": "thread-1",
    }


@pytest.mark.asyncio
async def test_append_user_message_uses_session_owner_for_memory_ingest():
    store = FakeSessionStore()
    store.sessions["thread-1"] = {
        "thread_id": "thread-1",
        "user_id": "alice",
        "title": "hello",
        "route": "agent",
        "status": "running",
    }
    memory_service = FakeMemoryService()
    service = SessionService(store=store, checkpointer=None, memory_service=memory_service)

    await service.append_user_message(
        thread_id="thread-1",
        content="请记住以后请用中文回答",
    )

    assert len(memory_service.calls) == 1
    assert memory_service.calls[0] == {
        "user_id": "alice",
        "text": "请记住以后请用中文回答",
        "source_kind": "chat_resume",
        "thread_id": "thread-1",
    }
