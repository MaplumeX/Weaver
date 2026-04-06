from __future__ import annotations


CHECKPOINT_DDL_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS graph_checkpoints (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        parent_checkpoint_id TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        checkpoint_type TEXT NOT NULL,
        checkpoint_payload BYTEA NOT NULL,
        metadata_type TEXT NOT NULL,
        metadata_payload BYTEA NOT NULL,
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
    )
    """,
    """
    ALTER TABLE graph_checkpoints
    ADD COLUMN IF NOT EXISTS checkpoint_type TEXT
    """,
    """
    ALTER TABLE graph_checkpoints
    ADD COLUMN IF NOT EXISTS metadata_type TEXT
    """,
    """
    CREATE TABLE IF NOT EXISTS graph_checkpoint_writes (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        task_path TEXT NOT NULL DEFAULT '',
        write_idx INTEGER NOT NULL,
        channel TEXT NOT NULL,
        value_type TEXT NOT NULL,
        value_payload BYTEA NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
    )
    """,
    """
    ALTER TABLE graph_checkpoint_writes
    ADD COLUMN IF NOT EXISTS value_type TEXT
    """,
)


SESSION_DDL_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS sessions (
        thread_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        route TEXT NOT NULL,
        is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
        tags JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_messages (
        id UUID PRIMARY KEY,
        thread_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
        sources JSONB NOT NULL DEFAULT '[]'::jsonb,
        tool_invocations JSONB NOT NULL DEFAULT '[]'::jsonb,
        process_events JSONB NOT NULL DEFAULT '[]'::jsonb,
        metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ NULL
    )
    """,
)
