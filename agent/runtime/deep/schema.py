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
AgentRole = Literal["clarify", "scope", "supervisor", "researcher", "verifier", "reporter"]
TaskStage = Literal[
    "planned",
    "dispatch",
    "search",
    "read",
    "extract",
    "synthesize",
    "verify",
    "grounding_check",
    "coverage_evaluation",
    "consistency_check",
    "revision",
    "challenge",
    "compare",
    "submit",
    "claim_check",
    "coverage_check",
    "reported",
]
ValidationStage = Literal[
    "claim_check",
    "coverage_check",
    "consistency_check",
    "challenge",
    "compare",
]
ValidationOutcome = Literal["passed", "failed", "needs_follow_up"]
CoordinationRequestType = Literal[
    "retry_branch",
    "need_counterevidence",
    "contradiction_found",
    "outline_gap",
    "blocked_by_tooling",
]
CoordinationRequestStatus = Literal["open", "accepted", "resolved", "dismissed"]
SubmissionKind = Literal["research_bundle", "verification_bundle", "report_bundle"]
GroundingStatus = Literal["grounded", "unsupported", "contradicted", "unresolved"]
ObligationStatus = Literal["satisfied", "partially_satisfied", "unsatisfied", "unresolved"]
ConsistencyStatus = Literal["consistent", "contradicted", "unresolved"]
RevisionIssueSeverity = Literal["low", "medium", "high", "critical"]
RevisionIssueStatus = Literal["open", "accepted", "resolved", "superseded", "waived"]
RevisionKind = Literal["patch_branch", "spawn_follow_up_branch", "spawn_counterevidence_branch"]

REGISTERED_COORDINATION_REQUEST_TYPES: tuple[CoordinationRequestType, ...] = (
    "retry_branch",
    "need_counterevidence",
    "contradiction_found",
    "outline_gap",
    "blocked_by_tooling",
)


def _now_iso() -> str:
    return datetime.now().isoformat()


def is_registered_coordination_request_type(value: str) -> bool:
    return str(value or "").strip() in REGISTERED_COORDINATION_REQUEST_TYPES


def validate_coordination_request_type(value: str) -> CoordinationRequestType:
    normalized = str(value or "").strip()
    if not is_registered_coordination_request_type(normalized):
        allowed = ", ".join(REGISTERED_COORDINATION_REQUEST_TYPES)
        raise ValueError(f"Unsupported coordination request type: {value!r}. Allowed: {allowed}")
    return normalized  # type: ignore[return-value]


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
    supervisor_phase: str
    supervisor_plan_id: str
    research_brief_id: str
    task_ledger_id: str
    progress_ledger_id: str
    outline_id: str
    outline_status: str
    latest_supervisor_decision_id: str
    open_request_count: int
    budget: dict[str, Any]
    task_queue_stats: dict[str, Any]
    artifact_counts: dict[str, Any]
    final_status: str
    terminal_status: str
    terminal_reason: str


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
    latest_submission_id: str | None
    latest_revision_brief_id: str | None
    open_issue_ids: list[str]
    resolved_issue_ids: list[str]
    open_request_ids: list[str]
    task_ids: list[str]


