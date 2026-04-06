from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.persistence_fixtures import build_fake_pg_conn

from common.session_store import SessionStore


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
async def test_get_snapshot_serializes_datetime_and_uuid_fields() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)

    session_created_at = datetime(2026, 4, 6, 7, 15, 55, 108562, tzinfo=timezone.utc)
    message_id = uuid4()
    message_created_at = datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)

    conn.rows["sessions"] = [
        {
            "thread_id": "thread-serialize",
            "user_id": "alice",
            "title": "Serialized session",
            "summary": "",
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
    assert snapshot["messages"][0]["id"] == str(message_id)
    assert snapshot["messages"][0]["created_at"] == message_created_at.isoformat()
