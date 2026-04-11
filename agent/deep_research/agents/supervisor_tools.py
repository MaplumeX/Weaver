"""Control-plane tools for the Deep Research supervisor manager."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class ConductResearchInput(BaseModel):
    section_id: str = Field(min_length=1, description="Target section id to research next")
    reason: str = Field(default="", description="Why another research pass is needed")
    queries: list[str] = Field(
        default_factory=list,
        description="Focused follow-up queries for the next research pass",
    )
    replan_kind: str = Field(
        default="follow_up_research",
        description="One of: follow_up_research, counterevidence, freshness_recheck",
    )
    issue_ids: list[str] = Field(
        default_factory=list,
        description="Relevant review issue ids to target",
    )


class ReviseSectionInput(BaseModel):
    section_id: str = Field(min_length=1, description="Target section id to revise")
    reason: str = Field(default="", description="Why the section should be revised")
    target_issue_ids: list[str] = Field(
        default_factory=list,
        description="Specific review issue ids the revision should address",
    )


class CompleteReportInput(BaseModel):
    reason: str = Field(default="", description="Why the runtime can proceed to reporting")


class StopResearchInput(BaseModel):
    reason: str = Field(default="", description="Why the runtime should stop instead of continuing")


class OutlineSectionInput(BaseModel):
    title: str = Field(default="", description="Short section title")
    objective: str = Field(default="", description="Concrete objective for the section")
    core_question: str = Field(default="", description="Primary question this section must answer")
    acceptance_checks: list[str] = Field(
        default_factory=list,
        description="Checks that define when the section is sufficiently covered",
    )
    source_requirements: list[str] = Field(
        default_factory=list,
        description="Source quality or citation requirements for this section",
    )
    coverage_targets: list[str] = Field(
        default_factory=list,
        description="Coverage targets that the section should address",
    )
    source_preferences: list[str] = Field(
        default_factory=list,
        description="Preferred source types for this section",
    )
    authority_preferences: list[str] = Field(
        default_factory=list,
        description="Preferred authoritative source types for this section",
    )
    freshness_policy: str = Field(
        default="default_advisory",
        description="Freshness policy for this section",
    )


class SubmitOutlinePlanInput(BaseModel):
    reason: str = Field(default="", description="Why this outline is the right minimum plan")
    sections: list[OutlineSectionInput] = Field(
        default_factory=list,
        description="Ordered required sections for the approved scope",
    )


class StopPlanningInput(BaseModel):
    reason: str = Field(default="", description="Why planning should stop instead of producing an outline")


@dataclass
class SupervisorToolRuntime:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def record(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "tool_name": str(tool_name or "").strip(),
            "payload": copy.deepcopy(payload),
        }
        self.calls.append(event)
        return {
            "accepted": True,
            "tool_name": event["tool_name"],
        }

    def latest_call(self) -> dict[str, Any]:
        if not self.calls:
            return {}
        return copy.deepcopy(self.calls[-1])


class ConductResearchTool(BaseTool):
    name: str = "conduct_research"
    description: str = (
        "Delegate a bounded follow-up research pass for one section. "
        "Use this when evidence is missing, source diversity is weak, or freshness needs re-checking."
    )
    args_schema: type[BaseModel] = ConductResearchInput

    runtime: SupervisorToolRuntime = Field(exclude=True)

    def _run(
        self,
        section_id: str,
        reason: str = "",
        queries: list[str] | None = None,
        replan_kind: str = "follow_up_research",
        issue_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.runtime.record(
            self.name,
            {
                "section_id": str(section_id or "").strip(),
                "reason": str(reason or "").strip(),
                "queries": [str(item).strip() for item in (queries or []) if str(item).strip()],
                "replan_kind": str(replan_kind or "").strip() or "follow_up_research",
                "issue_ids": [str(item).strip() for item in (issue_ids or []) if str(item).strip()],
            },
        )


class ReviseSectionTool(BaseTool):
    name: str = "revise_section"
    description: str = (
        "Delegate a bounded revision pass for one section draft when evidence exists "
        "but wording, limitations, or claim grounding needs tightening."
    )
    args_schema: type[BaseModel] = ReviseSectionInput

    runtime: SupervisorToolRuntime = Field(exclude=True)

    def _run(
        self,
        section_id: str,
        reason: str = "",
        target_issue_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.runtime.record(
            self.name,
            {
                "section_id": str(section_id or "").strip(),
                "reason": str(reason or "").strip(),
                "target_issue_ids": [
                    str(item).strip() for item in (target_issue_ids or []) if str(item).strip()
                ],
            },
        )


class CompleteReportTool(BaseTool):
    name: str = "complete_report"
    description: str = (
        "Proceed to final or best-effort reporting when the runtime has enough reportable sections."
    )
    args_schema: type[BaseModel] = CompleteReportInput

    runtime: SupervisorToolRuntime = Field(exclude=True)

    def _run(self, reason: str = "") -> dict[str, Any]:
        return self.runtime.record(
            self.name,
            {
                "reason": str(reason or "").strip(),
            },
        )


class StopResearchTool(BaseTool):
    name: str = "stop_research"
    description: str = "Stop the runtime when no safe or useful next action remains."
    args_schema: type[BaseModel] = StopResearchInput

    runtime: SupervisorToolRuntime = Field(exclude=True)

    def _run(self, reason: str = "") -> dict[str, Any]:
        return self.runtime.record(
            self.name,
            {
                "reason": str(reason or "").strip(),
            },
        )


class SubmitOutlinePlanTool(BaseTool):
    name: str = "submit_outline_plan"
    description: str = (
        "Submit the required ordered outline plan for the approved scope. "
        "Use this when planning can proceed safely now."
    )
    args_schema: type[BaseModel] = SubmitOutlinePlanInput

    runtime: SupervisorToolRuntime = Field(exclude=True)

    def _run(
        self,
        reason: str = "",
        sections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.runtime.record(
            self.name,
            {
                "reason": str(reason or "").strip(),
                "sections": copy.deepcopy(list(sections or [])),
            },
        )


class StopPlanningTool(BaseTool):
    name: str = "stop_planning"
    description: str = "Stop outline planning when no safe or valid plan can be produced."
    args_schema: type[BaseModel] = StopPlanningInput

    runtime: SupervisorToolRuntime = Field(exclude=True)

    def _run(self, reason: str = "") -> dict[str, Any]:
        return self.runtime.record(
            self.name,
            {
                "reason": str(reason or "").strip(),
            },
        )


def build_supervisor_control_tools(runtime: SupervisorToolRuntime) -> list[BaseTool]:
    return [
        ConductResearchTool(runtime=runtime),
        ReviseSectionTool(runtime=runtime),
        CompleteReportTool(runtime=runtime),
        StopResearchTool(runtime=runtime),
    ]


def build_supervisor_outline_tools(runtime: SupervisorToolRuntime) -> list[BaseTool]:
    return [
        SubmitOutlinePlanTool(runtime=runtime),
        StopPlanningTool(runtime=runtime),
    ]


__all__ = [
    "CompleteReportInput",
    "CompleteReportTool",
    "ConductResearchInput",
    "ConductResearchTool",
    "OutlineSectionInput",
    "ReviseSectionInput",
    "ReviseSectionTool",
    "StopPlanningInput",
    "StopPlanningTool",
    "StopResearchInput",
    "StopResearchTool",
    "SubmitOutlinePlanInput",
    "SubmitOutlinePlanTool",
    "SupervisorToolRuntime",
    "build_supervisor_control_tools",
    "build_supervisor_outline_tools",
]
