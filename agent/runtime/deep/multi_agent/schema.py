"""
Artifact, scope and state contracts for the multi-agent deep runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, TypedDict

from agent.core.context import ResearchWorkerContext

TaskStatus = Literal["ready", "in_progress", "blocked", "completed", "failed", "cancelled"]
ArtifactStatus = Literal["created", "updated", "completed", "discarded"]
ScopeDraftStatus = Literal["awaiting_review", "revision_requested", "approved"]
AgentRole = Literal["clarify", "scope", "coordinator", "planner", "researcher", "verifier", "reporter"]
TaskStage = Literal[
    "planned",
    "dispatch",
    "search",
    "read",
    "extract",
    "synthesize",
    "claim_check",
    "coverage_check",
    "reported",
]
ValidationStage = Literal["claim_check", "coverage_check"]
ValidationOutcome = Literal["passed", "failed", "needs_follow_up"]


def _now_iso() -> str:
    return datetime.now().isoformat()


class GraphScopeSnapshot(TypedDict, total=False):
    graph_run_id: str
    graph_attempt: int
    topic: str
    phase: str
    current_iteration: int
    intake_status: str
    scope_revision_count: int
    current_scope_version: int
    approved_scope_version: int
    budget: dict[str, Any]
    task_queue_stats: dict[str, Any]
    artifact_counts: dict[str, Any]
    final_status: str


class BranchScopeSnapshot(TypedDict, total=False):
    branch_id: str
    topic: str
    summary: str
    status: str
    parent_branch_id: str | None
    objective: str
    task_kind: str
    current_stage: str
    verification_status: str
    latest_task_id: str | None
    task_ids: list[str]


class WorkerScopeSnapshot(TypedDict, total=False):
    scope_id: str
    task_id: str
    branch_id: str | None
    agent_id: str
    query: str
    objective: str
    task_kind: str
    stage: str
    attempt: int
    status: str
    artifact_ids: list[str]


@dataclass
class BranchBrief:
    id: str
    topic: str
    summary: str
    objective: str = ""
    task_kind: str = "root"
    acceptance_criteria: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    input_artifact_ids: list[str] = field(default_factory=list)
    context_id: str | None = None
    parent_branch_id: str | None = None
    parent_task_id: str | None = None
    latest_task_id: str | None = None
    latest_synthesis_id: str | None = None
    latest_verification_id: str | None = None
    current_stage: str = "planned"
    verification_status: str = "pending"
    status: ArtifactStatus = "created"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchTask:
    id: str
    goal: str
    query: str
    priority: int
    objective: str = ""
    task_kind: str = "branch_research"
    acceptance_criteria: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    input_artifact_ids: list[str] = field(default_factory=list)
    output_artifact_types: list[str] = field(default_factory=list)
    query_hints: list[str] = field(default_factory=list)
    status: TaskStatus = "ready"
    stage: TaskStage = "planned"
    title: str = ""
    aspect: str = ""
    branch_id: str | None = None
    parent_task_id: str | None = None
    parent_context_id: str | None = None
    assigned_agent_id: str | None = None
    attempts: int = 0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceCard:
    id: str
    task_id: str
    source_title: str
    source_url: str
    summary: str
    excerpt: str
    branch_id: str | None = None
    source_provider: str = ""
    published_date: str | None = None
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceCandidate:
    id: str
    task_id: str
    branch_id: str | None
    title: str
    url: str
    summary: str
    rank: int = 0
    selected: bool = True
    source_provider: str = ""
    published_date: str | None = None
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FetchedDocument:
    id: str
    task_id: str
    branch_id: str | None
    source_candidate_id: str | None
    url: str
    title: str
    content: str
    excerpt: str = ""
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidencePassage:
    id: str
    task_id: str
    branch_id: str | None
    document_id: str | None
    url: str
    text: str
    quote: str = ""
    source_title: str = ""
    snippet_hash: str = ""
    heading_path: list[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchSynthesis:
    id: str
    task_id: str
    branch_id: str | None
    objective: str
    summary: str
    findings: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    evidence_passage_ids: list[str] = field(default_factory=list)
    source_document_ids: list[str] = field(default_factory=list)
    citation_urls: list[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    id: str
    task_id: str
    branch_id: str | None
    synthesis_id: str | None
    validation_stage: ValidationStage
    outcome: ValidationOutcome
    summary: str
    recommended_action: str = ""
    evidence_urls: list[str] = field(default_factory=list)
    evidence_passage_ids: list[str] = field(default_factory=list)
    gap_ids: list[str] = field(default_factory=list)
    status: ArtifactStatus = "completed"
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeGap:
    id: str
    aspect: str
    importance: str
    reason: str
    branch_id: str | None = None
    suggested_queries: list[str] = field(default_factory=list)
    related_task_ids: list[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReportSectionDraft:
    id: str
    task_id: str
    title: str
    summary: str
    branch_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FinalReportArtifact:
    id: str
    report_markdown: str
    executive_summary: str
    citation_urls: list[str] = field(default_factory=list)
    status: ArtifactStatus = "completed"
    created_by: str = "reporter"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScopeDraft:
    id: str
    version: int
    topic: str
    research_goal: str
    research_steps: list[str] = field(default_factory=list)
    core_questions: list[str] = field(default_factory=list)
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    source_preferences: list[str] = field(default_factory=list)
    deliverable_preferences: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    intake_summary: dict[str, Any] = field(default_factory=dict)
    feedback: str = ""
    status: ScopeDraftStatus = "awaiting_review"
    created_by: str = "scope"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentRunRecord:
    id: str
    role: AgentRole
    phase: str
    status: str
    agent_id: str
    graph_run_id: str = ""
    node_id: str = ""
    task_id: str | None = None
    branch_id: str | None = None
    task_kind: str = ""
    stage: str = ""
    validation_stage: str = ""
    objective_summary: str = ""
    attempt: int = 1
    parent_task_id: str | None = None
    parent_branch_id: str | None = None
    started_at: str = field(default_factory=_now_iso)
    ended_at: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkerExecutionResult:
    task: ResearchTask
    context: ResearchWorkerContext
    source_candidates: list[SourceCandidate]
    fetched_documents: list[FetchedDocument]
    evidence_passages: list[EvidencePassage]
    branch_synthesis: BranchSynthesis | None
    evidence_cards: list[EvidenceCard]
    section_draft: ReportSectionDraft | None
    raw_results: list[dict[str, Any]]
    tokens_used: int
    searches_used: int = 0
    branch_id: str | None = None
    task_stage: str = ""
    result_status: str = "completed"
    agent_run: AgentRunRecord | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "context": asdict(self.context),
            "source_candidates": [candidate.to_dict() for candidate in self.source_candidates],
            "fetched_documents": [document.to_dict() for document in self.fetched_documents],
            "evidence_passages": [passage.to_dict() for passage in self.evidence_passages],
            "branch_synthesis": self.branch_synthesis.to_dict() if self.branch_synthesis else None,
            "evidence_cards": [card.to_dict() for card in self.evidence_cards],
            "section_draft": self.section_draft.to_dict() if self.section_draft else None,
            "raw_results": list(self.raw_results),
            "tokens_used": self.tokens_used,
            "searches_used": self.searches_used,
            "branch_id": self.branch_id,
            "task_stage": self.task_stage,
            "result_status": self.result_status,
            "agent_run": self.agent_run.to_dict() if self.agent_run else None,
            "error": self.error,
        }


__all__ = [
    "AgentRole",
    "AgentRunRecord",
    "ArtifactStatus",
    "BranchBrief",
    "BranchScopeSnapshot",
    "BranchSynthesis",
    "EvidenceCard",
    "EvidencePassage",
    "FetchedDocument",
    "FinalReportArtifact",
    "GraphScopeSnapshot",
    "KnowledgeGap",
    "ReportSectionDraft",
    "ResearchTask",
    "SourceCandidate",
    "ScopeDraft",
    "ScopeDraftStatus",
    "TaskStatus",
    "TaskStage",
    "ValidationOutcome",
    "ValidationStage",
    "VerificationResult",
    "WorkerExecutionResult",
    "WorkerScopeSnapshot",
    "_now_iso",
]
