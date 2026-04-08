"""
Runtime state for a bounded branch-scoped research loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BranchResearchState:
    task_id: str
    section_id: str | None
    branch_id: str | None
    topic: str
    objective: str
    acceptance_criteria: list[str] = field(default_factory=list)
    existing_summary: str = ""
    source_preferences: list[str] = field(default_factory=list)
    language_hints: list[str] = field(default_factory=list)
    coverage_targets: list[str] = field(default_factory=list)
    freshness_policy: str = ""
    authority_preferences: list[str] = field(default_factory=list)
    round_index: int = 0
    max_rounds: int = 3
    max_results_per_query: int = 5
    max_follow_up_queries_per_round: int = 2
    executed_queries: list[str] = field(default_factory=list)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    passages: list[dict[str, Any]] = field(default_factory=list)
    query_rounds: list[dict[str, Any]] = field(default_factory=list)
    research_decisions: list[dict[str, Any]] = field(default_factory=list)
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    quality_summary: dict[str, Any] = field(default_factory=dict)
    contradiction_summary: dict[str, Any] = field(default_factory=dict)
    grounding_summary: dict[str, Any] = field(default_factory=dict)
    open_gaps: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    stop_reason: str = ""
