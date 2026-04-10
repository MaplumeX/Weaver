"""Public Deep Research artifact adapters for the lightweight runtime contract."""

from __future__ import annotations

from typing import Any

from agent.deep_research.artifacts.public_payload import (
    _build_lightweight_public_artifacts,
    _filter_public_artifacts,
)
from agent.deep_research.state import read_deep_runtime_snapshot, resolve_deep_runtime_mode


def build_public_deep_research_artifacts(
    *,
    task_queue: dict[str, Any] | None,
    artifact_store: dict[str, Any] | None,
    research_topology: dict[str, Any] | None = None,
    quality_summary: dict[str, Any] | None = None,
    runtime_state: dict[str, Any] | None = None,
    mode: str = "multi_agent",
    engine: str = "multi_agent",
) -> dict[str, Any]:
    queue_snapshot = task_queue if isinstance(task_queue, dict) else {}
    store_snapshot = artifact_store if isinstance(artifact_store, dict) else {}
    return _build_lightweight_public_artifacts(
        queue_snapshot=queue_snapshot,
        store_snapshot=store_snapshot,
        research_topology=research_topology,
        quality_summary=quality_summary,
        runtime_state=runtime_state,
        mode=mode,
        engine=engine,
    )


def build_public_deep_research_artifacts_from_state(state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}

    deep_runtime = read_deep_runtime_snapshot(state, default_engine="")
    task_queue = deep_runtime.get("task_queue")
    artifact_store = deep_runtime.get("artifact_store")
    has_runtime_snapshot = (
        isinstance(task_queue, dict)
        and isinstance(artifact_store, dict)
        and (bool(task_queue) or bool(artifact_store))
    )
    if has_runtime_snapshot:
        mode = resolve_deep_runtime_mode(state, default_mode="multi_agent")
        return build_public_deep_research_artifacts(
            task_queue=task_queue,
            artifact_store=artifact_store,
            research_topology=state.get("research_topology"),
            quality_summary=state.get("quality_summary"),
            runtime_state=deep_runtime.get("runtime_state"),
            mode=mode,
            engine=str(deep_runtime.get("engine") or mode or "multi_agent"),
        )

    artifacts = state.get("deep_research_artifacts")
    if isinstance(artifacts, dict) and artifacts:
        mode = resolve_deep_runtime_mode(state, default_mode="multi_agent")
        return _filter_public_artifacts(
            artifacts,
            default_mode=mode,
            default_engine=str(mode or "multi_agent"),
        )
    return {}


__all__ = [
    "build_public_deep_research_artifacts",
    "build_public_deep_research_artifacts_from_state",
]
