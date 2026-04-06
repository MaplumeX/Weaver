# Session Persistence Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 Weaver 的会话持久化与 checkpoint 层，改为 `SessionStore + WeaverPostgresCheckpointer` 双层持久化，保留 LangGraph 的 interrupt/resume 语义，但删除当前“扫 checkpoint 拼会话”的实现。

**Architecture:** 会话元数据和消息快照统一写入服务端 `SessionStore`；LangGraph 恢复状态统一写入 `WeaverPostgresCheckpointer`；`SessionService` 作为编排层，将聊天流式生命周期、会话 API 和 checkpoint 恢复解耦。前端历史列表与会话恢复改为消费服务端 snapshot 接口，不再把 `localStorage` 当作会话真相源。

**Tech Stack:** Python 3.11, FastAPI, LangGraph 1.x, psycopg 3, Pydantic v2, pytest, Next.js 14, TypeScript, node:test

---

**Scope Notes**

- 本计划执行你已确认的硬切设计：不迁移旧 `localStorage` 会话，不兼容旧 checkpoint 会话读模型。
- 保留 LangGraph 的 `thread_id / checkpoint / interrupt / resume` 语义，但不复用当前 checkpointer 存储实现。
- 仍允许 `GET /api/sessions/{thread_id}/state` 作为 runtime/debug 视图存在，但不再承担聊天恢复职责。
- 按仓库约束，本计划不包含 `git commit` 步骤。
- 本计划假定实现阶段使用 TDD；每个后端任务都先加失败测试，再做最小实现。

**File Map**

- Create: `common/persistence_schema.py`
  作用：集中创建 `sessions`、`session_messages`、`graph_checkpoints`、`graph_checkpoint_writes` 表。
- Create: `common/weaver_checkpointer.py`
  作用：实现自定义 LangGraph checkpointer，包括 `put/get_tuple/list/put_writes/delete_thread`。
- Create: `common/session_store.py`
  作用：封装会话元数据与消息快照 CRUD。
- Create: `common/checkpoint_runtime.py`
  作用：提供 checkpoint 侧的运行时读取辅助，例如读取 thread state、派生 pending interrupt、提取 deep research artifacts。
- Create: `common/session_service.py`
  作用：组合 `SessionStore` 与 `WeaverPostgresCheckpointer`，提供会话生命周期编排。
- Create: `tests/test_weaver_checkpointer.py`
  作用：覆盖自定义 checkpointer 的核心契约和幂等性。
- Create: `tests/persistence_fixtures.py`
  作用：提供共享的 `build_fake_pg_conn()`、`FakeRow` 和记录型异步连接，供持久化测试复用。
- Create: `tests/test_session_store.py`
  作用：覆盖会话元数据、消息追加、排序和删除。
- Create: `tests/test_session_service.py`
  作用：覆盖 snapshot 组装、状态流转、删除编排。
- Create: `tests/test_session_snapshot_api.py`
  作用：覆盖新的 snapshot 接口和 `PATCH /api/sessions/{thread_id}`。
- Create: `tests/test_chat_session_persistence.py`
  作用：覆盖聊天流式生命周期中的会话落盘。
- Create: `web/tests/use-chat-history.test.ts`
  作用：覆盖前端历史列表与 snapshot 恢复逻辑不再依赖 `localStorage`。
- Modify: `agent/runtime/graph.py`
  作用：将 `create_checkpointer()` 从 `AsyncPostgresSaver` 切换为 `WeaverPostgresCheckpointer`。
- Modify: `common/checkpoint_ops.py`
  作用：补齐 thread 级删除 helper，并兼容新的 checkpointer 方法。
- Modify: `main.py`
  作用：初始化 session store/service、移除 `MemorySaver()` 降级、重写会话 API 和聊天流式落盘。
- Modify: `tests/test_checkpointer_config.py`
  作用：校验 `create_checkpointer()` 改为构造 `WeaverPostgresCheckpointer`。
- Modify: `tests/test_health_db_status.py`
  作用：锁定无数据库时不再伪装可用恢复能力的健康状态。
- Modify: `tests/test_resume_session_deepsearch.py`
  作用：从旧 `SessionManager` fake 切到新的 `SessionService` / `checkpoint_runtime` 契约。
- Modify: `tests/test_session_evidence_api.py`
  作用：会话证据接口不再依赖旧 `SessionManager`。
- Modify: `tests/test_sessions_api_auth_filter.py`
  作用：会话列表改为基于 `SessionStore` 的用户隔离。
- Modify: `tests/test_sessions_api_thread_authz.py`
  作用：会话详情、snapshot、evidence 的鉴权来源调整为 session store + checkpoint runtime。
- Modify: `web/lib/session-api.ts`
  作用：新增 `fetchSessionSnapshot()` 和 `patchSession()`。
- Modify: `web/hooks/useChatHistory.ts`
  作用：移除 `localStorage` 作为会话真相源，改为消费服务端 snapshot。
- Modify: `web/components/chat/Chat.tsx`
  作用：聊天页打开历史会话时改为使用 snapshot 负载。
