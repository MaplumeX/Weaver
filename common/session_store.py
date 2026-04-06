from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from common.persistence_schema import SESSION_DDL_STATEMENTS


class SessionStore:
    def __init__(self, conn: Any):
        self.conn = conn

    async def setup(self) -> None:
        for statement in SESSION_DDL_STATEMENTS:
            await self.conn.execute(statement)

    async def _fetchrow(self, sql: str, params: tuple[Any, ...]) -> Any:
        if hasattr(self.conn, "fetchrow"):
            return await self.conn.fetchrow(sql, params)
        cursor = await self.conn.execute(sql, params)
        return await cursor.fetchone()

    async def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[Any]:
        if hasattr(self.conn, "fetch"):
            return list(await self.conn.fetch(sql, params))
        cursor = await self.conn.execute(sql, params)
        return list(await cursor.fetchall())

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

    async def create_session(
        self,
        *,
        thread_id: str,
        user_id: str,
        title: str,
        route: str,
        status: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO sessions (thread_id, user_id, title, route, status) VALUES (%s, %s, %s, %s, %s)",
            (thread_id, user_id, title, route, status),
        )

    async def append_message(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        created_at: str,
        **payload: Any,
    ) -> None:
        message_id = uuid.uuid4()
        attachments = payload.get("attachments")
        sources = payload.get("sources")
        tool_invocations = payload.get("tool_invocations")
        process_events = payload.get("process_events")
        metrics = payload.get("metrics")
        completed_at = payload.get("completed_at")
        await self.conn.execute(
            "INSERT INTO session_messages ("
            "id, thread_id, seq, role, content, attachments, sources, tool_invocations, "
            "process_events, metrics, created_at, completed_at"
            ") VALUES ("
            "%s, %s, COALESCE((SELECT MAX(seq) + 1 FROM session_messages WHERE thread_id = %s), 1), "
            "%s, %s, %s, %s, %s, %s, %s, %s, %s"
            ")",
            (
                message_id,
                thread_id,
                thread_id,
                role,
                content,
                Jsonb(attachments if isinstance(attachments, list) else []),
                Jsonb(sources if isinstance(sources, list) else []),
                Jsonb(tool_invocations if isinstance(tool_invocations, list) else []),
                Jsonb(process_events if isinstance(process_events, list) else []),
                Jsonb(metrics if isinstance(metrics, dict) else {}),
                created_at,
                completed_at,
            ),
        )

    async def get_snapshot(self, thread_id: str) -> dict[str, Any]:
        session = await self._fetchrow(
            "SELECT thread_id, user_id, title, summary, status, route, is_pinned, tags, created_at, updated_at "
            "FROM sessions WHERE thread_id = %s",
            (thread_id,),
        )
        if not session:
            return {}
        messages = await self._fetchall(
            "SELECT id, role, content, attachments, sources, tool_invocations, process_events, metrics, created_at, completed_at "
            "FROM session_messages WHERE thread_id = %s ORDER BY seq ASC",
            (thread_id,),
        )
        return {
            "session": self._normalize_row(session),
            "messages": [self._normalize_row(message) for message in messages],
        }

    async def get_session(self, thread_id: str) -> dict[str, Any] | None:
        session = await self._fetchrow(
            "SELECT thread_id, user_id, title, summary, status, route, is_pinned, tags, created_at, updated_at "
            "FROM sessions WHERE thread_id = %s",
            (thread_id,),
        )
        return self._normalize_row(session) if session else None

    async def list_sessions(self, *, user_id: str | None = None, limit: int) -> list[dict[str, Any]]:
        owner = str(user_id or "").strip()
        if owner:
            rows = await self._fetchall(
                "SELECT thread_id, user_id, title, summary, status, route, is_pinned, tags, created_at, updated_at "
                "FROM sessions WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s",
                (owner, limit),
            )
        else:
            rows = await self._fetchall(
                "SELECT thread_id, user_id, title, summary, status, route, is_pinned, tags, created_at, updated_at "
                "FROM sessions ORDER BY updated_at DESC LIMIT %s",
                (limit,),
            )
        return [self._normalize_row(row) for row in rows]

    async def update_session_metadata(self, thread_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        if not updates:
            snapshot = await self.get_snapshot(thread_id)
            return snapshot.get("session") if snapshot else None

        assignments: list[str] = []
        values: list[Any] = []
        for field in ("title", "summary", "is_pinned", "tags", "route", "status"):
            if field not in updates:
                continue
            assignments.append(f"{field} = %s")
            value = updates[field]
            if field == "tags":
                value = Jsonb(value)
            values.append(value)

        if not assignments:
            snapshot = await self.get_snapshot(thread_id)
            return snapshot.get("session") if snapshot else None

        values.append(thread_id)
        await self.conn.execute(
            f"UPDATE sessions SET {', '.join(assignments)} WHERE thread_id = %s",
            tuple(values),
        )
        snapshot = await self.get_snapshot(thread_id)
        return snapshot.get("session") if snapshot else None

    async def delete_session(self, thread_id: str) -> bool:
        await self.conn.execute("DELETE FROM session_messages WHERE thread_id = %s", (thread_id,))
        await self.conn.execute("DELETE FROM sessions WHERE thread_id = %s", (thread_id,))
        return True


async def create_session_store(database_url: str) -> SessionStore:
    if not database_url:
        raise ValueError("database_url is required to initialize the session store.")

    try:
        conn = await psycopg.AsyncConnection.connect(
            database_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Postgres for session store: {e}") from e

    store = SessionStore(conn)
    await store.setup()
    return store
