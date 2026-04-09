from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.core.chat_context import (
    build_recent_runtime_messages,
    build_short_term_snapshot,
    normalize_short_term_context,
    short_term_context_fetch_limit,
)
from common.checkpoint_runtime import get_thread_runtime_state


class SessionService:
    def __init__(self, *, store: Any, checkpointer: Any, memory_service: Any = None):
        self.store = store
        self.checkpointer = checkpointer
        self.memory_service = memory_service

    async def load_snapshot(self, thread_id: str) -> dict[str, Any] | None:
        snapshot = await self.store.get_snapshot(thread_id)
        if not snapshot:
            return None
        runtime_state = await get_thread_runtime_state(self.checkpointer, thread_id)
        return {
            **snapshot,
            "pending_interrupt": (
                runtime_state.get("__interrupt__") if isinstance(runtime_state, dict) else None
            ),
            "can_resume": bool(runtime_state),
        }

    async def update_session_metadata(
        self,
        thread_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        return await self.store.update_session_metadata(thread_id, updates)

    async def list_sessions(
        self,
        *,
        limit: int,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        owner = str(user_id or "").strip() or None
        return await self.store.list_sessions(user_id=owner, limit=limit)

    async def get_session(self, thread_id: str) -> dict[str, Any] | None:
        return await self.store.get_session(thread_id)

    async def list_messages(self, thread_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if hasattr(self.store, "list_messages"):
            return await self.store.list_messages(thread_id, limit=limit)

        snapshot = await self.store.get_snapshot(thread_id)
        if not snapshot:
            return []
        messages = snapshot.get("messages")
        if not isinstance(messages, list):
            return []
        return list(messages[-limit:]) if limit > 0 else []

    async def _refresh_context_snapshot(self, thread_id: str) -> dict[str, Any] | None:
        get_snapshot = getattr(self.store, "get_snapshot", None)
        update_metadata = getattr(self.store, "update_session_metadata", None)
        if not callable(get_snapshot) or not callable(update_metadata):
            return None

        snapshot = await get_snapshot(thread_id)
        session = snapshot.get("session") if isinstance(snapshot, dict) else None
        messages = snapshot.get("messages") if isinstance(snapshot, dict) else None
        if not isinstance(session, dict) or not isinstance(messages, list):
            return None

        context_snapshot = build_short_term_snapshot(
            messages,
            previous_snapshot=session.get("context_snapshot"),
        )
        updated = await update_metadata(thread_id, {"context_snapshot": context_snapshot})
        if isinstance(updated, dict):
            current = updated.get("context_snapshot")
            return current if isinstance(current, dict) else None
        return context_snapshot

    async def load_chat_runtime_context(self, thread_id: str) -> dict[str, Any]:
        messages = await self.list_messages(
            thread_id,
            limit=short_term_context_fetch_limit(),
        )
        session = await self.get_session(thread_id)
        context_snapshot = normalize_short_term_context(
            (session or {}).get("context_snapshot"),
        )
        if not context_snapshot.get("updated_at") and messages:
            context_snapshot = build_short_term_snapshot(
                messages,
                previous_snapshot=context_snapshot,
            )
        return {
            "history_messages": build_recent_runtime_messages(messages),
            "short_term_context": context_snapshot,
        }

    async def start_session_run(
        self,
        *,
        thread_id: str,
        user_id: str,
        route: str,
        initial_user_message: str,
    ) -> None:
        created_at = datetime.now(UTC).isoformat()
        title = str(initial_user_message or "").strip()[:40] or "New Conversation"
        existing = await self.store.get_session(thread_id)
        if existing:
            await self.store.update_session_metadata(
                thread_id,
                {
                    "status": "running",
                    "route": route,
                },
            )
        else:
            await self.store.create_session(
                thread_id=thread_id,
                user_id=user_id,
                title=title,
                route=route,
                status="running",
            )
        await self.store.append_message(
            thread_id=thread_id,
            role="user",
            content=initial_user_message,
            created_at=created_at,
        )
        await self._refresh_context_snapshot(thread_id)
        if self.memory_service is not None:
            self.memory_service.ingest_user_message(
                user_id=user_id,
                text=initial_user_message,
                source_kind="chat",
                thread_id=thread_id,
            )

    async def append_user_message(self, *, thread_id: str, content: str) -> None:
        if not str(content or "").strip():
            return
        session = await self.store.get_session(thread_id)
        await self.store.append_message(
            thread_id=thread_id,
            role="user",
            content=content,
            created_at=datetime.now(UTC).isoformat(),
        )
        await self.store.update_session_metadata(
            thread_id,
            {
                "status": "running",
            },
        )
        await self._refresh_context_snapshot(thread_id)
        owner = str((session or {}).get("user_id") or "").strip()
        if self.memory_service is not None and owner:
            self.memory_service.ingest_user_message(
                user_id=owner,
                text=content,
                source_kind="chat_resume",
                thread_id=thread_id,
            )

    async def finalize_assistant_message(
        self,
        *,
        thread_id: str,
        content: str,
        status: str,
        sources: list[dict[str, Any]] | None = None,
        tool_invocations: list[dict[str, Any]] | None = None,
        process_events: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        created_at = datetime.now(UTC).isoformat()
        if str(content or "").strip():
            await self.store.append_message(
                thread_id=thread_id,
                role="assistant",
                content=content,
                sources=sources,
                tool_invocations=tool_invocations,
                process_events=process_events,
                metrics=metrics,
                created_at=created_at,
                completed_at=created_at,
            )
        await self.store.update_session_metadata(
            thread_id,
            {
                "status": status,
                "summary": str(content or "").strip()[:140],
            },
        )
        await self._refresh_context_snapshot(thread_id)

    async def delete_session(self, thread_id: str) -> dict[str, Any]:
        await self.store.delete_session(thread_id)
        checkpoint_cleanup_pending = False
        if self.checkpointer is not None:
            if hasattr(self.checkpointer, "adelete_thread"):
                await self.checkpointer.adelete_thread(thread_id)
            elif hasattr(self.checkpointer, "adelete"):
                await self.checkpointer.adelete({"configurable": {"thread_id": thread_id}})
            elif hasattr(self.checkpointer, "delete_thread"):
                self.checkpointer.delete_thread(thread_id)
            elif hasattr(self.checkpointer, "delete"):
                self.checkpointer.delete({"configurable": {"thread_id": thread_id}})
            else:
                checkpoint_cleanup_pending = True
        return {
            "success": True,
            "message": f"Session {thread_id} deleted",
            "checkpoint_cleanup_pending": checkpoint_cleanup_pending,
        }