class WorkerScopeSnapshot(TypedDict, total=False):
    scope_id: str
    task_id: str
    branch_id: str | None
    agent_id: str
    role: AgentRole
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
    latest_revision_brief_id: str | None = None
    current_stage: str = "planned"
    verification_status: str = "pending"
    answer_unit_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    obligation_ids: list[str] = field(default_factory=list)
    open_issue_ids: list[str] = field(default_factory=list)
    resolved_issue_ids: list[str] = field(default_factory=list)
    revision_count: int = 0
    lineage: dict[str, Any] = field(default_factory=dict)
    status: ArtifactStatus = "created"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchBriefArtifact:
    id: str
    scope_id: str
    scope_version: int
    topic: str
    user_goal: str
    research_goal: str
    core_questions: list[str] = field(default_factory=list)
    coverage_dimensions: list[str] = field(default_factory=list)
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    deliverable_constraints: list[str] = field(default_factory=list)
    source_preferences: list[str] = field(default_factory=list)
    time_boundary: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    status: ArtifactStatus = "completed"
    created_by: str = "scope"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

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
    revision_kind: str = ""
    revision_of_task_id: str | None = None
    revision_brief_id: str | None = None
    target_issue_ids: list[str] = field(default_factory=list)
    resolved_issue_ids: list[str] = field(default_factory=list)
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
    locator: dict[str, Any] = field(default_factory=dict)
    source_published_date: str | None = None
    passage_kind: str = "stable_passage"
    admissible: bool = True
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimUnit:
    id: str
    task_id: str
    branch_id: str | None
    claim: str
    claim_provenance: dict[str, Any] = field(default_factory=dict)
    evidence_passage_ids: list[str] = field(default_factory=list)
    citation_urls: list[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerUnit:
    id: str
    task_id: str
    branch_id: str | None
    text: str
    unit_type: str = "claim"
    provenance: dict[str, Any] = field(default_factory=dict)
    supporting_passage_ids: list[str] = field(default_factory=list)
    citation_urls: list[str] = field(default_factory=list)
    obligation_ids: list[str] = field(default_factory=list)
    dependent_answer_unit_ids: list[str] = field(default_factory=list)
    required: bool = True
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_claim_unit(self) -> ClaimUnit:
        return ClaimUnit(
            id=self.id,
            task_id=self.task_id,
            branch_id=self.branch_id,
            claim=self.text,
            claim_provenance=dict(self.provenance),
            evidence_passage_ids=list(self.supporting_passage_ids),
            citation_urls=list(self.citation_urls),
            status=self.status,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata={
                **dict(self.metadata),
                "unit_type": self.unit_type,
                "obligation_ids": list(self.obligation_ids),
                "dependent_answer_unit_ids": list(self.dependent_answer_unit_ids),
                "required": self.required,
            },
        )

    @classmethod
    def from_claim_unit(cls, claim_unit: ClaimUnit) -> "AnswerUnit":
        metadata = dict(claim_unit.metadata or {})
        return cls(
            id=claim_unit.id,
            task_id=claim_unit.task_id,
            branch_id=claim_unit.branch_id,
            text=claim_unit.claim,
            unit_type=str(metadata.get("unit_type") or "claim"),
            provenance=dict(claim_unit.claim_provenance or {}),
            supporting_passage_ids=list(claim_unit.evidence_passage_ids),
            citation_urls=list(claim_unit.citation_urls),
            obligation_ids=list(metadata.get("obligation_ids") or []),
            dependent_answer_unit_ids=list(metadata.get("dependent_answer_unit_ids") or []),
            required=bool(metadata.get("required", True)),
            status=claim_unit.status,
            created_by=claim_unit.created_by,
            created_at=claim_unit.created_at,
            updated_at=claim_unit.updated_at,
            metadata=metadata,
        )


@dataclass
class CoverageObligation:
    id: str
    task_id: str
    branch_id: str | None
    source: str
    target: str
    completion_criteria: list[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_by: str = "supervisor"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimGroundingResult:
    id: str
    task_id: str
    branch_id: str | None
    claim_id: str
    status: GroundingStatus
    summary: str
    evidence_urls: list[str] = field(default_factory=list)
    evidence_passage_ids: list[str] = field(default_factory=list)
    severity: RevisionIssueSeverity = "medium"
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoverageEvaluationResult:
    id: str
    task_id: str
    branch_id: str | None
    obligation_id: str
    status: ObligationStatus
    summary: str
    evidence_urls: list[str] = field(default_factory=list)
    evidence_passage_ids: list[str] = field(default_factory=list)
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsistencyResult:
    id: str
    task_id: str | None
    branch_id: str | None
    claim_ids: list[str]
    related_branch_ids: list[str]
    status: ConsistencyStatus
    summary: str
    evidence_urls: list[str] = field(default_factory=list)
    evidence_passage_ids: list[str] = field(default_factory=list)
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RevisionIssue:
    id: str
    task_id: str | None
    branch_id: str | None
    issue_type: str
    summary: str
    status: RevisionIssueStatus = "open"
    severity: RevisionIssueSeverity = "medium"
    blocking: bool = True
    recommended_action: str = ""
    claim_ids: list[str] = field(default_factory=list)
    obligation_ids: list[str] = field(default_factory=list)
    consistency_result_ids: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    evidence_urls: list[str] = field(default_factory=list)
    evidence_passage_ids: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)
    resolution: dict[str, Any] = field(default_factory=dict)
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchRevisionBrief:
    id: str
    revision_kind: RevisionKind
    target_branch_id: str | None
    target_task_id: str | None
    issue_ids: list[str]
    summary: str
    source_branch_id: str | None = None
    source_task_id: str | None = None
    reusable_artifact_ids: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_by: str = "supervisor"
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
    answer_unit_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    resolved_issue_ids: list[str] = field(default_factory=list)
    revision_brief_id: str | None = None
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
class BranchValidationSummary:
    id: str
    task_id: str
    branch_id: str | None
    synthesis_id: str | None = None
    answer_unit_ids: list[str] = field(default_factory=list)
    obligation_ids: list[str] = field(default_factory=list)
    consistency_result_ids: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    blocking_issue_ids: list[str] = field(default_factory=list)
    supported_answer_unit_ids: list[str] = field(default_factory=list)
    partially_supported_answer_unit_ids: list[str] = field(default_factory=list)
    unsupported_answer_unit_ids: list[str] = field(default_factory=list)
    contradicted_answer_unit_ids: list[str] = field(default_factory=list)
    satisfied_obligation_ids: list[str] = field(default_factory=list)
    partially_satisfied_obligation_ids: list[str] = field(default_factory=list)
    unsatisfied_obligation_ids: list[str] = field(default_factory=list)
    blocking: bool = False
    ready_for_report: bool = False
    advisory_notes: list[str] = field(default_factory=list)
    summary: str = ""
    status: ArtifactStatus = "completed"
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskLedgerArtifact:
    id: str
    research_brief_id: str | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)
    issue_statuses: list[dict[str, Any]] = field(default_factory=list)
    status: ArtifactStatus = "updated"
    created_by: str = "supervisor"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProgressLedgerArtifact:
    id: str
    research_brief_id: str | None = None
    phase: str = ""
    current_iteration: int = 0
    active_request_ids: list[str] = field(default_factory=list)
    latest_decision: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[dict[str, Any]] = field(default_factory=list)
    verification_summary: dict[str, Any] = field(default_factory=dict)
    issue_statuses: list[dict[str, Any]] = field(default_factory=list)
    revision_lineage: list[dict[str, Any]] = field(default_factory=list)
    outline_status: str = "pending"
    budget_stop_reason: str = ""
    stop_reason: str = ""
    status: ArtifactStatus = "updated"
    created_by: str = "supervisor"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoverageMatrixArtifact:
    id: str
    research_brief_id: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    overall_coverage: float = 0.0
    status: ArtifactStatus = "completed"
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContradictionRegistryArtifact:
    id: str
    research_brief_id: str | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)
    status: ArtifactStatus = "completed"
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissingEvidenceListArtifact:
    id: str
    research_brief_id: str | None = None
    items: list[dict[str, Any]] = field(default_factory=list)
    status: ArtifactStatus = "completed"
    created_by: str = "verifier"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutlineArtifact:
    id: str
    research_brief_id: str | None = None
    sections: list[dict[str, Any]] = field(default_factory=list)
    blocking_gaps: list[dict[str, Any]] = field(default_factory=list)
    is_ready: bool = False
    status: ArtifactStatus = "created"
    created_by: str = "reporter"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoordinationRequest:
    id: str
    request_type: CoordinationRequestType
    summary: str
    branch_id: str | None = None
    task_id: str | None = None
    requested_by: str = ""
    status: CoordinationRequestStatus = "open"
    priority: int = 0
    artifact_ids: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)
    impact_scope: str = ""
    reason: str = ""
    blocking_level: str = "blocking"
    suggested_next_action: str = ""
    target_branch_id: str | None = None
    target_task_id: str | None = None
    revision_brief_id: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.request_type = str(self.request_type or "").strip()  # type: ignore[assignment]
        self.reason = self.reason or self.summary
        self.impact_scope = self.impact_scope or str(self.branch_id or self.task_id or "").strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchSubmission:
    id: str
    submission_kind: SubmissionKind
    summary: str
    task_id: str | None = None
    branch_id: str | None = None
    created_by: str = ""
    result_status: str = "completed"
    status: ArtifactStatus = "completed"
    stage: str = ""
    validation_stage: str = ""
    artifact_ids: list[str] = field(default_factory=list)
    request_ids: list[str] = field(default_factory=list)
    answer_unit_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    obligation_ids: list[str] = field(default_factory=list)
    consistency_result_ids: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    resolved_issue_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SupervisorDecisionArtifact:
    id: str
    phase: str
    decision_type: str
    summary: str
    branch_id: str | None = None
    task_ids: list[str] = field(default_factory=list)
    request_ids: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    revision_brief_ids: list[str] = field(default_factory=list)
    next_step: str = ""
    planning_mode: str = ""
    iteration: int = 0
    status: ArtifactStatus = "completed"
    created_by: str = "supervisor"
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
    advisory: bool = True
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
    coordination_requests: list[CoordinationRequest]
    submission: ResearchSubmission | None
    raw_results: list[dict[str, Any]]
    tokens_used: int
    searches_used: int = 0
    branch_id: str | None = None
    task_stage: str = ""
    result_status: str = "completed"
    agent_run: AgentRunRecord | None = None
    error: str = ""
    answer_units: list[AnswerUnit] = field(default_factory=list)
    claim_units: list[ClaimUnit] = field(default_factory=list)
    resolved_issue_ids: list[str] = field(default_factory=list)

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
            "coordination_requests": [request.to_dict() for request in self.coordination_requests],
            "submission": self.submission.to_dict() if self.submission else None,
            "raw_results": list(self.raw_results),
            "tokens_used": self.tokens_used,
            "searches_used": self.searches_used,
            "branch_id": self.branch_id,
            "task_stage": self.task_stage,
            "result_status": self.result_status,
            "agent_run": self.agent_run.to_dict() if self.agent_run else None,
            "error": self.error,
            "answer_units": [item.to_dict() for item in self.answer_units],
            "claim_units": [item.to_dict() for item in self.claim_units],
            "resolved_issue_ids": list(self.resolved_issue_ids),
        }


