from __future__ import annotations

from types import SimpleNamespace

import pytest

from common.session_service import SessionService
from common.session_store import SessionStore
from tests.persistence_fixtures import build_fake_pg_conn


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
async def test_list_messages_falls_back_to_snapshot_when_store_has_no_direct_api() -> None:
    class FakeStore:
        async def get_snapshot(self, thread_id: str):
            return {
                "session": {"thread_id": thread_id, "title": "hello", "status": "running"},
                "messages": [
                    {"id": "m1", "role": "user", "content": "hello"},
                    {"id": "m2", "role": "assistant", "content": "world"},
                    {"id": "m3", "role": "user", "content": "follow up"},
                ],
            }

    service = SessionService(store=FakeStore(), checkpointer=None)

    messages = await service.list_messages("thread-11", limit=2)

    assert [message["content"] for message in messages] == ["world", "follow up"]


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


@pytest.mark.asyncio
async def test_finalize_assistant_message_persists_process_payload_in_snapshot() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    await store.create_session(
        thread_id="thread-process",
        user_id="alice",
        title="Process session",
        route="agent",
        status="running",
    )
    service = SessionService(store=store, checkpointer=None)

    sources = [{"title": "Doc", "url": "https://example.com/doc"}]
    tool_invocations = [
        {
            "toolName": "search_docs",
            "toolCallId": "tool-1",
            "state": "completed",
            "args": {"query": "session persistence"},
            "result": {"hits": 2},
        }
    ]
    process_events = [
        {
            "id": "evt-1",
            "type": "thinking",
            "timestamp": "2026-04-06T08:01:00Z",
            "data": {"text": "Analyzing persistence flow"},
        },
        {
            "id": "evt-2",
            "type": "done",
            "timestamp": "2026-04-06T08:01:27Z",
            "data": {"metrics": {"duration_ms": 27000}},
        },
    ]
    metrics = {"duration_ms": 27000, "run_id": "run-27"}

    await service.finalize_assistant_message(
        thread_id="thread-process",
        content="assistant answer",
        status="completed",
        sources=sources,
        tool_invocations=tool_invocations,
        process_events=process_events,
        metrics=metrics,
    )

    snapshot = await service.load_snapshot("thread-process")

    assert snapshot is not None
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["session"]["summary"] == "assistant answer"
    assert len(snapshot["messages"]) == 1
    assert snapshot["messages"][0]["role"] == "assistant"
    assert snapshot["messages"][0]["content"] == "assistant answer"
    assert snapshot["messages"][0]["sources"] == sources
    assert snapshot["messages"][0]["tool_invocations"] == tool_invocations
    assert snapshot["messages"][0]["process_events"] == process_events
    assert snapshot["messages"][0]["metrics"] == metrics
    assert snapshot["messages"][0]["completed_at"] is not None


@pytest.mark.asyncio
async def test_start_session_run_refreshes_context_snapshot() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    service = SessionService(store=store, checkpointer=None)

    await service.start_session_run(
        thread_id="thread-context",
        user_id="alice",
        route="agent",
        initial_user_message="以后请用中文回答",
    )

    session = await service.get_session("thread-context")

    assert session is not None
    assert session["context_snapshot"]["version"] == 1
    assert "以后请用中文回答" in session["context_snapshot"]["pinned_items"]


@pytest.mark.asyncio
async def test_finalize_assistant_message_refreshes_recent_tools_and_sources() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    await store.create_session(
        thread_id="thread-short-term",
        user_id="alice",
        title="Short-term memory",
        route="agent",
        status="running",
    )
    service = SessionService(store=store, checkpointer=None)

    await service.start_session_run(
        thread_id="thread-short-term",
        user_id="alice",
        route="agent",
        initial_user_message="帮我查一下持久化改造",
    )
    await service.finalize_assistant_message(
        thread_id="thread-short-term",
        content="我已经检查了相关文档。",
        status="completed",
        sources=[{"title": "Doc", "url": "https://example.com/doc"}],
        tool_invocations=[
            {
                "toolName": "search_docs",
                "toolCallId": "tool-1",
                "state": "completed",
                "args": {"query": "persistence"},
            }
        ],
        process_events=[
            {
                "type": "tool",
                "data": {
                    "name": "search_docs",
                    "status": "completed",
                    "args": {"query": "persistence"},
                },
            }
        ],
    )

    session = await service.get_session("thread-short-term")

    assert session is not None
    assert any("search_docs" in item for item in session["context_snapshot"]["recent_tools"])
    assert any("Doc" in item for item in session["context_snapshot"]["recent_sources"])


@pytest.mark.asyncio
async def test_load_chat_runtime_context_uses_snapshot_and_recent_messages() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    await store.create_session(
        thread_id="thread-runtime",
        user_id="alice",
        title="Runtime context",
        route="agent",
        status="running",
    )
    await store.update_session_metadata(
        "thread-runtime",
        {
            "context_snapshot": {
                "version": 1,
                "summarized_through_seq": 1,
                "rolling_summary": "之前已经说明过上下文裁剪。",
                "pinned_items": ["请用中文回答"],
                "open_questions": [],
                "recent_tools": [],
                "recent_sources": [],
                "updated_at": "2026-04-09T11:00:00Z",
            }
        },
    )
    await store.append_message(
        thread_id="thread-runtime",
        role="user",
        content="hello",
        created_at="2026-04-06T08:00:00Z",
    )
    await store.append_message(
        thread_id="thread-runtime",
        role="assistant",
        content="world",
        created_at="2026-04-06T08:00:01Z",
    )
    service = SessionService(store=store, checkpointer=None)

    runtime_context = await service.load_chat_runtime_context("thread-runtime")

    assert [message.content for message in runtime_context["history_messages"]] == [
        "hello",
        "world",
    ]
    assert (
        runtime_context["short_term_context"]["rolling_summary"]
        == "之前已经说明过上下文裁剪。"
    )
    assert runtime_context["short_term_context"]["pinned_items"] == ["请用中文回答"]
