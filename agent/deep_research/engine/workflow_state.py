"""Workflow state types and reducers for the Deep Research engine."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def reduce_worker_payloads(
    existing: list[dict[str, Any]] | None,
    new: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    current = list(existing or [])
    if not new:
        return current

    reset = any(isinstance(item, dict) and item.get("__reset__") for item in new)
    payloads = [
        item
        for item in new
        if isinstance(item, dict) and not item.get("__reset__")
    ]
    if reset:
        return payloads
    return current + payloads


class MultiAgentGraphState(TypedDict, total=False):
    shared_state: dict[str, Any]
    topic: str
    graph_run_id: str
    graph_attempt: int
    root_branch_id: str
    task_queue: dict[str, Any]
    artifact_store: dict[str, Any]
    runtime_state: dict[str, Any]
    agent_runs: list[dict[str, Any]]
    current_iteration: int
    planning_mode: str
    next_step: str
    latest_decision: dict[str, Any]
    latest_verification_summary: dict[str, Any]
    pending_worker_tasks: list[dict[str, Any]]
    worker_task: dict[str, Any]
    worker_results: Annotated[list[dict[str, Any]], reduce_worker_payloads]
    final_result: dict[str, Any]


def split_findings(summary: str) -> list[str]:
    text = str(summary or "").strip()
    if not text:
        return []
    parts = [item.strip(" -•\t") for item in text.replace("\r", "\n").split("\n") if item.strip()]
    findings = [part for part in parts if len(part) >= 12]
    if findings:
        return findings[:6]
    return [text[:300]]


__all__ = [
    "MultiAgentGraphState",
    "reduce_worker_payloads",
    "split_findings",
]
