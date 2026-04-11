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
AgentRole = Literal["clarify", "scope", "supervisor", "researcher", "reviewer", "revisor", "reporter"]
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

def _now_iso() -> str:
    return datetime.now().isoformat()


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
    source_preferences: list[str] = field(default_factory=list)
    authority_preferences: list[str] = field(default_factory=list)
    coverage_targets: list[str] = field(default_factory=list)
    language_hints: list[str] = field(default_factory=list)
    deliverable_constraints: list[str] = field(default_factory=list)
    source_requirements: list[str] = field(default_factory=list)
    freshness_policy: str = ""
    time_boundary: str = ""
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
    coverage_targets: list[str] = field(default_factory=list)
    source_preferences: list[str] = field(default_factory=list)
    authority_preferences: list[str] = field(default_factory=list)
    freshness_policy: str = "default_advisory"
    follow_up_policy: str = "bounded"
    branch_stop_policy: str = "default"
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
    reportability: str = "insufficient"
    quality_band: str = "insufficient"
    objective_score: float = 0.0
    grounding_score: float = 0.0
    freshness_score: float = 0.0
    contradiction_score: float = 0.0
    risk_flags: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    needs_manual_review: bool = False
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
    reportability: str = ""
    quality_band: str = ""
    key_claims_grounded_ratio: float = 0.0
    objective_met: bool = False
    has_primary_sources: bool = False
    freshness_warning: str = ""
    risk_flags: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    needs_manual_review: bool = False
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
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    quality_summary: dict[str, Any] = field(default_factory=dict)
    contradiction_summary: dict[str, Any] = field(default_factory=dict)
    grounding_summary: dict[str, Any] = field(default_factory=dict)
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
class BranchQueryRoundArtifact:
    id: str
    task_id: str
    section_id: str | None
    branch_id: str | None
    round_index: int
    queries: list[str] = field(default_factory=list)
    search_result_count: int = 0
    source_count: int = 0
    document_count: int = 0
    passage_count: int = 0
    new_source_count: int = 0
    coverage_ready: bool = False
    notes: str = ""
    created_by: str = "researcher"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchCoverageArtifact:
    id: str
    task_id: str
    section_id: str | None
    branch_id: str | None
    criteria: list[dict[str, Any]] = field(default_factory=list)
    covered_count: int = 0
    partial_count: int = 0
    missing_count: int = 0
    missing_topics: list[str] = field(default_factory=list)
    coverage_ready: bool = False
    created_by: str = "researcher"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchQualityArtifact:
    id: str
    task_id: str
    section_id: str | None
    branch_id: str | None
    authority_score: float = 0.0
    freshness_score: float = 0.0
    source_diversity_score: float = 0.0
    evidence_density_score: float = 0.0
    objective_alignment_score: float = 0.0
    quality_ready: bool = False
    notes: str = ""
    created_by: str = "researcher"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchContradictionArtifact:
    id: str
    task_id: str
    section_id: str | None
    branch_id: str | None
    has_material_conflict: bool = False
    conflict_count: int = 0
    conflict_source_urls: list[str] = field(default_factory=list)
    conflict_notes: list[str] = field(default_factory=list)
    needs_counterevidence_query: bool = False
    created_by: str = "researcher"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchGroundingArtifact:
    id: str
    task_id: str
    section_id: str | None
    branch_id: str | None
    claims: list[dict[str, Any]] = field(default_factory=list)
    total_claim_count: int = 0
    grounded_claim_count: int = 0
    primary_grounding_ratio: float = 0.0
    secondary_grounding_ratio: float = 0.0
    grounding_ready: bool = False
    created_by: str = "researcher"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchDecisionArtifact:
    id: str
    task_id: str
    section_id: str | None
    branch_id: str | None
    round_index: int
    action: str
    reason: str = ""
    follow_up_queries: list[str] = field(default_factory=list)
    stop_reason: str = ""
    notes: str = ""
    created_by: str = "researcher"
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
    requested_tools: list[str] = field(default_factory=list)
    resolved_tools: list[str] = field(default_factory=list)
    parent_task_id: str | None = None
    parent_section_id: str | None = None
    parent_branch_id: str | None = None
    started_at: str = field(default_factory=_now_iso)
    ended_at: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "AgentRole",
    "AgentRunRecord",
    "ArtifactStatus",
    "BranchContradictionArtifact",
    "BranchCoverageArtifact",
    "BranchDecisionArtifact",
    "BranchGroundingArtifact",
    "BranchQualityArtifact",
    "BranchQueryRoundArtifact",
    "ClaimUnit",
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
]
