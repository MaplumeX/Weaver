"""
Artifact, scope and state contracts for the lightweight multi-agent deep runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

TaskStatus = Literal["ready", "in_progress", "blocked", "completed", "failed", "cancelled"]
ArtifactStatus = Literal["created", "updated", "completed", "discarded"]
ScopeDraftStatus = Literal["awaiting_review", "revision_requested", "approved"]
AgentRole = Literal["clarify", "scope", "supervisor", "researcher", "reviewer", "revisor", "verifier", "reporter"]
ControlPlaneAgent = Literal["clarify", "scope", "supervisor"]
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

REGISTERED_CONTROL_PLANE_AGENTS: tuple[ControlPlaneAgent, ...] = (
    "clarify",
    "scope",
    "supervisor",
)


def _now_iso() -> str:
    return datetime.now().isoformat()


def is_control_plane_agent(value: str) -> bool:
    return str(value or "").strip() in REGISTERED_CONTROL_PLANE_AGENTS


def validate_control_plane_agent(value: str) -> ControlPlaneAgent:
    normalized = str(value or "").strip()
    if not is_control_plane_agent(normalized):
        allowed = ", ".join(REGISTERED_CONTROL_PLANE_AGENTS)
        raise ValueError(f"Unsupported control-plane agent: {value!r}. Allowed: {allowed}")
    return normalized  # type: ignore[return-value]


@dataclass
class ControlPlaneHandoff:
    id: str
    from_agent: ControlPlaneAgent
    to_agent: ControlPlaneAgent
    reason: str
    context_refs: list[str] = field(default_factory=list)
    scope_snapshot: dict[str, Any] = field(default_factory=dict)
    review_state: str = ""
    created_at: str = field(default_factory=_now_iso)
    created_by: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.from_agent = validate_control_plane_agent(self.from_agent)
        self.to_agent = validate_control_plane_agent(self.to_agent)
        self.reason = str(self.reason or "").strip()
        self.context_refs = [str(item).strip() for item in self.context_refs if str(item).strip()]
        self.scope_snapshot = dict(self.scope_snapshot or {})
        self.review_state = str(self.review_state or "").strip()
        self.created_at = str(self.created_at or _now_iso())
        self.created_by = str(self.created_by or self.from_agent).strip()
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchTask:
    id: str
    goal: str
    query: str
    priority: int
    objective: str = ""
    task_kind: str = "section_research"
    acceptance_criteria: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    input_artifact_ids: list[str] = field(default_factory=list)
    output_artifact_types: list[str] = field(default_factory=list)
    query_hints: list[str] = field(default_factory=list)
    status: TaskStatus = "ready"
    stage: TaskStage = "planned"
    title: str = ""
    aspect: str = ""
    section_id: str | None = None
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
class ResearchPlanArtifact:
    id: str
    scope_id: str | None = None
    tasks: list[dict[str, Any]] = field(default_factory=list)
    status: ArtifactStatus = "completed"
    created_by: str = "supervisor"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutlineSection:
    id: str
    title: str
    objective: str
    core_question: str
    acceptance_checks: list[str] = field(default_factory=list)
    source_requirements: list[str] = field(default_factory=list)
    freshness_policy: str = "default_advisory"
    section_order: int = 1
    status: str = "planned"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutlineArtifact:
    id: str
    topic: str
    outline_version: int = 1
    sections: list[dict[str, Any]] = field(default_factory=list)
    required_section_ids: list[str] = field(default_factory=list)
    question_section_map: dict[str, str] = field(default_factory=dict)
    status: ArtifactStatus = "completed"
    created_by: str = "supervisor"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceBundle:
    id: str
    task_id: str
    section_id: str | None
    branch_id: str | None
    sources: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    passages: list[dict[str, Any]] = field(default_factory=list)
    source_count: int = 0
    status: ArtifactStatus = "completed"
    created_by: str = "researcher"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimUnit:
    id: str
    text: str
    importance: str = "secondary"
    evidence_passage_ids: list[str] = field(default_factory=list)
    evidence_urls: list[str] = field(default_factory=list)
    grounded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SectionReviewArtifact:
    id: str
    task_id: str
    section_id: str
    branch_id: str | None
    verdict: str
    objective_score: float = 0.0
    grounding_score: float = 0.0
    freshness_score: float = 0.0
    contradiction_score: float = 0.0
    blocking_issues: list[dict[str, Any]] = field(default_factory=list)
    advisory_issues: list[dict[str, Any]] = field(default_factory=list)
    follow_up_queries: list[str] = field(default_factory=list)
    notes: str = ""
    created_by: str = "reviewer"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SectionCertificationArtifact:
    id: str
    section_id: str
    certified: bool
    key_claims_grounded_ratio: float = 0.0
    objective_met: bool = False
    has_primary_sources: bool = False
    freshness_warning: str = ""
    limitations: list[str] = field(default_factory=list)
    blocking_issue_count: int = 0
    advisory_issue_count: int = 0
    created_by: str = "reviewer"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SectionDraftArtifact:
    id: str
    task_id: str
    section_id: str
    branch_id: str | None
    title: str
    objective: str = ""
    core_question: str = ""
    summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    confidence_note: str = ""
    source_urls: list[str] = field(default_factory=list)
    claim_units: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    review_artifact_id: str | None = None
    certification_artifact_id: str | None = None
    evidence_bundle_id: str | None = None
    review_status: str = "pending"
    certified: bool = False
    status: ArtifactStatus = "completed"
    created_by: str = "researcher"
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
    clarification_context: dict[str, Any] = field(default_factory=dict)
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
    section_id: str | None = None
    branch_id: str | None = None
    task_kind: str = ""
    stage: str = ""
    validation_stage: str = ""
    objective_summary: str = ""
    attempt: int = 1
    parent_task_id: str | None = None
    parent_section_id: str | None = None
    parent_branch_id: str | None = None
    started_at: str = field(default_factory=_now_iso)
    ended_at: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "REGISTERED_CONTROL_PLANE_AGENTS",
    "AgentRole",
    "AgentRunRecord",
    "ArtifactStatus",
    "ClaimUnit",
    "ControlPlaneAgent",
    "ControlPlaneHandoff",
    "EvidenceBundle",
    "FinalReportArtifact",
    "OutlineArtifact",
    "OutlineSection",
    "ResearchPlanArtifact",
    "ResearchTask",
    "ScopeDraft",
    "ScopeDraftStatus",
    "SectionCertificationArtifact",
    "SectionDraftArtifact",
    "SectionReviewArtifact",
    "TaskStage",
    "TaskStatus",
    "_now_iso",
    "is_control_plane_agent",
    "validate_control_plane_agent",
]
