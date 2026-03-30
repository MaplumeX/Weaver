"""
Storage contracts for the multi-agent deep runtime.
"""

from __future__ import annotations

import copy
import threading
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from agent.runtime.deep.multi_agent.schema import (
    BranchBrief,
    EvidenceCard,
    FinalReportArtifact,
    KnowledgeGap,
    ReportSectionDraft,
    ResearchTask,
    _now_iso,
)


class ResearchTaskQueue:
    def __init__(self) -> None:
        self._tasks: Dict[str, ResearchTask] = {}
        self._lock = threading.Lock()

    def enqueue(self, tasks: List[ResearchTask]) -> None:
        with self._lock:
            for task in tasks:
                task.updated_at = _now_iso()
                self._tasks[task.id] = task

    def claim_ready_tasks(self, *, limit: int, agent_ids: List[str]) -> List[ResearchTask]:
        claimed: List[ResearchTask] = []
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

    def update_status(self, task_id: str, status: str, *, reason: str = "") -> Optional[ResearchTask]:
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

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            tasks = [task.to_dict() for task in self._tasks.values()]
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

    def all_tasks(self) -> List[ResearchTask]:
        with self._lock:
            return [copy.deepcopy(task) for task in self._tasks.values()]

    def ready_count(self) -> int:
        with self._lock:
            return sum(1 for task in self._tasks.values() if task.status == "ready")

    def completed_count(self) -> int:
        with self._lock:
            return sum(1 for task in self._tasks.values() if task.status == "completed")


class ArtifactStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._briefs: Dict[str, BranchBrief] = {}
        self._evidence_cards: Dict[str, EvidenceCard] = {}
        self._knowledge_gaps: Dict[str, KnowledgeGap] = {}
        self._section_drafts: Dict[str, ReportSectionDraft] = {}
        self._final_report: Optional[FinalReportArtifact] = None

    def put_brief(self, brief: BranchBrief) -> None:
        with self._lock:
            brief.updated_at = _now_iso()
            self._briefs[brief.id] = brief

    def add_evidence(self, evidence_cards: List[EvidenceCard]) -> None:
        with self._lock:
            for card in evidence_cards:
                card.updated_at = _now_iso()
                self._evidence_cards[card.id] = card

    def replace_gaps(self, gaps: List[KnowledgeGap]) -> None:
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

    def get_related_artifacts(self, task_id: str) -> Dict[str, List[Dict[str, Any]]]:
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

    def evidence_cards(self) -> List[EvidenceCard]:
        with self._lock:
            return [copy.deepcopy(card) for card in self._evidence_cards.values()]

    def gap_artifacts(self) -> List[KnowledgeGap]:
        with self._lock:
            return [copy.deepcopy(gap) for gap in self._knowledge_gaps.values()]

    def section_drafts(self) -> List[ReportSectionDraft]:
        with self._lock:
            return [copy.deepcopy(section) for section in self._section_drafts.values()]

    def final_report(self) -> Optional[FinalReportArtifact]:
        with self._lock:
            return copy.deepcopy(self._final_report)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "branch_briefs": [asdict(brief) for brief in self._briefs.values()],
                "evidence_cards": [asdict(card) for card in self._evidence_cards.values()],
                "knowledge_gaps": [asdict(gap) for gap in self._knowledge_gaps.values()],
                "report_section_drafts": [asdict(section) for section in self._section_drafts.values()],
                "final_report": asdict(self._final_report) if self._final_report else None,
            }


__all__ = ["ArtifactStore", "ResearchTaskQueue"]
