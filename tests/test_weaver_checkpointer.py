from __future__ import annotations

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from tests.persistence_fixtures import build_fake_pg_conn

from common.weaver_checkpointer import WeaverPostgresCheckpointer


@pytest.mark.asyncio
async def test_setup_creates_checkpoint_tables() -> None:
    conn = build_fake_pg_conn()
    saver = WeaverPostgresCheckpointer(conn)

    await saver.setup()

    ddl_statements = [sql for sql, _ in conn.executed]
    assert any("graph_checkpoints" in sql for sql in ddl_statements)
    assert any("graph_checkpoint_writes" in sql for sql in ddl_statements)
    assert len(ddl_statements) >= 2


def test_weaver_checkpointer_is_a_langgraph_base_checkpoint_saver() -> None:
    saver = WeaverPostgresCheckpointer(build_fake_pg_conn())
    assert isinstance(saver, BaseCheckpointSaver)


@pytest.mark.asyncio
async def test_put_writes_is_idempotent_for_same_task_and_index() -> None:
    conn = build_fake_pg_conn()
    saver = WeaverPostgresCheckpointer(conn)

    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": "", "checkpoint_id": "cp-1"}}
    writes = [("channel_a", {"value": 1}), ("channel_b", {"value": 2})]

    await saver.aput_writes(config, writes, task_id="task-1", task_path="root")
    await saver.aput_writes(config, writes, task_id="task-1", task_path="root")

    inserts = [sql for sql, _ in conn.executed if "graph_checkpoint_writes" in sql]
    assert inserts, "expected writes insert SQL to run"


@pytest.mark.asyncio
async def test_get_tuple_returns_latest_checkpoint_when_checkpoint_id_missing() -> None:
    conn = build_fake_pg_conn()
    saver = WeaverPostgresCheckpointer(conn)
    serde = JsonPlusSerializer()
    base = {"configurable": {"thread_id": "thread-7", "checkpoint_ns": ""}}

    await saver.aput(
        {**base, "configurable": {**base["configurable"], "checkpoint_id": "cp-1"}},
        {"id": "cp-1", "ts": "2026-04-06T00:00:00Z", "channel_values": {}},
        {"created_at": "2026-04-06T00:00:00Z"},
        {},
    )
    await saver.aput(
        {**base, "configurable": {**base["configurable"], "checkpoint_id": "cp-2"}},
        {"id": "cp-2", "ts": "2026-04-06T00:01:00Z", "channel_values": {}},
        {"created_at": "2026-04-06T00:01:00Z"},
        {},
    )
    await saver.aput_writes(
        {**base, "configurable": {**base["configurable"], "checkpoint_id": "cp-2"}},
        [("channel_a", {"value": 1})],
        task_id="task-1",
        task_path="root",
    )

    checkpoint_tuple = await saver.aget_tuple(base)

    assert checkpoint_tuple is not None
    assert checkpoint_tuple.checkpoint["id"] == "cp-2"
    assert checkpoint_tuple.metadata["created_at"] == "2026-04-06T00:01:00Z"
    assert checkpoint_tuple.pending_writes == [("task-1", "channel_a", {"value": 1})]


@pytest.mark.asyncio
async def test_delete_thread_removes_checkpoints_and_writes() -> None:
    conn = build_fake_pg_conn()
    saver = WeaverPostgresCheckpointer(conn)

    await saver.aput(
        {"configurable": {"thread_id": "thread-delete", "checkpoint_ns": "", "checkpoint_id": "cp-1"}},
        {"id": "cp-1", "ts": "2026-04-06T00:00:00Z", "channel_values": {}},
        {"created_at": "2026-04-06T00:00:00Z"},
        {},
    )
    await saver.aput_writes(
        {"configurable": {"thread_id": "thread-delete", "checkpoint_ns": "", "checkpoint_id": "cp-1"}},
        [("channel_a", {"value": 1})],
        task_id="task-1",
    )

    await saver.adelete_thread("thread-delete")

    assert await conn.fetchval(
        "SELECT COUNT(*) FROM graph_checkpoints WHERE thread_id = %s",
        ("thread-delete",),
    ) == 0
    assert conn.rows["graph_checkpoint_writes"] == []
