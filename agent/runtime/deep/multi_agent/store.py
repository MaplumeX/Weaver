"""
Storage contracts for the multi-agent deep runtime.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

from agent.runtime.deep.multi_agent.schema import (
    BranchBrief,
    EvidenceCard,
    FinalReportArtifact,
    KnowledgeGap,
    ReportSectionDraft,
    ResearchTask,
    _now_iso,
)


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
            for idx, task in enumerate(ready[: max(0, limit)]):
                task.status = "in_progress"
                task.assigned_agent_id = agent_ids[idx] if idx < len(agent_ids) else None
                task.attempts += 1
                task.updated_at = _now_iso()
                claimed.append(copy.deepcopy(task))
        return claimed

    def update_status(self, task_id: str, status: str, *, reason: str = "") -> ResearchTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = status
            task.updated_at = _now_iso()
            if status == "completed":
                task.completed_at = task.updated_at
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


class ArtifactStore:
    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        self._lock = threading.Lock()
        self._briefs: dict[str, BranchBrief] = {}
        self._evidence_cards: dict[str, EvidenceCard] = {}
        self._knowledge_gaps: dict[str, KnowledgeGap] = {}
        self._section_drafts: dict[str, ReportSectionDraft] = {}
        self._final_report: FinalReportArtifact | None = None
        if snapshot:
            self.restore(snapshot)

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> ArtifactStore:
        return cls(snapshot=snapshot)

    def restore(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self._briefs = _restore_items(snapshot.get("branch_briefs", []), BranchBrief)
            self._evidence_cards = _restore_items(snapshot.get("evidence_cards", []), EvidenceCard)
            self._knowledge_gaps = _restore_items(snapshot.get("knowledge_gaps", []), KnowledgeGap)
            self._section_drafts = _restore_items(
                snapshot.get("report_section_drafts", []),
                ReportSectionDraft,
            )
            final_report = snapshot.get("final_report")
            self._final_report = FinalReportArtifact(**final_report) if isinstance(final_report, dict) else None

    def put_brief(self, brief: BranchBrief) -> None:
        with self._lock:
            brief.updated_at = _now_iso()
            self._briefs[brief.id] = brief

    def add_evidence(self, evidence_cards: list[EvidenceCard]) -> None:
        with self._lock:
            for card in evidence_cards:
                card.updated_at = _now_iso()
                self._evidence_cards[card.id] = card

    def replace_gaps(self, gaps: list[KnowledgeGap]) -> None:
        with self._lock:
            self._knowledge_gaps = {}
            for gap in gaps:
                gap.updated_at = _now_iso()
                self._knowledge_gaps[gap.id] = gap

    def add_section_draft(self, section: ReportSectionDraft) -> None:
        with self._lock:
            section.updated_at = _now_iso()
            self._section_drafts[section.id] = section

    def set_final_report(self, artifact: FinalReportArtifact) -> None:
        with self._lock:
            artifact.updated_at = _now_iso()
            self._final_report = artifact

    def get_related_artifacts(self, task_id: str) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            evidence = [asdict(card) for card in self._evidence_cards.values() if card.task_id == task_id]
            sections = [
                asdict(section)
                for section in self._section_drafts.values()
                if section.task_id == task_id
            ]
            gaps = [asdict(gap) for gap in self._knowledge_gaps.values()]
        return {
            "evidence_cards": evidence,
            "section_drafts": sections,
            "knowledge_gaps": gaps,
        }

    def evidence_cards(self) -> list[EvidenceCard]:
        with self._lock:
            return [copy.deepcopy(card) for card in self._evidence_cards.values()]

    def gap_artifacts(self) -> list[KnowledgeGap]:
        with self._lock:
            return [copy.deepcopy(gap) for gap in self._knowledge_gaps.values()]

    def section_drafts(self) -> list[ReportSectionDraft]:
        with self._lock:
            return [copy.deepcopy(section) for section in self._section_drafts.values()]

    def final_report(self) -> FinalReportArtifact | None:
        with self._lock:
            return copy.deepcopy(self._final_report)

    def branch_briefs(self) -> list[BranchBrief]:
        with self._lock:
            return [copy.deepcopy(brief) for brief in self._briefs.values()]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "branch_briefs": [
                    asdict(brief)
                    for brief in sorted(self._briefs.values(), key=lambda item: (item.created_at, item.id))
                ],
                "evidence_cards": [
                    asdict(card)
                    for card in sorted(
                        self._evidence_cards.values(),
                        key=lambda item: (item.task_id, item.source_url, item.created_at, item.id),
                    )
                ],
                "knowledge_gaps": [
                    asdict(gap)
                    for gap in sorted(self._knowledge_gaps.values(), key=lambda item: (item.aspect, item.id))
                ],
                "report_section_drafts": [
                    asdict(section)
                    for section in sorted(
                        self._section_drafts.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "final_report": asdict(self._final_report) if self._final_report else None,
            }


__all__ = ["ArtifactStore", "ResearchTaskQueue"]
