from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from agent.deep_research.artifacts.public_artifacts import (
    build_public_deep_research_artifacts_from_state,
)
from common.checkpoint_ops import aget_checkpoint_tuple


async def get_thread_runtime_state(checkpointer: Any, thread_id: str) -> dict[str, Any] | None:
    checkpoint_tuple = await aget_checkpoint_tuple(checkpointer, {"configurable": {"thread_id": thread_id}})
    if not checkpoint_tuple:
        return None
    state = checkpoint_tuple.checkpoint.get("channel_values", {})
    return state if isinstance(state, dict) else None


def extract_deep_research_artifacts(state: dict[str, Any] | None) -> dict[str, Any]:
    return build_public_deep_research_artifacts_from_state(state or {})


async def can_resume_thread(checkpointer: Any, thread_id: str) -> tuple[bool, str]:
    state = await get_thread_runtime_state(checkpointer, thread_id)
    if not state:
        return False, "Session not found"

    status = str(state.get("status") or "").strip()
    if state.get("is_complete") or status == "completed":
        return False, "Session already completed"
    if status == "deleted":
        return False, "Session has been deleted"
    if status == "running":
        return False, "Session is currently running"
    return True, "Session can be resumed"


async def build_resume_state(
    checkpointer: Any,
    thread_id: str,
    *,
    additional_input: str | None = None,
    update_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    state = await get_thread_runtime_state(checkpointer, thread_id)
    if not state:
        return None

    restored = deepcopy(state)
    artifacts = extract_deep_research_artifacts(state)
    if isinstance(update_state, dict):
        restored.update(update_state)
    if additional_input:
        restored["resume_input"] = additional_input
    if artifacts:
        restored["deep_research_artifacts"] = deepcopy(artifacts)
    restored["resumed_from_checkpoint"] = True
    restored["resumed_at"] = datetime.utcnow().isoformat()
    return restored
