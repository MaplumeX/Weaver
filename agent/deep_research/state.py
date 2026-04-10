"""Deep runtime state helpers."""

from __future__ import annotations

from typing import Any

from agent.foundation.state import DeepRuntimeSnapshot, build_deep_runtime_snapshot


def read_deep_runtime_snapshot(
    state: dict[str, Any] | None,
    *,
    default_engine: str = "multi_agent",
) -> DeepRuntimeSnapshot:
    if not isinstance(state, dict):
        return build_deep_runtime_snapshot(engine=default_engine)

    nested = state.get("deep_runtime")
    nested_snapshot = nested if isinstance(nested, dict) else {}

    engine = str(nested_snapshot.get("engine") or default_engine).strip() or default_engine
    task_queue = nested_snapshot.get("task_queue")
    artifact_store = nested_snapshot.get("artifact_store")
    runtime_state = nested_snapshot.get("runtime_state")
    agent_runs = nested_snapshot.get("agent_runs")

    return build_deep_runtime_snapshot(
        engine=engine,
        task_queue=task_queue if isinstance(task_queue, dict) else {},
        artifact_store=artifact_store if isinstance(artifact_store, dict) else {},
        runtime_state=runtime_state if isinstance(runtime_state, dict) else {},
        agent_runs=agent_runs if isinstance(agent_runs, list) else [],
    )


def resolve_deep_runtime_mode(
    state: dict[str, Any] | None,
    *,
    default_mode: str = "deep_research",
) -> str:
    snapshot = read_deep_runtime_snapshot(state, default_engine="")
    engine = str(snapshot.get("engine") or "").strip()
    if engine:
        return engine
    if isinstance(state, dict):
        mode = str(state.get("route") or "").strip()
        if mode:
            return mode
    return default_mode


__all__ = [
    "read_deep_runtime_snapshot",
    "resolve_deep_runtime_mode",
]
