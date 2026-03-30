"""
Artifact and task schema contracts for the multi-agent deep runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from agent.core.context import ResearchWorkerContext

TaskStatus = Literal["ready", "in_progress", "blocked", "completed", "failed", "cancelled"]
ArtifactStatus = Literal["created", "updated", "completed", "discarded"]
AgentRole = Literal["coordinator", "planner", "researcher", "verifier", "reporter"]


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class BranchBrief:
    id: str
    topic: str
    summary: str
    context_id: Optional[str] = None
    status: ArtifactStatus = "created"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class ResearchTask:
    id: str
    goal: str
    query: str
    priority: int
    status: TaskStatus = "ready"
    title: str = ""
    aspect: str = ""
    parent_task_id: Optional[str] = None
    parent_context_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    attempts: int = 0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    completed_at: Optional[str] = None
    last_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceCard:
    id: str
    task_id: str
    source_title: str
    source_url: str
    summary: str
    excerpt: str
    source_provider: str = ""
    published_date: Optional[str] = None
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGap:
    id: str
    aspect: str
    importance: str
    reason: str
    suggested_queries: List[str] = field(default_factory=list)
    related_task_ids: List[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class ReportSectionDraft:
    id: str
    task_id: str
    title: str
    summary: str
    evidence_ids: List[str] = field(default_factory=list)
    status: ArtifactStatus = "created"
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class FinalReportArtifact:
    id: str
    report_markdown: str
    executive_summary: str
    citation_urls: List[str] = field(default_factory=list)
    status: ArtifactStatus = "completed"
    created_by: str = "reporter"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class AgentRunRecord:
    id: str
    role: AgentRole
    phase: str
    status: str
    agent_id: str
    task_id: Optional[str] = None
    started_at: str = field(default_factory=_now_iso)
    ended_at: str = ""
    summary: str = ""


@dataclass
class WorkerExecutionResult:
    task: ResearchTask
    context: ResearchWorkerContext
    evidence_cards: List[EvidenceCard]
    section_draft: Optional[ReportSectionDraft]
    raw_results: List[Dict[str, Any]]
    tokens_used: int


__all__ = [
    "AgentRole",
    "AgentRunRecord",
    "ArtifactStatus",
    "BranchBrief",
    "EvidenceCard",
    "FinalReportArtifact",
    "KnowledgeGap",
    "ReportSectionDraft",
    "ResearchTask",
    "TaskStatus",
    "WorkerExecutionResult",
    "_now_iso",
]
