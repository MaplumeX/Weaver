from __future__ import annotations

from types import SimpleNamespace

import pytest

from common.session_service import SessionService


@pytest.mark.asyncio
async def test_load_snapshot_merges_store_messages_with_checkpoint_interrupts() -> None:
    class FakeStore:
        async def get_snapshot(self, thread_id: str):
            return {
                "session": {"thread_id": thread_id, "title": "hello", "status": "interrupted"},
                "messages": [{"id": "m1", "role": "user", "content": "hello"}],
            }

    class FakeCheckpointer:
        async def aget_tuple(self, config):
            return SimpleNamespace(
                checkpoint={"channel_values": {"__interrupt__": [{"kind": "scope_review"}]}},
                metadata={},
                parent_config=None,
                pending_writes=[],
            )

    service = SessionService(store=FakeStore(), checkpointer=FakeCheckpointer())
    snapshot = await service.load_snapshot("thread-9")

    assert snapshot["session"]["thread_id"] == "thread-9"
    assert snapshot["can_resume"] is True
    assert snapshot["pending_interrupt"] == [{"kind": "scope_review"}]


@pytest.mark.asyncio
async def test_update_session_metadata_delegates_to_store() -> None:
    captured: dict[str, object] = {}

    class FakeStore:
        async def update_session_metadata(self, thread_id: str, updates: dict[str, object]):
            captured["thread_id"] = thread_id
            captured["updates"] = updates
            return {"thread_id": thread_id, **updates}

    service = SessionService(store=FakeStore(), checkpointer=None)
    updated = await service.update_session_metadata("thread-10", {"title": "Renamed"})

    assert captured["thread_id"] == "thread-10"
    assert captured["updates"] == {"title": "Renamed"}
    assert updated["title"] == "Renamed"


@pytest.mark.asyncio
async def test_list_sessions_without_user_filter_delegates_to_store() -> None:
    captured: dict[str, object] = {}

    class FakeStore:
        async def list_sessions(self, *, user_id=None, limit: int):
            captured["user_id"] = user_id
            captured["limit"] = limit
            return [{"thread_id": "thread-1"}]

    service = SessionService(store=FakeStore(), checkpointer=None)
    sessions = await service.list_sessions(limit=10, user_id=None)

    assert captured["user_id"] is None
    assert captured["limit"] == 10
    assert sessions == [{"thread_id": "thread-1"}]


@pytest.mark.asyncio
async def test_start_session_run_reuses_existing_session_and_appends_user_message() -> None:
    captured: list[tuple[str, object]] = []

    class FakeStore:
        async def get_session(self, thread_id: str):
            return {"thread_id": thread_id, "title": "Existing"}

        async def create_session(self, **payload):
            captured.append(("create", payload))

        async def update_session_metadata(self, thread_id: str, updates: dict[str, object]):
            captured.append(("update", {"thread_id": thread_id, "updates": updates}))
            return {"thread_id": thread_id, **updates}

        async def append_message(self, **payload):
            captured.append(("append", payload))

    service = SessionService(store=FakeStore(), checkpointer=None)
    await service.start_session_run(
        thread_id="thread-existing",
        user_id="alice",
        route="agent",
        initial_user_message="follow up",
    )

    assert not any(kind == "create" for kind, _ in captured)
    assert any(kind == "update" for kind, _ in captured)
    assert any(kind == "append" for kind, _ in captured)
