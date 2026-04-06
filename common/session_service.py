from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from common.checkpoint_runtime import get_thread_runtime_state


class SessionService:
    def __init__(self, *, store: Any, checkpointer: Any):
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

    async def update_session_metadata(self, thread_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return await self.store.update_session_metadata(thread_id, updates)

    async def list_sessions(self, *, limit: int, user_id: str | None = None) -> list[dict[str, Any]]:
        owner = str(user_id or "").strip() or None
        return await self.store.list_sessions(user_id=owner, limit=limit)

    async def get_session(self, thread_id: str) -> dict[str, Any] | None:
        return await self.store.get_session(thread_id)

    async def start_session_run(
        self,
        *,
        thread_id: str,
        user_id: str,
        route: str,
        initial_user_message: str,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
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

    async def append_user_message(self, *, thread_id: str, content: str) -> None:
        if not str(content or "").strip():
            return
        await self.store.append_message(
            thread_id=thread_id,
            role="user",
            content=content,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self.store.update_session_metadata(
            thread_id,
            {
                "status": "running",
            },
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
        created_at = datetime.now(timezone.utc).isoformat()
        if str(content or "").strip():
            await self.store.append_message(
                thread_id=thread_id,
                role="assistant",
                content=content,
                created_at=created_at,
            )
        await self.store.update_session_metadata(
            thread_id,
            {
                "status": status,
                "summary": str(content or "").strip()[:140],
            },
        )

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
