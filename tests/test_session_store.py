from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from common.session_store import SessionStore
from tests.persistence_fixtures import build_fake_pg_conn


@pytest.mark.asyncio
async def test_setup_creates_session_tables_with_separate_statements() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)

    await store.setup()

    ddl_statements = [sql for sql, _ in conn.executed]
    assert any("sessions" in sql for sql in ddl_statements)
    assert any("session_messages" in sql for sql in ddl_statements)
    assert len(ddl_statements) >= 2


@pytest.mark.asyncio
async def test_create_session_and_append_messages() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()

    await store.create_session(
        thread_id="thread-a",
        user_id="alice",
        title="First question",
        route="agent",
        status="running",
    )
    await store.append_message(
        thread_id="thread-a",
        role="user",
        content="What changed?",
        created_at="2026-04-06T08:00:00Z",
    )

    snapshot = await store.get_snapshot("thread-a")
    assert snapshot["session"]["thread_id"] == "thread-a"
    assert snapshot["messages"][0]["role"] == "user"
    assert snapshot["messages"][0]["content"] == "What changed?"


@pytest.mark.asyncio
async def test_list_sessions_filters_by_user_and_sorts_by_updated_at() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()

    await store.create_session(
        thread_id="thread-alice",
        user_id="alice",
        title="Alice question",
        route="agent",
        status="running",
    )
    await store.create_session(
        thread_id="thread-bob",
        user_id="bob",
        title="Bob question",
        route="deep",
        status="completed",
    )

    sessions = await store.list_sessions(user_id="alice", limit=10)

    assert [session["thread_id"] for session in sessions] == ["thread-alice"]


@pytest.mark.asyncio
async def test_update_session_metadata_updates_title_and_pin() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    await store.create_session(
        thread_id="thread-edit",
        user_id="alice",
        title="Old title",
        route="agent",
        status="running",
    )

    updated = await store.update_session_metadata(
        "thread-edit",
        {"title": "New title", "is_pinned": True},
    )

    assert updated["title"] == "New title"
    assert updated["is_pinned"] is True


@pytest.mark.asyncio
async def test_update_session_metadata_supports_context_snapshot() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    await store.create_session(
        thread_id="thread-context",
        user_id="alice",
        title="Context session",
        route="agent",
        status="running",
    )

    updated = await store.update_session_metadata(
        "thread-context",
        {
            "context_snapshot": {
                "version": 1,
                "summarized_through_seq": 3,
                "rolling_summary": "summary",
                "pinned_items": ["请用中文回答"],
                "open_questions": [],
                "recent_tools": [],
                "recent_sources": [],
                "updated_at": "2026-04-09T10:00:00Z",
            }
        },
    )

    assert updated["context_snapshot"]["rolling_summary"] == "summary"
    assert updated["context_snapshot"]["pinned_items"] == ["请用中文回答"]


@pytest.mark.asyncio
async def test_get_snapshot_serializes_datetime_and_uuid_fields() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)

    session_created_at = datetime(2026, 4, 6, 7, 15, 55, 108562, tzinfo=UTC)
    message_id = uuid4()
    message_created_at = datetime(2026, 4, 6, 0, 0, 0, tzinfo=UTC)

    conn.rows["sessions"] = [
        {
            "thread_id": "thread-serialize",
            "user_id": "alice",
            "title": "Serialized session",
            "summary": "",
            "context_snapshot": {"version": 1, "rolling_summary": "summary"},
            "status": "running",
            "route": "agent",
            "is_pinned": False,
            "tags": [],
            "created_at": session_created_at,
            "updated_at": session_created_at,
        }
    ]
    conn.rows["session_messages"] = [
        {
            "id": message_id,
            "thread_id": "thread-serialize",
            "seq": 1,
            "role": "assistant",
            "content": "hello",
            "attachments": [],
            "sources": [],
            "tool_invocations": [],
            "process_events": [],
            "metrics": {},
            "created_at": message_created_at,
            "completed_at": None,
        }
    ]

    snapshot = await store.get_snapshot("thread-serialize")

    assert snapshot["session"]["created_at"] == session_created_at.isoformat()
    assert snapshot["session"]["updated_at"] == session_created_at.isoformat()
    assert snapshot["session"]["context_snapshot"]["rolling_summary"] == "summary"
    assert snapshot["messages"][0]["id"] == str(message_id)
    assert snapshot["messages"][0]["created_at"] == message_created_at.isoformat()


@pytest.mark.asyncio
async def test_list_messages_returns_recent_messages_in_ascending_order() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    await store.create_session(
        thread_id="thread-recent",
        user_id="alice",
        title="Recent messages",
        route="agent",
        status="running",
    )
    await store.append_message(
        thread_id="thread-recent",
        role="user",
        content="first",
        created_at="2026-04-06T08:00:00Z",
    )
    await store.append_message(
        thread_id="thread-recent",
        role="assistant",
        content="second",
        created_at="2026-04-06T08:00:01Z",
    )
    await store.append_message(
        thread_id="thread-recent",
        role="user",
        content="third",
        created_at="2026-04-06T08:00:02Z",
    )

    messages = await store.list_messages("thread-recent", limit=2)

    assert [message["content"] for message in messages] == ["second", "third"]


@pytest.mark.asyncio
async def test_list_messages_after_seq_returns_incremental_rows() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    await store.create_session(
        thread_id="thread-incremental",
        user_id="alice",
        title="Incremental messages",
        route="agent",
        status="running",
    )
    await store.append_message(
        thread_id="thread-incremental",
        role="user",
        content="first",
        created_at="2026-04-06T08:00:00Z",
    )
    await store.append_message(
        thread_id="thread-incremental",
        role="assistant",
        content="second",
        created_at="2026-04-06T08:00:01Z",
    )
    await store.append_message(
        thread_id="thread-incremental",
        role="user",
        content="third",
        created_at="2026-04-06T08:00:02Z",
    )

    messages = await store.list_messages_after_seq("thread-incremental", after_seq=1, limit=10)

    assert [message["seq"] for message in messages] == [2, 3]
    assert [message["content"] for message in messages] == ["second", "third"]


@pytest.mark.asyncio
async def test_session_store_serializes_concurrent_reads_on_shared_async_connection() -> None:
    class BusyConn:
        def __init__(self) -> None:
            self.busy = False
            self.row = {
                "thread_id": "thread-busy",
                "user_id": "alice",
                "title": "Busy session",
                "summary": "",
                "status": "running",
                "route": "agent",
                "is_pinned": False,
                "tags": [],
                "created_at": "2026-04-06T00:00:00Z",
                "updated_at": "2026-04-06T00:00:00Z",
            }

        async def fetchrow(self, sql: str, params: tuple | None = None):
            assert "FROM sessions" in sql
            if self.busy:
                raise RuntimeError("another command is already in progress")
            self.busy = True
            try:
                await asyncio.sleep(0.01)
                return self.row
            finally:
                self.busy = False

    store = SessionStore(BusyConn())

    first, second = await asyncio.gather(
        store.get_session("thread-busy"),
        store.get_session("thread-busy"),
    )

    assert first["thread_id"] == "thread-busy"
    assert second["thread_id"] == "thread-busy"
