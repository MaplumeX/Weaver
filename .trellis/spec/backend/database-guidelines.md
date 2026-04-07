# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

This project does not use a single ORM-centric data layer.

Current persistence patterns are:

- PostgreSQL via `psycopg` for LangGraph checkpoints and session persistence.
- LangGraph store backends (`PostgresStore` or `RedisStore`) for long-term
  memory, selected by configuration.
- ChromaDB for RAG vector storage.
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
- Avoid destructive migrations in startup code.
- If a breaking storage change is unavoidable, stage it through additive schema
  changes plus read-path compatibility code first.

---

## Naming Conventions

- Table names are lowercase snake case: `sessions`, `session_messages`,
  `graph_checkpoints`, `graph_checkpoint_writes`.
- Column names are lowercase snake case.
- `thread_id` is the primary partition key across session/checkpoint tables.
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

## Examples

- `common/persistence_schema.py`: source of truth for runtime-managed Postgres
  DDL.
- `common/session_store.py`: direct SQL, `Jsonb`, and row normalization.
- `common/agents_store.py`: file-backed persistence chosen explicitly to avoid
  migrations.
- `tests/test_checkpointer_config.py`: regression tests that lock in Postgres
  connection settings.