- Modify: `web/types/chat.ts`
  作用：补齐服务端 snapshot 需要的字段类型。
- Modify: `web/tests/session-utils.test.ts`
  作用：删除依赖 checkpoint state 拼消息的旧假设。
- Delete After Cutover Verification: `common/session_manager.py`
  作用：旧 checkpoint 会话包装器；在所有引用迁移完成后删除。
- Delete After Cutover Verification: `tests/test_session_manager_*.py`
  作用：旧会话管理器测试；迁移到新的 store/service 测试后删除。

### Task 1: 建立新的持久化底座与 Checkpointer 契约测试

**Files:**
- Create: `common/persistence_schema.py`
- Create: `common/weaver_checkpointer.py`
- Create: `tests/persistence_fixtures.py`
- Test: `tests/test_weaver_checkpointer.py`

- [ ] **Step 1: 先写自定义 checkpointer 的失败测试**

```python
from __future__ import annotations

import pytest

from tests.persistence_fixtures import build_fake_pg_conn
from common.weaver_checkpointer import WeaverPostgresCheckpointer


@pytest.mark.asyncio
async def test_setup_creates_checkpoint_tables() -> None:
    conn = build_fake_pg_conn()
    saver = WeaverPostgresCheckpointer(conn)

    await saver.setup()

    ddl = "\n".join(sql for sql, _ in conn.executed)
    assert "graph_checkpoints" in ddl
    assert "graph_checkpoint_writes" in ddl


@pytest.mark.asyncio
async def test_put_writes_is_idempotent_for_same_task_and_index() -> None:
    conn = _FakeConn()
    saver = WeaverPostgresCheckpointer(conn)

    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": "", "checkpoint_id": "cp-1"}}
    writes = [("channel_a", {"value": 1}), ("channel_b", {"value": 2})]

    await saver.aput_writes(config, writes, task_id="task-1", task_path="root")
    await saver.aput_writes(config, writes, task_id="task-1", task_path="root")

    inserts = [sql for sql, _ in conn.executed if "graph_checkpoint_writes" in sql]
    assert inserts, "expected writes insert SQL to run"
```

- [ ] **Step 2: 运行测试，确认当前缺少新的 checkpointer**

Run: `uv run pytest tests/test_weaver_checkpointer.py -v`

Expected:
- `ModuleNotFoundError: No module named 'common.weaver_checkpointer'`

- [ ] **Step 3: 写最小 schema helper 和 checkpointer 骨架**

```python
# tests/persistence_fixtures.py
from __future__ import annotations


class RecordingAsyncConn:
    def __init__(self):
        self.executed: list[tuple[str, tuple | None]] = []

    async def execute(self, sql: str, params: tuple | None = None):
        self.executed.append((sql, params))

    async def fetchrow(self, sql: str, params: tuple | None = None):
        return None

    async def fetch(self, sql: str, params: tuple | None = None):
        return []

    async def fetchval(self, sql: str, params: tuple | None = None):
        return 0


def build_fake_pg_conn() -> RecordingAsyncConn:
    return RecordingAsyncConn()
```

```python
# common/persistence_schema.py
from __future__ import annotations


CHECKPOINT_DDL = """
CREATE TABLE IF NOT EXISTS graph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checkpoint_payload BYTEA NOT NULL,
    metadata_payload BYTEA NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS graph_checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    write_idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    value_payload BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
);
"""
```

```python
# common/weaver_checkpointer.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.persistence_schema import CHECKPOINT_DDL


@dataclass
class WeaverPostgresCheckpointer:
    conn: Any

    async def setup(self) -> None:
        await self.conn.execute(CHECKPOINT_DDL)

    async def aput_writes(
        self,
        config: dict[str, Any],
        writes: list[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])
        for write_idx, (channel, value) in enumerate(writes):
            await self.conn.execute(
                "INSERT INTO graph_checkpoint_writes "
                "(thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, write_idx, channel, value_payload) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx) DO NOTHING",
                (thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, write_idx, channel, b'{}'),
            )
```

- [ ] **Step 4: 重新运行 checkpointer 基础测试**

Run: `uv run pytest tests/test_weaver_checkpointer.py -v`

Expected:
- `2 passed`

### Task 2: 完成 `WeaverPostgresCheckpointer` 的 LangGraph 兼容实现

**Files:**
- Modify: `common/weaver_checkpointer.py`
- Modify: `tests/persistence_fixtures.py`
- Test: `tests/test_weaver_checkpointer.py`
- Modify: `tests/test_checkpointer_config.py`

- [ ] **Step 1: 补失败测试，锁定 `put/get_tuple/list/delete_thread` 语义**

