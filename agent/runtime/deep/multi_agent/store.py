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
    BranchSynthesis,
    CoordinationRequest,
    EvidenceCard,
    EvidencePassage,
    FetchedDocument,
    FinalReportArtifact,
    KnowledgeGap,
    ReportSectionDraft,
    ResearchSubmission,
    ResearchTask,
    SourceCandidate,
    SupervisorDecisionArtifact,
    VerificationResult,
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


class ArtifactStore:
    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        self._lock = threading.Lock()
        self._briefs: dict[str, BranchBrief] = {}
        self._source_candidates: dict[str, SourceCandidate] = {}
        self._fetched_documents: dict[str, FetchedDocument] = {}
        self._evidence_passages: dict[str, EvidencePassage] = {}
        self._evidence_cards: dict[str, EvidenceCard] = {}
        self._branch_syntheses: dict[str, BranchSynthesis] = {}
        self._verification_results: dict[str, VerificationResult] = {}
        self._coordination_requests: dict[str, CoordinationRequest] = {}
        self._submissions: dict[str, ResearchSubmission] = {}
        self._supervisor_decisions: dict[str, SupervisorDecisionArtifact] = {}
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
            self._source_candidates = _restore_items(
                snapshot.get("source_candidates", []),
                SourceCandidate,
            )
            self._fetched_documents = _restore_items(
                snapshot.get("fetched_documents", []),
                FetchedDocument,
            )
            self._evidence_passages = _restore_items(
                snapshot.get("evidence_passages", []),
                EvidencePassage,
            )
            self._evidence_cards = _restore_items(snapshot.get("evidence_cards", []), EvidenceCard)
            self._branch_syntheses = _restore_items(
                snapshot.get("branch_syntheses", []),
                BranchSynthesis,
            )
            self._verification_results = _restore_items(
                snapshot.get("verification_results", []),
                VerificationResult,
            )
            self._coordination_requests = _restore_items(
                snapshot.get("coordination_requests", []),
                CoordinationRequest,
            )
            self._submissions = _restore_items(
                snapshot.get("submissions", []),
                ResearchSubmission,
            )
            self._supervisor_decisions = _restore_items(
                snapshot.get("supervisor_decisions", []),
                SupervisorDecisionArtifact,
            )
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

    def get_brief(self, branch_id: str) -> BranchBrief | None:
        with self._lock:
            brief = self._briefs.get(branch_id)
            return copy.deepcopy(brief) if brief else None

    def add_source_candidates(self, source_candidates: list[SourceCandidate]) -> None:
        with self._lock:
            for candidate in source_candidates:
                candidate.updated_at = _now_iso()
                self._source_candidates[candidate.id] = candidate

    def add_fetched_documents(self, documents: list[FetchedDocument]) -> None:
        with self._lock:
            for document in documents:
                document.updated_at = _now_iso()
                self._fetched_documents[document.id] = document

    def add_evidence_passages(self, passages: list[EvidencePassage]) -> None:
        with self._lock:
            for passage in passages:
                passage.updated_at = _now_iso()
                self._evidence_passages[passage.id] = passage

    def add_evidence(self, evidence_cards: list[EvidenceCard]) -> None:
        with self._lock:
            for card in evidence_cards:
                card.updated_at = _now_iso()
                self._evidence_cards[card.id] = card

    def add_branch_synthesis(self, synthesis: BranchSynthesis) -> None:
        with self._lock:
            synthesis.updated_at = _now_iso()
            self._branch_syntheses[synthesis.id] = synthesis

    def add_verification_results(self, verification_results: list[VerificationResult]) -> None:
        with self._lock:
            for result in verification_results:
                result.updated_at = _now_iso()
                self._verification_results[result.id] = result

    def add_coordination_requests(self, requests: list[CoordinationRequest]) -> None:
        with self._lock:
            for request in requests:
                request.updated_at = _now_iso()
                self._coordination_requests[request.id] = request

    def update_coordination_request_status(
        self,
        request_id: str,
        status: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> CoordinationRequest | None:
        with self._lock:
            request = self._coordination_requests.get(request_id)
            if not request:
                return None
            request.status = str(status or request.status)
            request.updated_at = _now_iso()
            if isinstance(metadata, dict) and metadata:
                request.metadata.update(metadata)
            return copy.deepcopy(request)

    def add_submissions(self, submissions: list[ResearchSubmission]) -> None:
        with self._lock:
            for submission in submissions:
                submission.updated_at = _now_iso()
                self._submissions[submission.id] = submission

    def add_supervisor_decision(self, artifact: SupervisorDecisionArtifact) -> None:
        with self._lock:
            artifact.updated_at = _now_iso()
            self._supervisor_decisions[artifact.id] = artifact

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

    def get_related_artifacts(
        self,
        task_id: str,
        *,
        branch_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            source_candidates = [
                asdict(candidate)
                for candidate in self._source_candidates.values()
                if candidate.task_id == task_id or (branch_id and candidate.branch_id == branch_id)
            ]
            fetched_documents = [
                asdict(document)
                for document in self._fetched_documents.values()
                if document.task_id == task_id or (branch_id and document.branch_id == branch_id)
            ]
            passages = [
                asdict(passage)
                for passage in self._evidence_passages.values()
                if passage.task_id == task_id or (branch_id and passage.branch_id == branch_id)
            ]
            evidence = [asdict(card) for card in self._evidence_cards.values() if card.task_id == task_id]
            sections = [
                asdict(section)
                for section in self._section_drafts.values()
                if section.task_id == task_id
            ]
            syntheses = [
                asdict(synthesis)
                for synthesis in self._branch_syntheses.values()
                if synthesis.task_id == task_id or (branch_id and synthesis.branch_id == branch_id)
            ]
            verification_results = [
                asdict(result)
                for result in self._verification_results.values()
                if result.task_id == task_id or (branch_id and result.branch_id == branch_id)
            ]
            coordination_requests = [
                asdict(request)
                for request in self._coordination_requests.values()
                if request.task_id == task_id or (branch_id and request.branch_id == branch_id)
            ]
            submissions = [
                asdict(submission)
                for submission in self._submissions.values()
                if submission.task_id == task_id or (branch_id and submission.branch_id == branch_id)
            ]
            gaps = [asdict(gap) for gap in self._knowledge_gaps.values()]
        return {
            "source_candidates": source_candidates,
            "fetched_documents": fetched_documents,
            "evidence_passages": passages,
            "evidence_cards": evidence,
            "section_drafts": sections,
            "branch_syntheses": syntheses,
            "verification_results": verification_results,
            "coordination_requests": coordination_requests,
            "submissions": submissions,
            "knowledge_gaps": gaps,
        }

    def source_candidates(self, *, branch_id: str | None = None) -> list[SourceCandidate]:
        with self._lock:
            items = self._source_candidates.values()
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            return [copy.deepcopy(item) for item in items]

    def fetched_documents(self, *, branch_id: str | None = None) -> list[FetchedDocument]:
        with self._lock:
            items = self._fetched_documents.values()
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            return [copy.deepcopy(item) for item in items]

    def evidence_passages(self, *, branch_id: str | None = None) -> list[EvidencePassage]:
        with self._lock:
            items = self._evidence_passages.values()
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            return [copy.deepcopy(item) for item in items]

    def evidence_cards(self) -> list[EvidenceCard]:
        with self._lock:
            return [copy.deepcopy(card) for card in self._evidence_cards.values()]

    def branch_syntheses(self, *, branch_id: str | None = None) -> list[BranchSynthesis]:
        with self._lock:
            items = self._branch_syntheses.values()
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            return [copy.deepcopy(item) for item in items]

    def verification_results(
        self,
        *,
        branch_id: str | None = None,
        validation_stage: str | None = None,
    ) -> list[VerificationResult]:
        with self._lock:
            items = list(self._verification_results.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if validation_stage:
                items = [item for item in items if item.validation_stage == validation_stage]
            return [copy.deepcopy(item) for item in items]

    def coordination_requests(
        self,
        *,
        branch_id: str | None = None,
        status: str | None = None,
    ) -> list[CoordinationRequest]:
        with self._lock:
            items = list(self._coordination_requests.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if status:
                items = [item for item in items if item.status == status]
            return [copy.deepcopy(item) for item in items]

    def submissions(
        self,
        *,
        branch_id: str | None = None,
        submission_kind: str | None = None,
    ) -> list[ResearchSubmission]:
        with self._lock:
            items = list(self._submissions.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if submission_kind:
                items = [item for item in items if item.submission_kind == submission_kind]
            return [copy.deepcopy(item) for item in items]

    def supervisor_decisions(self) -> list[SupervisorDecisionArtifact]:
        with self._lock:
            return [copy.deepcopy(item) for item in self._supervisor_decisions.values()]

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
                "source_candidates": [
                    asdict(candidate)
                    for candidate in sorted(
                        self._source_candidates.values(),
                        key=lambda item: (item.task_id, item.rank, item.created_at, item.id),
                    )
                ],
                "fetched_documents": [
                    asdict(document)
                    for document in sorted(
                        self._fetched_documents.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "evidence_passages": [
                    asdict(passage)
                    for passage in sorted(
                        self._evidence_passages.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "evidence_cards": [
                    asdict(card)
                    for card in sorted(
                        self._evidence_cards.values(),
                        key=lambda item: (item.task_id, item.source_url, item.created_at, item.id),
                    )
                ],
                "branch_syntheses": [
                    asdict(synthesis)
                    for synthesis in sorted(
                        self._branch_syntheses.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "verification_results": [
                    asdict(result)
                    for result in sorted(
                        self._verification_results.values(),
                        key=lambda item: (item.task_id, item.validation_stage, item.created_at, item.id),
                    )
                ],
                "coordination_requests": [
                    asdict(request)
                    for request in sorted(
                        self._coordination_requests.values(),
                        key=lambda item: (item.priority, item.created_at, item.id),
                    )
                ],
                "submissions": [
                    asdict(submission)
                    for submission in sorted(
                        self._submissions.values(),
                        key=lambda item: (item.created_at, item.id),
                    )
                ],
                "supervisor_decisions": [
                    asdict(decision)
                    for decision in sorted(
                        self._supervisor_decisions.values(),
                        key=lambda item: (item.iteration, item.created_at, item.id),
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
