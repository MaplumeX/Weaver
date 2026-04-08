# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

This project does not use a single ORM-centric data layer.

Current persistence patterns are:

- PostgreSQL via `psycopg` for LangGraph checkpoints and session persistence.
- PostgreSQL via project-owned adapters for long-term memory
  (`common/memory_store.py`), even when `MEMORY_STORE_BACKEND` is set for
  compatibility.
- JSON files for lightweight configuration/state where avoiding schema churn is
  more valuable than centralizing everything in SQL.

There is no Alembic or SQLAlchemy migration flow in the current codebase.
Document and extend the storage backend that already owns the data.

---

## Query Patterns

- Use `psycopg` directly with `%s` placeholders and tuple parameters.
- Keep SQL inside the storage adapter that owns the tables instead of building
  queries inside FastAPI endpoints.
- Use `psycopg.rows.dict_row` when the result needs to be accessed by column
  name.
- Normalize database values before returning them to the API layer. The current
  session store converts `UUID`, `datetime`, `date`, `time`, and `Decimal`
  values into JSON-friendly forms.
- Use `Jsonb(...)` for structured payload columns instead of hand-serializing
  JSON strings.

Examples:

- `common/session_store.py` inserts and fetches session rows with positional
  parameters.
- `common/memory_store.py` owns long-term memory tables, query helpers, and
  event logging.
- `agent/runtime/graph.py` creates the Postgres checkpointer with
  `dict_row`, `autocommit=True`, and `prepare_threshold=0`.
- `main.py` keeps `_init_store()` as the composition point, while the actual
  storage logic stays in dedicated store objects.

---

## Migrations

- There is no external migration tool today.
- Schema setup is runtime-managed through idempotent DDL statements in
  `common/persistence_schema.py`.