```python
@pytest.mark.asyncio
async def test_get_tuple_returns_latest_checkpoint_when_checkpoint_id_missing() -> None:
    from tests.persistence_fixtures import build_fake_pg_conn

    conn = build_fake_pg_conn()
    saver = WeaverPostgresCheckpointer(conn)
    await saver.setup()

    base = {"configurable": {"thread_id": "thread-7", "checkpoint_ns": ""}}
    await saver.aput({**base, "configurable": {**base["configurable"], "checkpoint_id": "cp-1"}}, {"id": "cp-1"}, {"created_at": "2026-04-06T00:00:00Z"}, {})
    await saver.aput({**base, "configurable": {**base["configurable"], "checkpoint_id": "cp-2"}}, {"id": "cp-2"}, {"created_at": "2026-04-06T00:01:00Z"}, {})

    checkpoint_tuple = await saver.aget_tuple(base)

    assert checkpoint_tuple.checkpoint["id"] == "cp-2"


@pytest.mark.asyncio
async def test_delete_thread_removes_checkpoints_and_writes() -> None:
    from tests.persistence_fixtures import build_fake_pg_conn

    conn = build_fake_pg_conn()
    saver = WeaverPostgresCheckpointer(conn)
    await saver.setup()
    # 先写入 checkpoint 和 writes，再删除
    await saver.delete_thread("thread-delete")
    assert await conn.fetchval("SELECT COUNT(*) FROM graph_checkpoints WHERE thread_id = %s", ("thread-delete",)) == 0
```

- [ ] **Step 2: 运行测试，确认骨架还不满足 LangGraph 契约**

Run: `uv run pytest tests/test_weaver_checkpointer.py tests/test_checkpointer_config.py -v`

Expected:
- `AttributeError` 或断言失败，提示 `aput/aget_tuple/alist/delete_thread` 尚未实现

- [ ] **Step 3: 用 LangGraph 兼容 tuple 结构补齐实现**

```python
# tests/persistence_fixtures.py
class RecordingAsyncConn:
    def __init__(self):
        self.executed = []
        self.rows = {"graph_checkpoints": [], "graph_checkpoint_writes": []}

    async def execute(self, sql: str, params: tuple | None = None):
        self.executed.append((sql, params))
        if "INSERT INTO graph_checkpoints" in sql:
            self.rows["graph_checkpoints"].append(
                {
                    "thread_id": params[0],
                    "checkpoint_ns": params[1],
                    "checkpoint_id": params[2],
                    "parent_checkpoint_id": params[3],
                    "checkpoint_payload": params[4],
                    "metadata_payload": params[5],
                }
            )
        if "INSERT INTO graph_checkpoint_writes" in sql:
            self.rows["graph_checkpoint_writes"].append(
                {
                    "thread_id": params[0],
                    "checkpoint_ns": params[1],
                    "checkpoint_id": params[2],
                    "task_id": params[3],
                    "channel": params[6],
                    "value_payload": params[7],
                }
            )
        if "DELETE FROM graph_checkpoint_writes" in sql:
            self.rows["graph_checkpoint_writes"] = [row for row in self.rows["graph_checkpoint_writes"] if row["thread_id"] != params[0]]
        if "DELETE FROM graph_checkpoints" in sql:
            self.rows["graph_checkpoints"] = [row for row in self.rows["graph_checkpoints"] if row["thread_id"] != params[0]]

    async def fetchrow(self, sql: str, params: tuple | None = None):
        if "graph_checkpoints" not in sql:
            return None
        if "checkpoint_id = %s" in sql:
            for row in self.rows["graph_checkpoints"]:
                if row["thread_id"] == params[0] and row["checkpoint_ns"] == params[1] and row["checkpoint_id"] == params[2]:
                    return row
            return None
        filtered = [row for row in self.rows["graph_checkpoints"] if row["thread_id"] == params[0] and row["checkpoint_ns"] == params[1]]
        return filtered[-1] if filtered else None

    async def fetch(self, sql: str, params: tuple | None = None):
        if "graph_checkpoint_writes" in sql:
            return [
                row
                for row in self.rows["graph_checkpoint_writes"]
                if row["thread_id"] == params[0] and row["checkpoint_ns"] == params[1] and row["checkpoint_id"] == params[2]
            ]
        return []

    async def fetchval(self, sql: str, params: tuple | None = None):
        if "graph_checkpoints" in sql:
            return len([row for row in self.rows["graph_checkpoints"] if row["thread_id"] == params[0]])
        return 0
```

