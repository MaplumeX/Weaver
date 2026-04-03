"""
Storage contracts for the multi-agent deep runtime.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

from agent.runtime.deep.schema import (
    AnswerUnit,
    BranchBrief,
    BranchRevisionBrief,
    BranchSynthesis,
    BranchValidationSummary,
    ClaimGroundingResult,
    ClaimUnit,
    ConsistencyResult,
    ContradictionRegistryArtifact,
    CoordinationRequest,
    CoverageMatrixArtifact,
    CoverageEvaluationResult,
    CoverageObligation,
    EvidenceCard,
    EvidencePassage,
    FetchedDocument,
    FinalReportArtifact,
    KnowledgeGap,
    MissingEvidenceListArtifact,
    OutlineArtifact,
    ProgressLedgerArtifact,
    ReportSectionDraft,
    ResearchBriefArtifact,
    ResearchSubmission,
    ResearchTask,
    RevisionIssue,
    SourceCandidate,
    SupervisorDecisionArtifact,
    TaskLedgerArtifact,
    VerificationResult,
    _now_iso,
    validate_coordination_request_type,
)


def _restore_items(items: Iterable[dict[str, Any]], cls: type[Any]) -> dict[str, Any]:
    restored: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        restored[item["id"]] = cls(**item)
    return restored


def _claim_to_answer_unit(claim_unit: ClaimUnit) -> AnswerUnit:
    return AnswerUnit.from_claim_unit(claim_unit)


def _answer_to_claim_unit(answer_unit: AnswerUnit) -> ClaimUnit:
    return answer_unit.to_claim_unit()


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
        self._research_brief: ResearchBriefArtifact | None = None
        self._task_ledger: TaskLedgerArtifact | None = None
        self._progress_ledger: ProgressLedgerArtifact | None = None
        self._coverage_matrix: CoverageMatrixArtifact | None = None
        self._contradiction_registry: ContradictionRegistryArtifact | None = None
        self._missing_evidence_list: MissingEvidenceListArtifact | None = None
        self._outline: OutlineArtifact | None = None
        self._briefs: dict[str, BranchBrief] = {}
        self._answer_units: dict[str, AnswerUnit] = {}
        self._claim_units: dict[str, ClaimUnit] = {}
        self._coverage_obligations: dict[str, CoverageObligation] = {}
        self._claim_grounding_results: dict[str, ClaimGroundingResult] = {}
        self._coverage_evaluation_results: dict[str, CoverageEvaluationResult] = {}
        self._consistency_results: dict[str, ConsistencyResult] = {}
        self._revision_issues: dict[str, RevisionIssue] = {}
        self._revision_briefs: dict[str, BranchRevisionBrief] = {}
        self._source_candidates: dict[str, SourceCandidate] = {}
        self._fetched_documents: dict[str, FetchedDocument] = {}
        self._evidence_passages: dict[str, EvidencePassage] = {}
        self._evidence_cards: dict[str, EvidenceCard] = {}
        self._branch_syntheses: dict[str, BranchSynthesis] = {}
        self._branch_validation_summaries: dict[str, BranchValidationSummary] = {}
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
            research_brief = snapshot.get("research_brief")
            self._research_brief = (
                ResearchBriefArtifact(**research_brief) if isinstance(research_brief, dict) else None
            )
            task_ledger = snapshot.get("task_ledger")
            self._task_ledger = TaskLedgerArtifact(**task_ledger) if isinstance(task_ledger, dict) else None
            progress_ledger = snapshot.get("progress_ledger")
            self._progress_ledger = (
                ProgressLedgerArtifact(**progress_ledger) if isinstance(progress_ledger, dict) else None
            )
            coverage_matrix = snapshot.get("coverage_matrix")
            self._coverage_matrix = (
                CoverageMatrixArtifact(**coverage_matrix) if isinstance(coverage_matrix, dict) else None
            )
            contradiction_registry = snapshot.get("contradiction_registry")
            self._contradiction_registry = (
                ContradictionRegistryArtifact(**contradiction_registry)
                if isinstance(contradiction_registry, dict)
                else None
            )
            missing_evidence_list = snapshot.get("missing_evidence_list")
            self._missing_evidence_list = (
                MissingEvidenceListArtifact(**missing_evidence_list)
                if isinstance(missing_evidence_list, dict)
                else None
            )
            outline = snapshot.get("outline")
            self._outline = OutlineArtifact(**outline) if isinstance(outline, dict) else None
            self._briefs = _restore_items(snapshot.get("branch_briefs", []), BranchBrief)
            self._answer_units = _restore_items(snapshot.get("answer_units", []), AnswerUnit)
            self._claim_units = _restore_items(snapshot.get("claim_units", []), ClaimUnit)
            if not self._answer_units and self._claim_units:
                self._answer_units = {
                    claim_id: _claim_to_answer_unit(item)
                    for claim_id, item in self._claim_units.items()
                }
            if not self._claim_units and self._answer_units:
                self._claim_units = {
                    answer_id: _answer_to_claim_unit(item)
                    for answer_id, item in self._answer_units.items()
                }
            self._coverage_obligations = _restore_items(
                snapshot.get("coverage_obligations", []),
                CoverageObligation,
            )
            self._claim_grounding_results = _restore_items(
                snapshot.get("claim_grounding_results", []),
                ClaimGroundingResult,
            )
            self._coverage_evaluation_results = _restore_items(
                snapshot.get("coverage_evaluation_results", []),
                CoverageEvaluationResult,
            )
            self._consistency_results = _restore_items(
                snapshot.get("consistency_results", []),
                ConsistencyResult,
            )
            self._revision_issues = _restore_items(snapshot.get("revision_issues", []), RevisionIssue)
            self._revision_briefs = _restore_items(
                snapshot.get("revision_briefs", []),
                BranchRevisionBrief,
            )
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
            self._branch_validation_summaries = _restore_items(
                snapshot.get("branch_validation_summaries", []),
                BranchValidationSummary,
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

    def set_research_brief(self, brief: ResearchBriefArtifact) -> None:
        with self._lock:
            brief.updated_at = _now_iso()
            self._research_brief = brief

    def research_brief(self) -> ResearchBriefArtifact | None:
        with self._lock:
            return copy.deepcopy(self._research_brief)

    def set_task_ledger(self, ledger: TaskLedgerArtifact) -> None:
        with self._lock:
            ledger.updated_at = _now_iso()
            self._task_ledger = ledger

    def task_ledger(self) -> TaskLedgerArtifact | None:
        with self._lock:
            return copy.deepcopy(self._task_ledger)

    def set_progress_ledger(self, ledger: ProgressLedgerArtifact) -> None:
        with self._lock:
            ledger.updated_at = _now_iso()
            self._progress_ledger = ledger

    def progress_ledger(self) -> ProgressLedgerArtifact | None:
        with self._lock:
            return copy.deepcopy(self._progress_ledger)

    def set_coverage_matrix(self, artifact: CoverageMatrixArtifact) -> None:
        with self._lock:
            artifact.updated_at = _now_iso()
            self._coverage_matrix = artifact

    def coverage_matrix(self) -> CoverageMatrixArtifact | None:
        with self._lock:
            return copy.deepcopy(self._coverage_matrix)

    def set_contradiction_registry(self, artifact: ContradictionRegistryArtifact) -> None:
        with self._lock:
            artifact.updated_at = _now_iso()
            self._contradiction_registry = artifact

    def contradiction_registry(self) -> ContradictionRegistryArtifact | None:
        with self._lock:
            return copy.deepcopy(self._contradiction_registry)

    def set_missing_evidence_list(self, artifact: MissingEvidenceListArtifact) -> None:
        with self._lock:
            artifact.updated_at = _now_iso()
            self._missing_evidence_list = artifact

    def missing_evidence_list(self) -> MissingEvidenceListArtifact | None:
        with self._lock:
            return copy.deepcopy(self._missing_evidence_list)

    def set_outline(self, artifact: OutlineArtifact) -> None:
        with self._lock:
            artifact.updated_at = _now_iso()
            self._outline = artifact

    def outline(self) -> OutlineArtifact | None:
        with self._lock:
            return copy.deepcopy(self._outline)

    def put_brief(self, brief: BranchBrief) -> None:
        with self._lock:
            brief.updated_at = _now_iso()
            self._briefs[brief.id] = brief

    def add_answer_units(self, answer_units: list[AnswerUnit]) -> None:
        with self._lock:
            for item in answer_units:
                item.updated_at = _now_iso()
                self._answer_units[item.id] = item
                self._claim_units[item.id] = item.to_claim_unit()

    def answer_units(
        self,
        *,
        branch_id: str | None = None,
        task_id: str | None = None,
    ) -> list[AnswerUnit]:
        with self._lock:
            items = list(self._answer_units.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if task_id:
                items = [item for item in items if item.task_id == task_id]
            return [copy.deepcopy(item) for item in items]

    def get_brief(self, branch_id: str) -> BranchBrief | None:
        with self._lock:
            brief = self._briefs.get(branch_id)
            return copy.deepcopy(brief) if brief else None

    def add_claim_units(self, claim_units: list[ClaimUnit]) -> None:
        with self._lock:
            for item in claim_units:
                item.updated_at = _now_iso()
                self._claim_units[item.id] = item
                self._answer_units[item.id] = _claim_to_answer_unit(item)

    def claim_units(
        self,
        *,
        branch_id: str | None = None,
        task_id: str | None = None,
    ) -> list[ClaimUnit]:
        with self._lock:
            items = list(self._claim_units.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if task_id:
                items = [item for item in items if item.task_id == task_id]
            return [copy.deepcopy(item) for item in items]

    def add_coverage_obligations(self, obligations: list[CoverageObligation]) -> None:
        with self._lock:
            for item in obligations:
                item.updated_at = _now_iso()
                self._coverage_obligations[item.id] = item

    def coverage_obligations(
        self,
        *,
        branch_id: str | None = None,
        task_id: str | None = None,
    ) -> list[CoverageObligation]:
        with self._lock:
            items = list(self._coverage_obligations.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if task_id:
                items = [item for item in items if item.task_id == task_id]
            return [copy.deepcopy(item) for item in items]

    def add_claim_grounding_results(self, items: list[ClaimGroundingResult]) -> None:
        with self._lock:
            for item in items:
                item.updated_at = _now_iso()
                self._claim_grounding_results[item.id] = item

    def claim_grounding_results(
        self,
        *,
        branch_id: str | None = None,
        task_id: str | None = None,
    ) -> list[ClaimGroundingResult]:
        with self._lock:
            items = list(self._claim_grounding_results.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if task_id:
                items = [item for item in items if item.task_id == task_id]
            return [copy.deepcopy(item) for item in items]

    def add_coverage_evaluation_results(self, items: list[CoverageEvaluationResult]) -> None:
        with self._lock:
            for item in items:
                item.updated_at = _now_iso()
                self._coverage_evaluation_results[item.id] = item

    def coverage_evaluation_results(
        self,
        *,
        branch_id: str | None = None,
        task_id: str | None = None,
    ) -> list[CoverageEvaluationResult]:
        with self._lock:
            items = list(self._coverage_evaluation_results.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if task_id:
                items = [item for item in items if item.task_id == task_id]
            return [copy.deepcopy(item) for item in items]

    def add_consistency_results(self, items: list[ConsistencyResult]) -> None:
        with self._lock:
            for item in items:
                item.updated_at = _now_iso()
                self._consistency_results[item.id] = item

    def consistency_results(
        self,
        *,
        branch_id: str | None = None,
    ) -> list[ConsistencyResult]:
        with self._lock:
            items = list(self._consistency_results.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            return [copy.deepcopy(item) for item in items]

    def add_revision_issues(self, items: list[RevisionIssue]) -> None:
        with self._lock:
            for item in items:
                item.updated_at = _now_iso()
                self._revision_issues[item.id] = item

    def revision_issues(
        self,
        *,
        branch_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
    ) -> list[RevisionIssue]:
        with self._lock:
            items = list(self._revision_issues.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if task_id:
                items = [item for item in items if item.task_id == task_id]
            if status:
                items = [item for item in items if item.status == status]
            return [copy.deepcopy(item) for item in items]

    def update_revision_issue_status(
        self,
        issue_id: str,
        status: str,
        *,
        resolution: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RevisionIssue | None:
        with self._lock:
            issue = self._revision_issues.get(issue_id)
            if not issue:
                return None
            issue.status = str(status or issue.status)
            issue.updated_at = _now_iso()
            if isinstance(resolution, dict) and resolution:
                issue.resolution.update(resolution)
            if isinstance(metadata, dict) and metadata:
                issue.metadata.update(metadata)
            return copy.deepcopy(issue)

    def add_revision_briefs(self, items: list[BranchRevisionBrief]) -> None:
        with self._lock:
            for item in items:
                item.updated_at = _now_iso()
                self._revision_briefs[item.id] = item

    def revision_briefs(
        self,
        *,
        target_branch_id: str | None = None,
    ) -> list[BranchRevisionBrief]:
        with self._lock:
            items = list(self._revision_briefs.values())
            if target_branch_id:
                items = [item for item in items if item.target_branch_id == target_branch_id]
            return [copy.deepcopy(item) for item in items]

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

    def add_branch_validation_summaries(self, items: list[BranchValidationSummary]) -> None:
        with self._lock:
            for item in items:
                item.updated_at = _now_iso()
                self._branch_validation_summaries[item.id] = item

    def branch_validation_summaries(
        self,
        *,
        branch_id: str | None = None,
        task_id: str | None = None,
    ) -> list[BranchValidationSummary]:
        with self._lock:
            items = list(self._branch_validation_summaries.values())
            if branch_id:
                items = [item for item in items if item.branch_id == branch_id]
            if task_id:
                items = [item for item in items if item.task_id == task_id]
            return [copy.deepcopy(item) for item in items]

    def add_verification_results(self, verification_results: list[VerificationResult]) -> None:
        with self._lock:
            for result in verification_results:
                result.updated_at = _now_iso()
                self._verification_results[result.id] = result

    def add_coordination_requests(self, requests: list[CoordinationRequest]) -> None:
        with self._lock:
            for request in requests:
                request.request_type = validate_coordination_request_type(request.request_type)
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
            claim_units = [
                asdict(item)
                for item in self._claim_units.values()
                if item.task_id == task_id or (branch_id and item.branch_id == branch_id)
            ]
            answer_units = [
                asdict(item)
                for item in self._answer_units.values()
                if item.task_id == task_id or (branch_id and item.branch_id == branch_id)
            ]
            obligations = [
                asdict(item)
                for item in self._coverage_obligations.values()
                if item.task_id == task_id or (branch_id and item.branch_id == branch_id)
            ]
            grounding_results = [
                asdict(item)
                for item in self._claim_grounding_results.values()
                if item.task_id == task_id or (branch_id and item.branch_id == branch_id)
            ]
            coverage_evaluation_results = [
                asdict(item)
                for item in self._coverage_evaluation_results.values()
                if item.task_id == task_id or (branch_id and item.branch_id == branch_id)
            ]
            consistency_results = [
                asdict(item)
                for item in self._consistency_results.values()
                if branch_id and item.branch_id == branch_id
            ]
            revision_issues = [
                asdict(item)
                for item in self._revision_issues.values()
                if item.task_id == task_id or (branch_id and item.branch_id == branch_id)
            ]
            revision_briefs = [
                asdict(item)
                for item in self._revision_briefs.values()
                if branch_id and item.target_branch_id == branch_id
            ]
            syntheses = [
                asdict(synthesis)
                for synthesis in self._branch_syntheses.values()
                if synthesis.task_id == task_id or (branch_id and synthesis.branch_id == branch_id)
            ]
            branch_validation_summaries = [
                asdict(summary)
                for summary in self._branch_validation_summaries.values()
                if summary.task_id == task_id or (branch_id and summary.branch_id == branch_id)
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
            "research_brief": asdict(self._research_brief) if self._research_brief else {},
            "task_ledger": asdict(self._task_ledger) if self._task_ledger else {},
            "progress_ledger": asdict(self._progress_ledger) if self._progress_ledger else {},
            "coverage_matrix": asdict(self._coverage_matrix) if self._coverage_matrix else {},
            "contradiction_registry": (
                asdict(self._contradiction_registry) if self._contradiction_registry else {}
            ),
            "missing_evidence_list": (
                asdict(self._missing_evidence_list) if self._missing_evidence_list else {}
            ),
            "outline": asdict(self._outline) if self._outline else {},
            "answer_units": answer_units,
            "claim_units": claim_units,
            "coverage_obligations": obligations,
            "claim_grounding_results": grounding_results,
            "coverage_evaluation_results": coverage_evaluation_results,
            "consistency_results": consistency_results,
            "revision_issues": revision_issues,
            "revision_briefs": revision_briefs,
            "source_candidates": source_candidates,
            "fetched_documents": fetched_documents,
            "evidence_passages": passages,
            "evidence_cards": evidence,
            "section_drafts": sections,
            "branch_syntheses": syntheses,
            "branch_validation_summaries": branch_validation_summaries,
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
                "research_brief": asdict(self._research_brief) if self._research_brief else None,
                "task_ledger": asdict(self._task_ledger) if self._task_ledger else None,
                "progress_ledger": asdict(self._progress_ledger) if self._progress_ledger else None,
                "coverage_matrix": asdict(self._coverage_matrix) if self._coverage_matrix else None,
                "contradiction_registry": (
                    asdict(self._contradiction_registry) if self._contradiction_registry else None
                ),
                "missing_evidence_list": (
                    asdict(self._missing_evidence_list) if self._missing_evidence_list else None
                ),
                "outline": asdict(self._outline) if self._outline else None,
                "branch_briefs": [
                    asdict(brief)
                    for brief in sorted(self._briefs.values(), key=lambda item: (item.created_at, item.id))
                ],
                "answer_units": [
                    asdict(item)
                    for item in sorted(
                        self._answer_units.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "claim_units": [
                    asdict(item)
                    for item in sorted(
                        self._claim_units.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "coverage_obligations": [
                    asdict(item)
                    for item in sorted(
                        self._coverage_obligations.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "claim_grounding_results": [
                    asdict(item)
                    for item in sorted(
                        self._claim_grounding_results.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "coverage_evaluation_results": [
                    asdict(item)
                    for item in sorted(
                        self._coverage_evaluation_results.values(),
                        key=lambda item: (item.task_id, item.created_at, item.id),
                    )
                ],
                "consistency_results": [
                    asdict(item)
                    for item in sorted(
                        self._consistency_results.values(),
                        key=lambda item: (item.created_at, item.id),
                    )
                ],
                "revision_issues": [
                    asdict(item)
                    for item in sorted(
                        self._revision_issues.values(),
                        key=lambda item: (item.created_at, item.id),
                    )
                ],
                "revision_briefs": [
                    asdict(item)
                    for item in sorted(
                        self._revision_briefs.values(),
                        key=lambda item: (item.created_at, item.id),
                    )
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
                "branch_validation_summaries": [
                    asdict(summary)
                    for summary in sorted(
                        self._branch_validation_summaries.values(),
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