- New schema changes should be additive and safe to run repeatedly:
  `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, and
  compatible defaults.
- Keep DDL close to the owning persistence adapter and execute it from that
  adapter's `setup()` method.
- For lightweight state such as agent profiles, prefer the existing JSON-file
  storage pattern over introducing a database migration burden.

What this means in practice:

- Extend `CHECKPOINT_DDL_STATEMENTS` or `SESSION_DDL_STATEMENTS` when changing
  checkpoint/session persistence.
- Extend `MEMORY_DDL_STATEMENTS` when changing long-term memory persistence.
- When removing a runtime-managed DDL statement from one of the `*_DDL_STATEMENTS`
  tuples, delete the entire tuple item and then run a schema smoke check to
  catch dangling delimiters or malformed SQL strings before startup.
- Avoid destructive migrations in startup code.
- If a breaking storage change is unavoidable, stage it through additive schema
  changes plus read-path compatibility code first.

---

## Naming Conventions

- Table names are lowercase snake case: `sessions`, `session_messages`,
  `graph_checkpoints`, `graph_checkpoint_writes`, `memory_entries`,
  `memory_entry_events`, `memory_user_migrations`.
- Column names are lowercase snake case.
- `thread_id` is the primary partition key across session/checkpoint tables.
- `user_id` is the primary partition key for long-term memory tables.
- Timestamps use `TIMESTAMPTZ`.
- Structured arrays/objects that must be queryable or preserved as JSON use
  `JSONB`.
- Serialized checkpoint payloads use typed binary columns rather than opaque
  string blobs.

---

## Common Mistakes

- Do not assume SQLAlchemy or Alembic exists here.
- Do not build SQL with string interpolation; use placeholders and parameters.
- Do not put storage concerns into `main.py` route handlers.
- Do not introduce a database table when a JSON file is the established pattern
  for small local state (`common/agents_store.py`).
- Do not make startup DDL destructive; startup schema management must stay
  idempotent.

## Scenario: LangGraph Checkpoint Persistence For Interrupt Resume

### 1. Scope / Trigger

- Trigger: changing `common/weaver_checkpointer.py`, `common/checkpoint_ops.py`,
  or any resume/status endpoint that reads LangGraph checkpoints.
- This is an infra and cross-layer contract:
  LangGraph runtime -> custom Postgres saver -> `main.py` interrupt APIs ->
  frontend resume flow.
- Treat the saver as a compatibility layer with LangGraph's Postgres saver, not
  as an arbitrary project-local schema adapter.

### 2. Signatures

- `common/weaver_checkpointer.py`
  - `WeaverPostgresCheckpointer.aget_tuple(config: dict[str, Any]) -> CheckpointTuple | None`
  - `WeaverPostgresCheckpointer.get_tuple(config: dict[str, Any]) -> CheckpointTuple | None`
  - `WeaverPostgresCheckpointer.aput_writes(config, writes, task_id, task_path="") -> None`
  - `WeaverPostgresCheckpointer.put_writes(config, writes, task_id, task_path="") -> None`
- `main.py`
  - `POST /api/interrupt/resume`
  - `GET /api/interrupt/{thread_id}/status`

### 3. Contracts

- Latest checkpoint lookup for a thread must use:
  `ORDER BY checkpoint_id DESC LIMIT 1`
  instead of `created_at DESC`.
- Reason: LangGraph checkpoint IDs are monotonically increasing and are the
  source of truth for resume ordering.
- `config["configurable"]` must preserve:
  - `thread_id`
  - `checkpoint_ns`
  - `checkpoint_id` when resuming an exact checkpoint
- `pending_writes` must deserialize into:
  `(task_id, channel, value)`
- Special LangGraph channels use fixed write indexes from
  `langgraph.checkpoint.base.WRITES_IDX_MAP`:
  - `__error__`
  - `__scheduled__`
  - `__interrupt__`
  - `__resume__`
- When all writes in a batch are special channels, the saver must upsert
  conflicting rows instead of ignoring them, so the latest interrupt/resume
  payload replaces the stale one for the same `(thread_id, checkpoint_ns,
  checkpoint_id, task_id, write_idx)`.
- `/api/interrupt/resume` and `/api/interrupt/{thread_id}/status` depend on the
  latest `__interrupt__` payload for the thread. Stale writes will surface the
  wrong prompt to the user.

### 4. Validation & Error Matrix

| Change Area | Required Behavior | If Broken | Typical Symptom |
|-------------|-------------------|-----------|-----------------|
| Latest checkpoint query | Sort by `checkpoint_id DESC` | Reads an older checkpoint | Resume/status returns an outdated interrupt |
| Special write persistence | Use `WRITES_IDX_MAP` for special channels | Later special writes collide on wrong indexes or become append-only | Old `clarify` prompt survives after `scope_review` is produced |
| Special write conflict handling | `DO UPDATE` for special channels | Stale row is kept | Same clarify question appears twice after user already answered |
| Generic write conflict handling | Keep non-special writes append-only / idempotent | Intermediate writes are overwritten unexpectedly | Runtime bookkeeping becomes inconsistent |

### 5. Good/Base/Bad Cases

- Good:
  `deep_research_clarify` is written first, then the same task writes
  `deep_research_scope_review`; status/resume returns only
  `deep_research_scope_review`.
- Base:
  a single interrupt exists for the latest checkpoint; `aget_tuple()` and
  `get_tuple()` both return that checkpoint's writes.
- Bad:
  an older clarify interrupt is inserted earlier, a newer scope-review interrupt
  is written later, but latest-checkpoint lookup or special-write persistence
  still returns the clarify interrupt.

### 6. Tests Required

- `tests/test_weaver_checkpointer.py`
  - assert latest checkpoint selection uses highest `checkpoint_id`
  - assert special `__interrupt__` writes overwrite stale values for the same
    task/checkpoint
- `tests/test_deepsearch_multi_agent_runtime.py`
  - keep coverage that one clarify answer advances to `scope_review`
- Assertion points:
  - `checkpoint_tuple.checkpoint["id"]`
  - `checkpoint_tuple.pending_writes`
  - final interrupt checkpoint name (`deep_research_scope_review`, not stale
    `deep_research_clarify`)

### 7. Wrong vs Correct

#### Wrong

```python
row = await self._fetchrow(
    "SELECT * FROM graph_checkpoints WHERE thread_id = %s AND checkpoint_ns = %s "
    "ORDER BY created_at DESC LIMIT 1",
    (thread_id, checkpoint_ns),
)

await self.conn.execute(
    "... ON CONFLICT (...) DO NOTHING",
    (..., write_idx, "__interrupt__", value_type, value_payload),
)
```

#### Correct

```python
row = await self._fetchrow(
    "SELECT * FROM graph_checkpoints WHERE thread_id = %s AND checkpoint_ns = %s "
    "ORDER BY checkpoint_id DESC LIMIT 1",
    (thread_id, checkpoint_ns),
)