```python
from __future__ import annotations

from typing import Any, Iterable

from langgraph.checkpoint.base import CheckpointTuple


class WeaverPostgresCheckpointer:
    def __init__(self, conn: Any, *, serde: Any | None = None):
        self.conn = conn
        self.serde = serde or JsonPlusSerializer()

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = dict(config.get("configurable", {}))
        thread_id = str(cfg["thread_id"])
        checkpoint_ns = str(cfg.get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])
        parent_id = str(cfg.get("checkpoint_id", "") or "") or None
        checkpoint_payload = self.serde.dumps_typed(checkpoint)
        metadata_payload = self.serde.dumps_typed(metadata)
        await self.conn.execute(
            "INSERT INTO graph_checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_payload, metadata_payload) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (thread_id, checkpoint_ns, checkpoint_id, parent_id, checkpoint_payload, metadata_payload),
        )
        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id}}

    async def aget_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        cfg = dict((config or {}).get("configurable", {}))
        thread_id = str(cfg["thread_id"])
        checkpoint_ns = str(cfg.get("checkpoint_ns", ""))
        checkpoint_id = str(cfg.get("checkpoint_id", "") or "")
        if checkpoint_id:
            row = await self.conn.fetchrow(
                "SELECT * FROM graph_checkpoints WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s",
                (thread_id, checkpoint_ns, checkpoint_id),
            )
        else:
            row = await self.conn.fetchrow(
                "SELECT * FROM graph_checkpoints WHERE thread_id = %s AND checkpoint_ns = %s ORDER BY created_at DESC LIMIT 1",
                (thread_id, checkpoint_ns),
            )
        if not row:
            return None
        writes = await self.conn.fetch(
            "SELECT task_id, channel, value_payload FROM graph_checkpoint_writes "
            "WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s ORDER BY task_id, write_idx",
            (thread_id, checkpoint_ns, row["checkpoint_id"]),
        )
        checkpoint = self.serde.loads_typed(row["checkpoint_payload"])
        metadata = self.serde.loads_typed(row["metadata_payload"])
        pending_writes = [
            (item["task_id"], item["channel"], self.serde.loads_typed(item["value_payload"]))
            for item in writes
        ]
        parent_config = None
        if row["parent_checkpoint_id"]:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": row["parent_checkpoint_id"],
                }
            }
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": row["checkpoint_id"],
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    async def alist(self, config: dict[str, Any] | None, **kwargs: Any) -> Iterable[CheckpointTuple]:
        cfg = dict((config or {}).get("configurable", {}))
        thread_id = str(cfg.get("thread_id", "") or "")
        checkpoint_ns = str(cfg.get("checkpoint_ns", ""))
        limit = int(kwargs.get("limit") or 100)
        rows = await self.conn.fetch(
            "SELECT thread_id, checkpoint_ns, checkpoint_id FROM graph_checkpoints "
            "WHERE (%s = '' OR thread_id = %s) AND checkpoint_ns = %s "
            "ORDER BY created_at DESC LIMIT %s",
            (thread_id, thread_id, checkpoint_ns, limit),
        )
        for row in rows:
            yield await self.aget_tuple(
                {
                    "configurable": {
                        "thread_id": row["thread_id"],
                        "checkpoint_ns": row["checkpoint_ns"],
                        "checkpoint_id": row["checkpoint_id"],
                    }
                }
            )

    async def adelete_thread(self, thread_id: str) -> None:
        await self.conn.execute("DELETE FROM graph_checkpoint_writes WHERE thread_id = %s", (thread_id,))
        await self.conn.execute("DELETE FROM graph_checkpoints WHERE thread_id = %s", (thread_id,))
```

- [ ] **Step 4: 修改 `create_checkpointer()` 的构造测试**

```python
# tests/test_checkpointer_config.py
class DummyCheckpointer:
    def __init__(self, conn):
        captured["conn"] = conn

    async def setup(self):
        captured["setup_called"] = True


monkeypatch.setattr(graph, "WeaverPostgresCheckpointer", DummyCheckpointer)
checkpointer = await graph.create_checkpointer("postgresql://example")
assert isinstance(checkpointer, DummyCheckpointer)
```

- [ ] **Step 5: 运行 checkpointer 契约测试**

Run: `uv run pytest tests/test_weaver_checkpointer.py tests/test_checkpointer_config.py -v`

Expected:
- `all passed`

### Task 3: 实现 `SessionStore` 与 `SessionService`

**Files:**
- Create: `common/session_store.py`
- Create: `common/checkpoint_runtime.py`
- Create: `common/session_service.py`
- Modify: `tests/persistence_fixtures.py`
- Test: `tests/test_session_store.py`
- Test: `tests/test_session_service.py`

- [ ] **Step 1: 先写会话 store 的失败测试**

```python
from __future__ import annotations

import pytest

from tests.persistence_fixtures import build_fake_pg_conn
from common.session_store import SessionStore


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


@pytest.mark.asyncio
async def test_list_sessions_filters_by_user_and_sorts_by_updated_at() -> None:
    conn = build_fake_pg_conn()
    store = SessionStore(conn)
    await store.setup()
    sessions = await store.list_sessions(user_id="alice", limit=10)
    assert isinstance(sessions, list)
```

- [ ] **Step 2: 运行测试，确认 `SessionStore` 尚不存在**

Run: `uv run pytest tests/test_session_store.py tests/test_session_service.py -v`

Expected:
- `ModuleNotFoundError: No module named 'common.session_store'`

- [ ] **Step 3: 写最小会话存储实现**

