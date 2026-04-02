"""Deep runtime state adapters.

`deep_runtime` is the preferred nested snapshot. Legacy `deepsearch_*` top-level
fields remain available only as compatibility views derived from that snapshot.
"""

from __future__ import annotations

import copy
from typing import Any

from agent.core.state import DeepRuntimeSnapshot, build_deep_runtime_snapshot


def read_deep_runtime_snapshot(
    state: dict[str, Any] | None,
    *,
    default_engine: str = "multi_agent",
) -> DeepRuntimeSnapshot:
    if not isinstance(state, dict):
        return build_deep_runtime_snapshot(engine=default_engine)

    nested = state.get("deep_runtime")
    nested_snapshot = nested if isinstance(nested, dict) else {}

    engine = str(
        nested_snapshot.get("engine")
        or state.get("deepsearch_engine")
        or state.get("deepsearch_mode")
        or default_engine
    ).strip() or default_engine

    task_queue = nested_snapshot.get("task_queue")
    if not isinstance(task_queue, dict):
        task_queue = state.get("deepsearch_task_queue")

    artifact_store = nested_snapshot.get("artifact_store")
    if not isinstance(artifact_store, dict):
        artifact_store = state.get("deepsearch_artifact_store")

    runtime_state = nested_snapshot.get("runtime_state")
    if not isinstance(runtime_state, dict):
        runtime_state = state.get("deepsearch_runtime_state")

    agent_runs = nested_snapshot.get("agent_runs")
    if not isinstance(agent_runs, list):
        agent_runs = state.get("deepsearch_agent_runs")

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
    default_mode: str = "deepsearch",
) -> str:
    snapshot = read_deep_runtime_snapshot(state, default_engine="")
    engine = str(snapshot.get("engine") or "").strip()
    if engine:
        return engine
    if isinstance(state, dict):
        mode = str(state.get("deepsearch_mode") or state.get("route") or "").strip()
        if mode:
            return mode
    return default_mode


def build_legacy_deepsearch_fields(
    snapshot: DeepRuntimeSnapshot,
    *,
    mode: str | None = None,
    tokens_used: int | None = None,
    elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    engine = str(snapshot.get("engine") or "multi_agent").strip() or "multi_agent"
    legacy: dict[str, Any] = {
        "deepsearch_mode": mode or engine,
        "deepsearch_engine": engine,
        "deepsearch_task_queue": copy.deepcopy(snapshot.get("task_queue") or {}),
        "deepsearch_artifact_store": copy.deepcopy(snapshot.get("artifact_store") or {}),
        "deepsearch_runtime_state": copy.deepcopy(snapshot.get("runtime_state") or {}),
        "deepsearch_agent_runs": copy.deepcopy(snapshot.get("agent_runs") or []),
    }
    if tokens_used is not None:
        legacy["deepsearch_tokens_used"] = int(tokens_used)
    if elapsed_seconds is not None:
        legacy["deepsearch_elapsed_seconds"] = float(elapsed_seconds)
    return legacy


__all__ = [
    "build_legacy_deepsearch_fields",
    "read_deep_runtime_snapshot",
    "resolve_deep_runtime_mode",
]