write_idx = WRITES_IDX_MAP.get(channel, idx)

await self.conn.execute(
    "... ON CONFLICT (...) DO UPDATE SET "
    "channel = EXCLUDED.channel, "
    "value_type = EXCLUDED.value_type, "
    "value_payload = EXCLUDED.value_payload",
    (..., write_idx, channel, value_type, value_payload),
)
```

## Scenario: SessionStore Shared Async Connection Concurrency

### 1. Scope / Trigger

- Trigger: changing `common/session_store.py`, `common/session_service.py`, or
  `main.py` request paths that issue session persistence reads/writes during
  chat handling.
- This is an infra contract between:
  FastAPI request concurrency -> shared `SessionStore` instance ->
  shared `psycopg.AsyncConnection`.
- Treat the `SessionStore` connection as a shared runtime resource, not a
  per-request isolated cursor manager.

### 2. Signatures

- `common/session_store.py`
  - `SessionStore.get_session(thread_id: str) -> dict[str, Any] | None`
  - `SessionStore.get_snapshot(thread_id: str) -> dict[str, Any]`
  - `SessionStore.list_messages(thread_id: str, *, limit: int = 50) -> list[dict[str, Any]]`
  - `SessionStore.create_session(...) -> None`
  - `SessionStore.append_message(...) -> None`
  - `SessionStore.update_session_metadata(...) -> dict[str, Any] | None`
- `main.py`
  - `POST /api/chat`
  - `GET /api/sessions/{thread_id}/snapshot`
  - any request path that reuses the global `session_service`

### 3. Contracts

- A shared `psycopg.AsyncConnection` cannot execute multiple commands at the
  same time.
- `SessionStore` must serialize access to its shared async connection for all
  execute/fetch operations.
- Concurrent chat/session requests must not surface:
  `psycopg.OperationalError: another command is already in progress`.
- Read helpers and write helpers must use the same serialization mechanism so
  mixed read/write interleaving is also safe.
- New helper methods added to `SessionStore` must go through the same guarded
  connection path instead of calling `self.conn.execute(...)` directly.

### 4. Validation & Error Matrix

| Change Area | Required Behavior | If Broken | Typical Symptom |
|-------------|-------------------|-----------|-----------------|
| Shared async connection access | All DB commands are serialized | Concurrent requests overlap on one connection | `/api/chat` returns 500 with `another command is already in progress` |
| New read helpers | Use the guarded fetch path | One new helper bypasses serialization | Only follow-up history loads fail under load |
| Mixed read/write traffic | Reads and writes share one guard | Read path is safe but write path still races | Session create succeeds, append or metadata update fails intermittently |

### 5. Good/Base/Bad Cases

- Good:
  two concurrent `get_session()` calls on one shared `SessionStore` both
  succeed without raising a concurrency error.
- Base:
  a single request reads or writes session rows and behaves exactly as before.
- Bad:
  one request enters `get_session()` while another request is still using the
  same async connection, and the second request crashes with
  `another command is already in progress`.

### 6. Tests Required

- `tests/test_session_store.py`
  - assert concurrent reads on one shared async connection are serialized
  - keep snapshot/list-message persistence coverage intact
- `tests/test_chat_session_persistence.py`
  - keep coverage that `/api/chat` persists session start/final assistant flows
- Assertion points:
  - no raised concurrency error
  - returned session payloads stay correct
  - recent message ordering remains stable

### 7. Wrong vs Correct

#### Wrong

```python
async def _fetchrow(self, sql, params):
    return await self.conn.fetchrow(sql, params)
```

#### Correct

```python
async def _fetchrow(self, sql, params):
    async with self._conn_lock:
        return await self.conn.fetchrow(sql, params)
```

## Examples

- `common/persistence_schema.py`: source of truth for runtime-managed Postgres
  DDL.
- `common/session_store.py`: direct SQL, `Jsonb`, and row normalization.
- `common/memory_store.py`: direct SQL for memory entries, events, and migration
  status.
- `common/agents_store.py`: file-backed persistence chosen explicitly to avoid
  migrations.
- `tests/test_checkpointer_config.py`: regression tests that lock in Postgres
  connection settings.