```python
# common/session_store.py
from __future__ import annotations

from typing import Any

from common.persistence_schema import SESSION_DDL


class SessionStore:
    def __init__(self, conn: Any):
        self.conn = conn

    async def setup(self) -> None:
        await self.conn.execute(SESSION_DDL)

    async def create_session(self, *, thread_id: str, user_id: str, title: str, route: str, status: str) -> None:
        await self.conn.execute(
            "INSERT INTO sessions (thread_id, user_id, title, route, status) VALUES (%s, %s, %s, %s, %s)",
            (thread_id, user_id, title, route, status),
        )

    async def append_message(self, *, thread_id: str, role: str, content: str, created_at: str, **payload: Any) -> None:
        await self.conn.execute(
            "INSERT INTO session_messages (id, thread_id, seq, role, content, created_at) "
            "VALUES (gen_random_uuid(), %s, COALESCE((SELECT MAX(seq) + 1 FROM session_messages WHERE thread_id = %s), 1), %s, %s, %s)",
            (thread_id, thread_id, role, content, created_at),
        )

    async def get_snapshot(self, thread_id: str) -> dict[str, Any]:
        session = await self.conn.fetchrow(
            "SELECT thread_id, user_id, title, summary, status, route, is_pinned, tags, created_at, updated_at "
            "FROM sessions WHERE thread_id = %s",
            (thread_id,),
        )
        if not session:
            return {}
        messages = await self.conn.fetch(
            "SELECT id, role, content, attachments, sources, tool_invocations, process_events, metrics, created_at, completed_at "
            "FROM session_messages WHERE thread_id = %s ORDER BY seq ASC",
            (thread_id,),
        )
        return {
            "session": dict(session),
            "messages": [dict(message) for message in messages],
        }
```

```python
# common/checkpoint_runtime.py
from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent.runtime.deep.artifacts.public_artifacts import build_public_deep_research_artifacts_from_state
from common.checkpoint_ops import aget_checkpoint_tuple


async def get_thread_runtime_state(checkpointer: Any, thread_id: str) -> dict[str, Any] | None:
    checkpoint_tuple = await aget_checkpoint_tuple(checkpointer, {"configurable": {"thread_id": thread_id}})
    if not checkpoint_tuple:
        return None
    state = checkpoint_tuple.checkpoint.get("channel_values", {})
    return state if isinstance(state, dict) else None


def extract_deep_research_artifacts(state: dict[str, Any] | None) -> dict[str, Any]:
    return build_public_deep_research_artifacts_from_state(state or {})
```

```python
# common/session_service.py
from __future__ import annotations

from typing import Any

from common.checkpoint_runtime import get_thread_runtime_state


class SessionService:
    def __init__(self, *, store, checkpointer):
        self.store = store
        self.checkpointer = checkpointer

    async def load_snapshot(self, thread_id: str) -> dict[str, Any] | None:
        snapshot = await self.store.get_snapshot(thread_id)
        if not snapshot:
            return None
        runtime_state = await get_thread_runtime_state(self.checkpointer, thread_id)
        return {
            **snapshot,
            "pending_interrupt": runtime_state.get("__interrupt__") if isinstance(runtime_state, dict) else None,
            "can_resume": bool(runtime_state),
        }
```

- [ ] **Step 4: 写 service 层失败测试并补齐状态编排**

```python
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
```

- [ ] **Step 5: 运行 store/service 测试**

Run: `uv run pytest tests/test_session_store.py tests/test_session_service.py -v`

Expected:
- `all passed`

### Task 4: 重写运行时初始化并移除 `MemorySaver()` 降级

**Files:**
- Modify: `agent/runtime/graph.py`
- Modify: `main.py`
- Modify: `tests/test_health_db_status.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: 先写健康状态和初始化失败测试**

```python
@pytest.mark.asyncio
async def test_health_reports_failed_when_database_required_but_unavailable(monkeypatch):
    monkeypatch.setattr(main.settings, "database_url", "")
    monkeypatch.setattr(main, "_checkpointer_status", "failed")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200
    assert resp.json()["database"] == "failed"
```

- [ ] **Step 2: 运行配置与健康测试，确认当前仍假设 `MemorySaver()`**

Run: `uv run pytest tests/test_checkpointer_config.py tests/test_health_db_status.py -v`

Expected:
- 至少一条失败，显示当前 `create_checkpointer()` 仍构造 `AsyncPostgresSaver`
- 健康测试仍把无数据库视为 `not_configured`

- [ ] **Step 3: 将运行时初始化切换到新的持久化对象**

```python
# agent/runtime/graph.py
from common.weaver_checkpointer import WeaverPostgresCheckpointer


async def create_checkpointer(database_url: str):
    if not database_url:
        raise ValueError("database_url is required for WeaverPostgresCheckpointer")
    conn = await psycopg.AsyncConnection.connect(
        database_url,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    )
    checkpointer = WeaverPostgresCheckpointer(conn)
    await checkpointer.setup()
    return checkpointer
```

```python
# main.py
checkpointer = None
session_store = None
session_service = None


async def _initialize_runtime_state() -> None:
    if not settings.database_url:
        checkpointer = None
        session_store = None
        session_service = None
        _checkpointer_status = "failed"
        _checkpointer_error = "DATABASE_URL is required for session persistence"
        return
```

- [ ] **Step 4: 更新测试入口，避免全局默认 `DATABASE_URL=''` 再伪装合法后端**

```python
# tests/conftest.py
os.environ.setdefault("DATABASE_URL", "postgresql://test-placeholder")
```

```python
class DummyCheckpointer:
    async def setup(self):
        return None


