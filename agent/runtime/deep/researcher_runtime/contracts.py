"""
Typed contracts for the branch-scoped researcher runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BranchQueryPlan:
    queries: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchCoverageSummary:
    criteria: list[dict[str, Any]] = field(default_factory=list)
    covered_count: int = 0
    partial_count: int = 0
    missing_count: int = 0
    missing_topics: list[str] = field(default_factory=list)
    coverage_ready: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchQualitySummary:
    authority_score: float = 0.0
    freshness_score: float = 0.0
    source_diversity_score: float = 0.0
    evidence_density_score: float = 0.0
    objective_alignment_score: float = 0.0
    quality_ready: bool = False
    gaps: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchContradictionSummary:
    has_material_conflict: bool = False
    conflict_count: int = 0
    conflict_source_urls: list[str] = field(default_factory=list)
    conflict_notes: list[str] = field(default_factory=list)
    needs_counterevidence_query: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchGroundingSummary:
    claims: list[dict[str, Any]] = field(default_factory=list)
    total_claim_count: int = 0
    grounded_claim_count: int = 0
    primary_grounding_ratio: float = 0.0
    secondary_grounding_ratio: float = 0.0
    grounding_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BranchDecision:
    action: str
    reason: str = ""
    follow_up_queries: list[str] = field(default_factory=list)
    stop_reason: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