__all__ = [
    "AgentRole",
    "AgentRunRecord",
    "ArtifactStatus",
    "AnswerUnit",
    "BranchBrief",
    "BranchRevisionBrief",
    "BranchScopeSnapshot",
    "BranchSynthesis",
    "BranchValidationSummary",
    "ClaimGroundingResult",
    "ClaimUnit",
    "ConsistencyResult",
    "ContradictionRegistryArtifact",
    "CoordinationRequest",
    "CoordinationRequestStatus",
    "CoordinationRequestType",
    "CoverageEvaluationResult",
    "CoverageMatrixArtifact",
    "CoverageObligation",
    "EvidenceCard",
    "EvidencePassage",
    "FetchedDocument",
    "FinalReportArtifact",
    "GraphScopeSnapshot",
    "GroundingStatus",
    "is_registered_coordination_request_type",
    "KnowledgeGap",
    "MissingEvidenceListArtifact",
    "ObligationStatus",
    "OutlineArtifact",
    "ProgressLedgerArtifact",
    "REGISTERED_COORDINATION_REQUEST_TYPES",
    "ReportSectionDraft",
    "ResearchBriefArtifact",
    "ResearchSubmission",
    "ResearchTask",
    "RevisionIssue",
    "RevisionIssueStatus",
    "RevisionIssueSeverity",
    "RevisionKind",
    "SourceCandidate",
    "ScopeDraft",
    "ScopeDraftStatus",
    "SubmissionKind",
    "SupervisorDecisionArtifact",
    "TaskLedgerArtifact",
    "TaskStatus",
    "TaskStage",
    "ValidationOutcome",
    "ValidationStage",
    "VerificationResult",
    "WorkerExecutionResult",
    "WorkerScopeSnapshot",
    "_now_iso",
    "validate_coordination_request_type",
]
