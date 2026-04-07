from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from common.persistence_schema import MEMORY_DDL_STATEMENTS


class MemoryStore:
    def __init__(self, conn: Any):
        self.conn = conn

    def setup(self) -> None:
        for statement in MEMORY_DDL_STATEMENTS:
            self.conn.execute(statement)

    def _fetchone(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        return self._normalize_row(row) if row else None

    def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [self._normalize_row(row) for row in rows]

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {str(key): self._normalize_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._normalize_value(item) for item in value]
        return value

    def _normalize_row(self, row: Any) -> dict[str, Any]:
        return {
            str(key): self._normalize_value(value)
            for key, value in dict(row).items()
        }

    def upsert_entry(
        self,
        *,
        user_id: str,
        memory_type: str,
        content: str,
        normalized_key: str,
        source_kind: str,
        source_thread_id: str = "",
        source_message: str = "",
        importance: int = 50,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry_id = uuid.uuid4()
        return self._fetchone(
            """
            INSERT INTO memory_entries (
                id,
                user_id,
                memory_type,
                content,
                normalized_key,
                source_kind,
                source_thread_id,
                source_message,
                importance,
                status,
                metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s)
            ON CONFLICT (user_id, memory_type, normalized_key)
            DO UPDATE SET
                content = EXCLUDED.content,
                source_kind = EXCLUDED.source_kind,
                source_thread_id = EXCLUDED.source_thread_id,
                source_message = EXCLUDED.source_message,
                importance = GREATEST(memory_entries.importance, EXCLUDED.importance),
                status = 'active',
                invalidated_at = NULL,
                invalidation_reason = '',
                metadata = COALESCE(memory_entries.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING *
            """,
            (
                entry_id,
                user_id,
                memory_type,
                content,
                normalized_key,
                source_kind,
                source_thread_id,
                source_message,
                int(importance),
                Jsonb(metadata if isinstance(metadata, dict) else {}),
            ),
        ) or {}

    def list_entries(
        self,
        *,
        user_id: str,
        limit: int = 50,
        status: str | None = None,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["user_id = %s"]
        params: list[Any] = [user_id]
        if status:
            clauses.append("status = %s")
            params.append(status)
        if memory_type:
            clauses.append("memory_type = %s")
            params.append(memory_type)
        params.append(int(limit))
        return self._fetchall(
            f"""
            SELECT *
            FROM memory_entries
            WHERE {' AND '.join(clauses)}
            ORDER BY importance DESC, updated_at DESC
            LIMIT %s
            """,
            tuple(params),
        )

    def invalidate_entry(
        self,
        *,
        user_id: str,
        entry_id: str,
        reason: str,
    ) -> dict[str, Any] | None:
        return self._fetchone(
            """
            UPDATE memory_entries
            SET
                status = 'invalidated',
                invalidated_at = NOW(),
                invalidation_reason = %s,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (reason, entry_id, user_id),
        )

    def delete_entry(self, *, user_id: str, entry_id: str) -> dict[str, Any] | None:
        return self._fetchone(
            """
            DELETE FROM memory_entries
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (entry_id, user_id),
        )

    def touch_entries(self, *, entry_ids: list[str]) -> None:
        if not entry_ids:
            return
        self._execute(
            """
            UPDATE memory_entries
            SET
                retrieval_count = retrieval_count + 1,
                last_retrieved_at = NOW()
            WHERE id = ANY(%s)
            """,
            (entry_ids,),
        )

    def record_event(
        self,
        *,
        user_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str = "",
        reason: str = "",
        payload: dict[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        event_id = uuid.uuid4()
        return self._fetchone(
            """
            INSERT INTO memory_entry_events (
                id,
                entry_id,
                user_id,
                event_type,
                actor_type,
                actor_id,
                reason,
                payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                event_id,
                entry_id,
                user_id,
                event_type,
                actor_type,
                actor_id,
                reason,
                Jsonb(payload if isinstance(payload, dict) else {}),
            ),
        ) or {}

    def list_events(
        self,
        *,
        user_id: str,
        entry_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if entry_id:
            return self._fetchall(
                """
                SELECT *
                FROM memory_entry_events
                WHERE user_id = %s AND entry_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, entry_id, int(limit)),
            )
        return self._fetchall(
            """
            SELECT *
            FROM memory_entry_events
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, int(limit)),
        )

    def get_migration_status(self, *, user_id: str, source: str) -> dict[str, Any] | None:
        return self._fetchone(
            """
            SELECT *
            FROM memory_user_migrations
            WHERE user_id = %s AND source = %s
            """,
            (user_id, source),
        )

    def list_migration_statuses(self, *, user_id: str) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT *
            FROM memory_user_migrations
            WHERE user_id = %s
            ORDER BY source ASC
            """,
            (user_id,),
        )

    def upsert_migration_status(
        self,
        *,
        user_id: str,
        source: str,
        status: str,
        imported_count: int = 0,
        skipped_count: int = 0,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._fetchone(
            """
            INSERT INTO memory_user_migrations (
                user_id,
                source,
                status,
                imported_count,
                skipped_count,
                details
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, source)
            DO UPDATE SET
                status = EXCLUDED.status,
                imported_count = EXCLUDED.imported_count,
                skipped_count = EXCLUDED.skipped_count,
                details = EXCLUDED.details,
                updated_at = NOW()
            RETURNING *
            """,
            (
                user_id,
                source,
                status,
                int(imported_count),
                int(skipped_count),
                Jsonb(details if isinstance(details, dict) else {}),
            ),
        ) or {}


def create_memory_store(database_url: str) -> MemoryStore:
    if not database_url:
        raise ValueError("database_url is required to initialize the memory store.")

    try:
        conn = psycopg.connect(
            database_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Postgres for memory store: {e}") from e

    store = MemoryStore(conn)
    store.setup()
    return store