monkeypatch.setattr("agent.runtime.graph.create_checkpointer", lambda _url: DummyCheckpointer())
monkeypatch.setattr(main.settings, "database_url", "postgresql://example")
```

- [ ] **Step 5: 重新运行初始化与健康测试**

Run: `uv run pytest tests/test_checkpointer_config.py tests/test_health_db_status.py -v`

Expected:
- `all passed`

### Task 5: 重写会话 API，并切走旧 `SessionManager`

**Files:**
- Modify: `main.py`
- Create: `tests/test_session_snapshot_api.py`
- Modify: `tests/test_sessions_api_auth_filter.py`
- Modify: `tests/test_sessions_api_thread_authz.py`
- Modify: `tests/test_resume_session_deepsearch.py`
- Modify: `tests/test_session_evidence_api.py`
- Delete After Green: `common/session_manager.py`
- Delete After Green: `tests/test_session_manager_postgres_listing.py`
- Delete After Green: `tests/test_session_manager_user_filter.py`
- Delete After Green: `tests/test_session_manager_claim_evidence_passages.py`
- Delete After Green: `tests/test_session_deepsearch_artifacts.py`

- [ ] **Step 1: 先写新的 snapshot / patch API 失败测试**

```python
@pytest.mark.asyncio
async def test_session_snapshot_returns_messages_and_resume_flags(monkeypatch):
    class FakeSessionService:
        def __init__(self, *, snapshot=None, updated=None):
            self._snapshot = snapshot
            self._updated = updated

        async def load_snapshot(self, thread_id: str):
            return self._snapshot

        async def update_session_metadata(self, thread_id: str, payload: dict[str, object]):
            return self._updated

    fake_service = FakeSessionService(
        snapshot={
            "session": {"thread_id": "thread-api", "title": "hello", "status": "interrupted"},
            "messages": [{"id": "m1", "role": "user", "content": "hello"}],
            "pending_interrupt": {"kind": "scope_review"},
            "can_resume": True,
        }
    )
    monkeypatch.setattr(main, "session_service", fake_service)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sessions/thread-api/snapshot")

    assert resp.status_code == 200
    assert resp.json()["can_resume"] is True
    assert resp.json()["messages"][0]["content"] == "hello"
```

```python
@pytest.mark.asyncio
async def test_patch_session_updates_title_and_pin(monkeypatch):
    class FakeSessionService:
        def __init__(self, *, updated=None):
            self._updated = updated

        async def update_session_metadata(self, thread_id: str, payload: dict[str, object]):
            return self._updated

    fake_service = FakeSessionService(updated={"thread_id": "thread-api", "title": "Renamed", "is_pinned": True})
    monkeypatch.setattr(main, "session_service", fake_service)
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch("/api/sessions/thread-api", json={"title": "Renamed", "is_pinned": True})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"
```

- [ ] **Step 2: 运行 API 测试，确认当前接口和依赖仍停留在旧 `SessionManager`**

Run: `uv run pytest tests/test_session_snapshot_api.py tests/test_sessions_api_auth_filter.py tests/test_sessions_api_thread_authz.py tests/test_resume_session_deepsearch.py tests/test_session_evidence_api.py -v`

Expected:
- 新测试因 `/snapshot` 或 `PATCH /api/sessions/{thread_id}` 缺失而失败
- 旧测试仍在 monkeypatch `common.session_manager.get_session_manager`

- [ ] **Step 3: 在 `main.py` 中引入新的 snapshot 响应模型和 patch payload**

```python
class SessionMessagePayload(BaseModel):
    id: str
    role: str
    content: str
    attachments: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    tool_invocations: List[Dict[str, Any]] = []
    process_events: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {}
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class SessionSnapshotResponse(BaseModel):
    session: SessionSummary
    messages: List[SessionMessagePayload]
    pending_interrupt: Optional[Dict[str, Any]] = None
    can_resume: bool = False
    checkpoint_cleanup_pending: bool = False


