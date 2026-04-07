from common.memory_service import MemoryService


class FakeMemoryStore:
    def __init__(self, entries=None):
        self.entries = list(entries or [])
        self.events = []
        self.touched_ids = []

    def upsert_entry(self, **kwargs):
        entry = {
            "id": f"mem_{len(self.entries) + 1}",
            "user_id": kwargs["user_id"],
            "memory_type": kwargs["memory_type"],
            "content": kwargs["content"],
            "normalized_key": kwargs["normalized_key"],
            "source_kind": kwargs["source_kind"],
            "source_thread_id": kwargs.get("source_thread_id", ""),
            "source_message": kwargs.get("source_message", ""),
            "importance": kwargs.get("importance", 50),
            "status": "active",
            "retrieval_count": 0,
            "last_retrieved_at": None,
            "invalidated_at": None,
            "invalidation_reason": "",
            "metadata": kwargs.get("metadata", {}),
            "created_at": "2026-04-07T00:00:00Z",
            "updated_at": "2026-04-07T00:00:00Z",
        }
        self.entries.append(entry)
        return entry

    def record_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs

    def list_entries(self, *, user_id: str, limit: int = 50, status=None, memory_type=None):
        items = [entry for entry in self.entries if entry["user_id"] == user_id]
        if status:
            items = [entry for entry in items if entry["status"] == status]
        if memory_type:
            items = [entry for entry in items if entry["memory_type"] == memory_type]
        return items[:limit]

    def touch_entries(self, *, entry_ids):
        self.touched_ids = list(entry_ids)


def test_ingest_user_message_requires_explicit_memory_intent():
    store = FakeMemoryStore()
    service = MemoryService(store=store)

    created = service.ingest_user_message(
        user_id="alice",
        text="请记住我喜欢简洁回答",
        source_kind="chat",
        thread_id="thread-1",
    )

    assert len(created) == 1
    assert created[0]["memory_type"] == "preference"
    assert created[0]["content"] == "用户偏好: 我喜欢简洁回答"
    assert created[0]["source_thread_id"] == "thread-1"

    assert service.ingest_user_message(
        user_id="alice",
        text="我喜欢简洁回答",
        source_kind="chat",
    ) == []


def test_ingest_user_message_rejects_ephemeral_task_state():
    store = FakeMemoryStore()
    service = MemoryService(store=store)

    created = service.ingest_user_message(
        user_id="alice",
        text="记住这次任务先改 main.py",
        source_kind="chat",
    )

    assert created == []
    assert store.entries == []


def test_debug_context_returns_structured_matches_and_touches_entries():
    store = FakeMemoryStore(
        entries=[
            {
                "id": "mem_1",
                "user_id": "alice",
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
            },
            {
                "id": "mem_2",
                "user_id": "alice",
                "memory_type": "user_fact",
                "content": "用户信息: 我主要用 FastAPI",
                "source_kind": "chat",
                "source_thread_id": "thread-2",
                "source_message": "请记住我主要用 FastAPI",
                "importance": 80,
                "status": "active",
                "retrieval_count": 0,
                "last_retrieved_at": None,
                "invalidated_at": None,
                "invalidation_reason": "",
                "metadata": {},
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:00Z",
            },
        ]
    )
    service = MemoryService(store=store)

    context = service.debug_context(user_id="alice", query="用中文回答", limit=2)

    assert context["stored"] == ["用户偏好: 用中文回答", "用户信息: 我主要用 FastAPI"]
    assert context["relevant"][0] == "用户偏好: 用中文回答"
    assert "matched query tokens" in context["relevant_entries"][0]["reason"]
    assert set(store.touched_ids) == {"mem_1", "mem_2"}
