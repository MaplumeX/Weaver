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
    task_ids: list[str]


class WorkerScopeSnapshot(TypedDict, total=False):
    scope_id: str
    task_id: str
    branch_id: str | None
    agent_id: str
    query: str
    attempt: int
    status: str
    artifact_ids: list[str]


@dataclass
class BranchBrief:
    id: str
    topic: str
    summary: str
    context_id: str | None = None
    parent_branch_id: str | None = None
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
    status: TaskStatus = "ready"
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
    evidence_cards: list[EvidenceCard]
    section_draft: ReportSectionDraft | None
    raw_results: list[dict[str, Any]]
    tokens_used: int
    branch_id: str | None = None
    agent_run: AgentRunRecord | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "context": asdict(self.context),
            "evidence_cards": [card.to_dict() for card in self.evidence_cards],
            "section_draft": self.section_draft.to_dict() if self.section_draft else None,
            "raw_results": list(self.raw_results),
            "tokens_used": self.tokens_used,
            "branch_id": self.branch_id,
            "agent_run": self.agent_run.to_dict() if self.agent_run else None,
            "error": self.error,
        }


__all__ = [
    "AgentRole",
    "AgentRunRecord",
    "ArtifactStatus",
    "BranchBrief",
    "BranchScopeSnapshot",
    "EvidenceCard",
    "FinalReportArtifact",
    "GraphScopeSnapshot",
    "KnowledgeGap",
    "ReportSectionDraft",
    "ResearchTask",
    "ScopeDraft",
    "ScopeDraftStatus",
    "TaskStatus",
    "WorkerExecutionResult",
    "WorkerScopeSnapshot",
    "_now_iso",
]