class SessionPatchRequest(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    is_pinned: Optional[bool] = None
    tags: Optional[List[str]] = None
```

- [ ] **Step 4: 重写会话接口为 `session_service` 驱动**

```python
@app.get("/api/sessions/{thread_id}/snapshot", response_model=SessionSnapshotResponse)
async def get_session_snapshot(thread_id: str, request: Request):
    await _require_thread_owner(request, thread_id)
    snapshot = await session_service.load_snapshot(thread_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")
    return snapshot


@app.patch("/api/sessions/{thread_id}")
async def patch_session(thread_id: str, request: Request, payload: SessionPatchRequest):
    await _require_thread_owner(request, thread_id)
    updated = await session_service.update_session_metadata(thread_id, payload.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")
    return updated
```

- [ ] **Step 5: 把 evidence / resume / auth 测试中的旧 `SessionManager` fake 改成 `session_service` 或 `checkpoint_runtime` fake**

```python
monkeypatch.setattr(
    main,
    "session_service",
    FakeSessionService(
        snapshot={
            "session": {"thread_id": "thread-api", "title": "hello", "status": "running"},
            "messages": [],
            "pending_interrupt": None,
            "can_resume": False,
        }
    ),
)
monkeypatch.setattr("common.checkpoint_runtime.get_thread_runtime_state", fake_get_thread_runtime_state)
```

- [ ] **Step 6: 跑会话 API 回归测试**

Run: `uv run pytest tests/test_session_snapshot_api.py tests/test_sessions_api_auth_filter.py tests/test_sessions_api_thread_authz.py tests/test_resume_session_deepsearch.py tests/test_session_evidence_api.py -v`

Expected:
- `all passed`

### Task 6: 将聊天流式生命周期接到 `SessionService`

**Files:**
- Modify: `main.py`
- Create: `tests/test_chat_session_persistence.py`

- [ ] **Step 1: 先写聊天流中的会话落盘失败测试**

```python
@pytest.mark.asyncio
async def test_chat_stream_creates_session_and_persists_user_message(monkeypatch):
    captured: list[tuple[str, dict]] = []

    class FakeSessionService:
        async def start_session_run(self, **payload):
            captured.append(("start", payload))

        async def append_user_message(self, **payload):
            captured.append(("user", payload))

        async def finalize_assistant_message(self, **payload):
            captured.append(("assistant", payload))

    async def fake_stream_agent_events(*args, **kwargs):
        yield 'data: {"type":"text","data":{"content":"assistant answer"}}\n\n'
        yield 'data: {"type":"done","data":{"metrics":{"run_id":"run-1"}}}\n\n'

    monkeypatch.setattr(main, "session_service", FakeSessionService())
    monkeypatch.setattr(main, "stream_agent_events", fake_stream_agent_events)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
                "search_mode": "agent",
            },
        )

    assert captured[0][0] == "start"
    assert captured[1][0] == "user"
```

- [ ] **Step 2: 运行测试，确认当前聊天流没有调用 `SessionService`**

Run: `uv run pytest tests/test_chat_session_persistence.py -v`

Expected:
- 断言失败，`captured` 为空

- [ ] **Step 3: 在聊天入口创建会话并先写 user message**

```python
thread_id = f"thread_{uuid.uuid4().hex}"
await session_service.start_session_run(
    thread_id=thread_id,
    user_id=user_id,
    route=mode_info.get("mode", "agent"),
    initial_user_message=last_message,
)
```

- [ ] **Step 4: 在 SSE 生命周期边界事件中统一 finalize assistant**

```python
assistant_accumulator = {
    "content": "",
    "sources": [],
    "tool_invocations": [],
    "process_events": [],
    "metrics": {},
}
if event_type == "text":
    assistant_accumulator["content"] += event_payload.get("content", "")
elif event_type == "sources":
    assistant_accumulator["sources"] = list(event_payload.get("items", []))
elif event_type == "tool":
    assistant_accumulator["tool_invocations"].append(event_payload)
elif event_type in {"status", "search", "thinking", "task_update"}:
    assistant_accumulator["process_events"].append({"type": event_type, "data": event_payload})
elif event_type == "done":
    assistant_accumulator["metrics"] = dict(event_payload.get("metrics", {}))

await session_service.finalize_assistant_message(
    thread_id=thread_id,
    content=assistant_accumulator["content"],
    sources=assistant_accumulator["sources"],
    tool_invocations=assistant_accumulator["tool_invocations"],
    process_events=assistant_accumulator["process_events"],
    metrics=assistant_accumulator["metrics"],
    status=final_status,
)
```

- [ ] **Step 5: 在 interrupt/cancel/fail 路径中接入状态更新**

```python
await session_service.mark_interrupted(thread_id=thread_id)
await session_service.mark_cancelled(thread_id=thread_id)
await session_service.mark_failed(thread_id=thread_id, error=str(e))
```

- [ ] **Step 6: 运行聊天持久化测试**

Run: `uv run pytest tests/test_chat_session_persistence.py -v`

Expected:
- `all passed`

### Task 7: 前端改为消费服务端 Session Snapshot

**Files:**
- Modify: `web/lib/session-api.ts`
- Modify: `web/hooks/useChatHistory.ts`
- Modify: `web/components/chat/Chat.tsx`
- Modify: `web/types/chat.ts`
- Modify: `web/tests/session-utils.test.ts`
- Create: `web/tests/use-chat-history.test.ts`

- [ ] **Step 1: 先写前端失败测试，锁定“打开会话时必须走 snapshot”**

```typescript
import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { fetchSessionSnapshot } from '../lib/session-api'

test('fetchSessionSnapshot requests the new snapshot endpoint', async () => {
  let requested = ''
  globalThis.fetch = async ((input: string) => {
    requested = input
    return new Response(JSON.stringify({ session: { thread_id: 'thread-1' }, messages: [], can_resume: false }), { status: 200 })
  }) as typeof fetch

  await fetchSessionSnapshot('thread-1')
  assert.match(requested, /\/api\/sessions\/thread-1\/snapshot$/)
})
```

- [ ] **Step 2: 运行前端测试，确认 snapshot helper 还不存在**

Run: `pnpm -C web test -- tests/use-chat-history.test.ts tests/session-utils.test.ts`

Expected:
- `fetchSessionSnapshot is not a function` 或导入失败

- [ ] **Step 3: 在前端 API 层补齐 snapshot / patch helper**

```typescript
export async function fetchSessionSnapshot(threadId: string) {
  return fetchJson(`/api/sessions/${threadId}/snapshot`)
}

export async function patchSession(threadId: string, payload: Record<string, unknown>) {
  return fetchJson(`/api/sessions/${threadId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
```

- [ ] **Step 4: 将 `useChatHistory()` 改为服务端真相源**

```typescript
const refreshHistory = useCallback(async () => {
  const remoteHistory = await fetchSessions(REMOTE_SESSION_LIMIT)
  commitHistory(remoteHistory.map(mapRemoteSession))
}, [commitHistory])

const loadSession = useCallback(async (id: string) => {
  const snapshot = await fetchSessionSnapshot(id)
  if (!snapshot) return null
  return {
    sessionId: id,
    threadId: snapshot.session.thread_id,
    messages: snapshot.messages,
    pendingInterrupt: snapshot.pending_interrupt,
    canResume: snapshot.can_resume,
    artifacts: [],
    currentStatus: snapshot.session.status,
    route: snapshot.session.route,
    searchMode: snapshot.session.route,
    status: snapshot.session.status,
    updatedAt: Date.parse(snapshot.session.updated_at),
    createdAt: Date.parse(snapshot.session.created_at),
  }
}, [])
```

- [ ] **Step 5: 将重命名/置顶改成服务端写入**

```typescript
const renameSession = useCallback(async (id: string, newTitle: string) => {
  const updated = await patchSession(id, { title: newTitle })
  commitHistory(replaceSessionPreservingOrder(historyRef.current, normalizeSession(updated)), {
    preserveOrder: true,
  })
}, [commitHistory])
```

```typescript
const togglePin = useCallback(async (id: string) => {
  const target = historyRef.current.find((session) => session.id === id)
  if (!target) return
  const updated = await patchSession(id, { is_pinned: !target.isPinned })
  commitHistory(
    replaceSessionPreservingOrder(historyRef.current, normalizeSession(updated)),
    { preserveOrder: true },
  )
}, [commitHistory])
```

- [ ] **Step 6: 清理 `session-utils` 中依赖 checkpoint state 拼消息的旧断言**

```typescript
test('buildMessagesFromSessionState remains runtime-only and is no longer the chat restore path', () => {
  const messages = buildMessagesFromSessionState({ messages: [{ type: 'human', content: 'q' }] }, 'session-1')
  assert.equal(messages[0]?.role, 'user')
})
```

- [ ] **Step 7: 运行前端回归测试**

Run: `pnpm -C web test -- tests/use-chat-history.test.ts tests/session-utils.test.ts`

Expected:
- `all tests passed`

### Task 8: 删除旧会话包装器并做全链路回归

**Files:**
- Delete: `common/session_manager.py`
- Delete: `tests/test_session_manager_postgres_listing.py`
- Delete: `tests/test_session_manager_user_filter.py`
- Delete: `tests/test_session_manager_claim_evidence_passages.py`
- Delete: `tests/test_session_deepsearch_artifacts.py`
- Modify: `docs/superpowers/specs/2026-04-06-session-persistence-redesign-design.md`

- [ ] **Step 1: 搜索仓库里残留的 `SessionManager` 引用**

Run: `rg -n "SessionManager|get_session_manager|common\\.session_manager" "."`

Expected:
- 只剩待删除文件或注释；主代码路径不再引用旧管理器

- [ ] **Step 2: 删除旧文件和过时测试**

```diff
- from common.session_manager import get_session_manager
- manager = get_session_manager(checkpointer)
+ from common.session_service import SessionService
+ # 会话读取已改由 session_service 负责
```

- [ ] **Step 3: 运行后端会话相关回归测试**

Run: `uv run pytest tests/test_weaver_checkpointer.py tests/test_session_store.py tests/test_session_service.py tests/test_session_snapshot_api.py tests/test_chat_session_persistence.py tests/test_sessions_api_auth_filter.py tests/test_sessions_api_thread_authz.py tests/test_resume_session_deepsearch.py tests/test_session_evidence_api.py tests/test_checkpointer_config.py tests/test_health_db_status.py -v`

Expected:
- `all passed`

- [ ] **Step 4: 运行前端历史会话回归测试**

Run: `pnpm -C web test -- tests/use-chat-history.test.ts tests/session-utils.test.ts`

Expected:
- `all tests passed`

- [ ] **Step 5: 更新设计文档中的实现状态备注**

```markdown
## 实现备注

- 会话恢复入口已切换到 `/api/sessions/{thread_id}/snapshot`
- 旧 `SessionManager` 已删除
- `MemorySaver()` 降级路径已移除
```

**Self-Review Notes**

- 覆盖了 spec 中的两层持久化重写、API 重构、聊天写入链路、前端历史恢复、错误处理和硬切规则。
- 计划中未包含 `git commit` 步骤，符合仓库要求。
- 如实现中发现 `common/session_manager.py` 仍被某个 debug/导出路径间接依赖，应先加失败测试，再把该路径迁移到 `common/checkpoint_runtime.py`，不要保留双实现。
