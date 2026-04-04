"""
Storage contracts for the lightweight multi-agent deep runtime.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Iterable
from typing import Any

from agent.runtime.deep.schema import ResearchTask, _now_iso


def _restore_items(items: Iterable[dict[str, Any]], cls: type[Any]) -> dict[str, Any]:
    restored: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        restored[item["id"]] = cls(**item)
    return restored


class ResearchTaskQueue:
    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        self._tasks: dict[str, ResearchTask] = {}
        self._lock = threading.Lock()
        if snapshot:
            self.restore(snapshot)

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> ResearchTaskQueue:
        return cls(snapshot=snapshot)

    def restore(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self._tasks = _restore_items(snapshot.get("tasks", []), ResearchTask)

    def enqueue(self, tasks: list[ResearchTask]) -> None:
        with self._lock:
            for task in tasks:
                task.updated_at = _now_iso()
                self._tasks[task.id] = task

    def claim_ready_tasks(self, *, limit: int, agent_ids: list[str]) -> list[ResearchTask]:
        claimed: list[ResearchTask] = []
        with self._lock:
            ready = sorted(
                (task for task in self._tasks.values() if task.status == "ready"),
                key=lambda task: (task.priority, task.created_at),
            )
            claimed_branch_ids: set[str] = set()
            for task in ready:
                if len(claimed) >= max(0, limit):
                    break
                branch_id = str(task.branch_id or "").strip()
                if branch_id and branch_id in claimed_branch_ids:
                    continue
                task.status = "in_progress"
                task.stage = "dispatch"
                task.assigned_agent_id = agent_ids[len(claimed)] if len(claimed) < len(agent_ids) else None
                task.attempts += 1
                task.updated_at = _now_iso()
                claimed.append(copy.deepcopy(task))
                if branch_id:
                    claimed_branch_ids.add(branch_id)
        return claimed

    def update_status(self, task_id: str, status: str, *, reason: str = "") -> ResearchTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = status
            task.updated_at = _now_iso()
            if status == "in_progress" and task.stage == "planned":
                task.stage = "dispatch"
            if status in {"ready", "failed", "blocked", "completed", "cancelled"}:
                task.assigned_agent_id = None
            if status == "completed":
                task.stage = "reported"
                task.completed_at = task.updated_at
            if reason:
                task.last_error = reason
            return copy.deepcopy(task)

    def update_stage(
        self,
        task_id: str,
        stage: str,
        *,
        status: str | None = None,
        reason: str = "",
    ) -> ResearchTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.stage = str(stage or task.stage or "planned")
            if status:
                task.status = status
                if status in {"ready", "failed", "blocked", "completed", "cancelled"}:
                    task.assigned_agent_id = None
            task.updated_at = _now_iso()
            if reason:
                task.last_error = reason
            return copy.deepcopy(task)

    def requeue_in_progress(self, *, reason: str = "resume_pending_dispatch") -> list[ResearchTask]:
        restored: list[ResearchTask] = []
        with self._lock:
            for task in self._tasks.values():
                if task.status != "in_progress":
                    continue
                task.status = "ready"
                task.assigned_agent_id = None
                task.last_error = reason
                task.updated_at = _now_iso()
                restored.append(copy.deepcopy(task))
        return restored

    def get(self, task_id: str) -> ResearchTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return copy.deepcopy(task) if task else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            tasks = [
                task.to_dict()
                for task in sorted(
                    self._tasks.values(),
                    key=lambda item: (item.priority, item.created_at, item.id),
                )
            ]
        return {
            "tasks": tasks,
            "stats": {
                "total": len(tasks),
                "ready": sum(1 for task in tasks if task["status"] == "ready"),
                "in_progress": sum(1 for task in tasks if task["status"] == "in_progress"),
                "completed": sum(1 for task in tasks if task["status"] == "completed"),
                "failed": sum(1 for task in tasks if task["status"] == "failed"),
                "blocked": sum(1 for task in tasks if task["status"] == "blocked"),
            },
        }

    def all_tasks(self) -> list[ResearchTask]:
        with self._lock:
            return [copy.deepcopy(task) for task in self._tasks.values()]

    def ready_count(self) -> int:
        with self._lock:
            return sum(1 for task in self._tasks.values() if task.status == "ready")

    def completed_count(self) -> int:
        with self._lock:
            return sum(1 for task in self._tasks.values() if task.status == "completed")


__all__ = ["ResearchTaskQueue"]
