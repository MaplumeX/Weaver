"""
Deep Research supervisor agent.

Unifies planning and loop-control decisions for the multi-agent deep runtime.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agent.deep_research.agents.supervisor_tools import (
    SupervisorToolRuntime,
    build_supervisor_control_tools,
    build_supervisor_outline_tools,
)
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import OutlineArtifact, OutlineSection

logger = logging.getLogger(__name__)

_TOOL_CALLING_REPLAN_KINDS = {
    "follow_up_research",
    "counterevidence",
    "freshness_recheck",
}
_DEFAULT_SECTION_SOURCE_REQUIREMENTS = [
    "至少 1 个可引用来源",
    "至少 1 段可定位 passage 支撑主结论",
]
_OUTLINE_MANAGER_PROMPT = """
You are the Deep Research supervisor manager.

You are a control-plane role, not a researcher.
You do not search the web, read sources, or write report prose directly.
You must choose exactly one control-plane tool call.

Use submit_outline_plan when the approved scope is clear enough to plan.
Use stop_planning only when the approved scope is too incomplete or contradictory to plan safely.

Outline rules:
- Produce the smallest ordered set of required sections that covers the approved scope.
- Usually map one materially distinct core question to one section.
- Every section must include a concrete objective and core_question.
- Keep titles short and specific.
- Respect explicit source, deliverable, and time constraints from the approved scope.
- Do not invent sections outside the approved scope.
- Be conservative. Fewer sections is better if coverage remains complete.

Always choose one tool call and keep reasons concise.
""".strip()
_SUPERVISOR_MANAGER_PROMPT = """
You are the Deep Research supervisor manager.

You are a control-plane role, not a researcher.
You do not search the web, read sources, or write report prose directly.
You must choose exactly one control-plane tool call.

Decision rules:
- Use conduct_research when a section needs another bounded research pass.
- Use revise_section when evidence exists but the draft should be tightened.
- Use complete_report when reporting can proceed now.
- Use stop_research only when there is no safe or useful next action.

Priorities:
1. Respect budget stop reasons.
2. Fix blocking issues before advisory issues.
3. Prefer counterevidence when source diversity is weak.
4. Prefer freshness_recheck when the gap is recency or publication-date confidence.
5. Be conservative. If the state already supports reporting, do not request another loop.

Always choose one tool call and keep reasons concise.
""".strip()


class SupervisorAction(str, Enum):
    PLAN = "plan"
    DISPATCH = "dispatch"
    REPLAN = "replan"
    RETRY_BRANCH = "retry_branch"
    PATCH_BRANCH = "patch_branch"
    SPAWN_FOLLOW_UP_BRANCH = "spawn_follow_up_branch"
    SPAWN_COUNTEREVIDENCE_BRANCH = "spawn_counterevidence_branch"
    BOUNDED_STOP = "bounded_stop"
    REPORT = "report"
    STOP = "stop"


@dataclass
class SupervisorDecision:
    action: SupervisorAction
    reasoning: str
    priority_topics: list[str] = field(default_factory=list)
    retry_task_ids: list[str] = field(default_factory=list)
    request_ids: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    target_branch_ids: list[str] = field(default_factory=list)
    task_specs: list[dict[str, Any]] = field(default_factory=list)


class ResearchSupervisor:
    """Single control-plane role for Deep Research planning and loop decisions."""

    def __init__(self, llm: BaseChatModel, config: dict[str, Any] | None = None):
        self.llm = llm
        self.config = config or {}

    def create_outline_plan(
        self,
        topic: str,
        *,
        approved_scope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._create_outline_plan_tool_calling(
            topic=topic,
            approved_scope=approved_scope or {},
        )

    def decide_section_action(
        self,
        *,
        outline: dict[str, Any],
        section_status_map: dict[str, Any],
        budget_stop_reason: str = "",
        aggregate_summary: dict[str, Any] | None = None,
        reportable_section_count: int = 0,
        pending_replans: list[dict[str, Any]] | None = None,
    ) -> SupervisorDecision:
        return self._decide_section_action_tool_calling(
            outline=outline,
            section_status_map=section_status_map,
            budget_stop_reason=budget_stop_reason,
            aggregate_summary=aggregate_summary,
            reportable_section_count=reportable_section_count,
            pending_replans=pending_replans or [],
        )

    def _decide_section_action_tool_calling(
        self,
        *,
        outline: dict[str, Any],
        section_status_map: dict[str, Any],
        budget_stop_reason: str = "",
        aggregate_summary: dict[str, Any] | None = None,
        reportable_section_count: int = 0,
        pending_replans: list[dict[str, Any]] | None = None,
    ) -> SupervisorDecision:
        pending_replans = [
            item for item in (pending_replans or []) if isinstance(item, dict) and str(item.get("section_id") or "").strip()
        ]
        runtime = SupervisorToolRuntime()
        tools = build_supervisor_control_tools(runtime)
        messages = self._build_manager_messages(
            outline=outline,
            section_status_map=section_status_map,
            budget_stop_reason=budget_stop_reason,
            aggregate_summary=aggregate_summary or {},
            reportable_section_count=reportable_section_count,
            pending_replans=pending_replans,
        )
        try:
            agent = create_agent(self.llm, tools)
            agent.invoke({"messages": messages}, config=self.config)
        except Exception as exc:
            reason = f"tool-calling manager execution failed: {exc}"
            logger.warning("[deep-research-supervisor] %s", reason)
            return SupervisorDecision(
                action=SupervisorAction.STOP,
                reasoning=reason,
            )

        tool_call = runtime.latest_call()
        if not tool_call:
            reason = "tool-calling manager produced no tool call"
            logger.warning("[deep-research-supervisor] %s", reason)
            return SupervisorDecision(
                action=SupervisorAction.STOP,
                reasoning=reason,
            )
        decision = self._decision_from_tool_call(
            tool_call,
            outline=outline,
            pending_replans=pending_replans,
        )
        if decision is not None:
            return decision
        reason = "tool-calling manager produced an invalid tool call"
        logger.warning("[deep-research-supervisor] %s", reason)
        return SupervisorDecision(
            action=SupervisorAction.STOP,
            reasoning=reason,
        )

    def _create_outline_plan_tool_calling(
        self,
        *,
        topic: str,
        approved_scope: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = SupervisorToolRuntime()
        tools = build_supervisor_outline_tools(runtime)
        messages = self._build_outline_manager_messages(
            topic=topic,
            approved_scope=approved_scope,
        )
        try:
            agent = create_agent(self.llm, tools)
            agent.invoke({"messages": messages}, config=self.config)
        except Exception as exc:
            reason = f"tool-calling outline manager execution failed: {exc}"
            logger.warning("[deep-research-supervisor] %s", reason)
            raise RuntimeError(reason) from exc

        tool_call = runtime.latest_call()
        if not tool_call:
            reason = "tool-calling outline manager produced no tool call"
            logger.warning("[deep-research-supervisor] %s", reason)
            raise RuntimeError(reason)

        outline = self._outline_from_tool_call(
            tool_call,
            topic=topic,
            approved_scope=approved_scope,
        )
        if outline:
            return outline
        reason = "tool-calling outline manager produced an invalid tool call"
        logger.warning("[deep-research-supervisor] %s", reason)
        raise RuntimeError(reason)

    def _build_manager_messages(
        self,
        *,
        outline: dict[str, Any],
        section_status_map: dict[str, Any],
        budget_stop_reason: str,
        aggregate_summary: dict[str, Any],
        reportable_section_count: int,
        pending_replans: list[dict[str, Any]],
    ) -> list[Any]:
        sections = [
            {
                "id": str(item.get("id") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "objective": str(item.get("objective") or "").strip(),
                "core_question": str(item.get("core_question") or "").strip(),
                "section_order": int(item.get("section_order", 0) or 0),
            }
            for item in (outline.get("sections") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        payload = {
            "required_section_ids": [
                str(item).strip()
                for item in (outline.get("required_section_ids") or [])
                if str(item).strip()
            ],
            "sections": sections,
            "section_status_map": {
                str(key).strip(): str(value or "").strip()
                for key, value in dict(section_status_map or {}).items()
                if str(key).strip()
            },
            "budget_stop_reason": str(budget_stop_reason or "").strip(),
            "aggregate_summary": aggregate_summary,
            "reportable_section_count": int(reportable_section_count or 0),
            "pending_replans": pending_replans,
        }
        return [
            SystemMessage(content=_SUPERVISOR_MANAGER_PROMPT),
            HumanMessage(
                content=(
                    "Choose the next control action for the Deep Research runtime.\n\n"
                    f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
                )
            ),
        ]

    def _build_outline_manager_messages(
        self,
        *,
        topic: str,
        approved_scope: dict[str, Any],
    ) -> list[Any]:
        constraints = self._dedupe_strings(list(approved_scope.get("constraints") or []))
        payload = {
            "topic": str(topic or "").strip(),
            "approved_scope": {
                "research_goal": str(approved_scope.get("research_goal") or "").strip(),
                "research_steps": self._dedupe_strings(list(approved_scope.get("research_steps") or [])),
                "core_questions": self._dedupe_strings(list(approved_scope.get("core_questions") or [])),
                "in_scope": self._dedupe_strings(list(approved_scope.get("in_scope") or [])),
                "out_of_scope": self._dedupe_strings(list(approved_scope.get("out_of_scope") or [])),
                "constraints": constraints,
                "source_preferences": self._dedupe_strings(list(approved_scope.get("source_preferences") or [])),
                "deliverable_preferences": self._dedupe_strings(
                    list(
                        approved_scope.get("deliverable_preferences")
                        or approved_scope.get("deliverable_constraints")
                        or []
                    )
                ),
                "time_boundary": self._extract_time_boundary(approved_scope, constraints=constraints),
            },
        }
        return [
            SystemMessage(content=_OUTLINE_MANAGER_PROMPT),
            HumanMessage(
                content=(
                    "Choose the outline planning action for the approved Deep Research scope.\n\n"
                    f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
                )
            ),
        ]

    def _decision_from_tool_call(
        self,
        tool_call: dict[str, Any],
        *,
        outline: dict[str, Any],
        pending_replans: list[dict[str, Any]],
    ) -> SupervisorDecision | None:
        tool_name = str(tool_call.get("tool_name") or "").strip()
        payload = tool_call.get("payload") if isinstance(tool_call.get("payload"), dict) else {}
        if not tool_name or not payload:
            return None

        pending_map = {
            str(item.get("section_id") or "").strip(): item
            for item in pending_replans
            if isinstance(item, dict) and str(item.get("section_id") or "").strip()
        }
        section_map = {
            str(item.get("id") or "").strip(): item
            for item in (outline.get("sections") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }

        if tool_name == "conduct_research":
            task_spec = self._build_research_task_spec(payload, section_map=section_map, pending_map=pending_map)
            if not task_spec:
                return None
            topic = str(task_spec.get("objective") or task_spec.get("core_question") or "").strip()
            issue_ids = self._dedupe_strings(task_spec.get("issue_ids") or [])
            return SupervisorDecision(
                action=SupervisorAction.REPLAN,
                reasoning=str(payload.get("reason") or task_spec.get("reason") or "需要补充研究").strip(),
                priority_topics=[topic] if topic else [],
                request_ids=[str(task_spec.get("section_id") or "").strip()],
                issue_ids=issue_ids,
                task_specs=[task_spec],
            )

        if tool_name == "revise_section":
            task_spec = self._build_revision_task_spec(payload, section_map=section_map, pending_map=pending_map)
            if not task_spec:
                return None
            topic = str(task_spec.get("objective") or task_spec.get("core_question") or "").strip()
            issue_ids = self._dedupe_strings(task_spec.get("issue_ids") or [])
            return SupervisorDecision(
                action=SupervisorAction.REPLAN,
                reasoning=str(payload.get("reason") or task_spec.get("reason") or "需要修订章节").strip(),
                priority_topics=[topic] if topic else [],
                request_ids=[str(task_spec.get("section_id") or "").strip()],
                issue_ids=issue_ids,
                task_specs=[task_spec],
            )

        if tool_name == "complete_report":
            return SupervisorDecision(
                action=SupervisorAction.REPORT,
                reasoning=str(payload.get("reason") or "已有可报告章节，可进入最佳努力报告生成").strip(),
            )

        if tool_name == "stop_research":
            return SupervisorDecision(
                action=SupervisorAction.STOP,
                reasoning=str(payload.get("reason") or "当前没有可执行的安全下一步").strip(),
            )
        return None

    def _outline_from_tool_call(
        self,
        tool_call: dict[str, Any],
        *,
        topic: str,
        approved_scope: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name = str(tool_call.get("tool_name") or "").strip()
        payload = tool_call.get("payload") if isinstance(tool_call.get("payload"), dict) else {}
        if not tool_name or not payload:
            return {}
        if tool_name == "stop_planning":
            reason = str(payload.get("reason") or "tool-calling outline manager stopped planning").strip()
            raise RuntimeError(reason)
        if tool_name != "submit_outline_plan":
            return {}

        raw_sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
        sections = self._normalize_outline_sections(raw_sections, approved_scope=approved_scope)
        if not sections:
            raise RuntimeError("tool-calling outline manager produced no valid sections")
        return OutlineArtifact(
            id=_new_id("outline"),
            topic=topic,
            outline_version=1,
            sections=sections,
            required_section_ids=[
                str(item.get("id") or "").strip()
                for item in sections
                if str(item.get("id") or "").strip()
            ],
            question_section_map={
                str(item.get("core_question") or "").strip(): str(item.get("id") or "").strip()
                for item in sections
                if str(item.get("core_question") or "").strip() and str(item.get("id") or "").strip()
            },
        ).to_dict()

    def _normalize_outline_sections(
        self,
        raw_sections: list[Any],
        *,
        approved_scope: dict[str, Any],
    ) -> list[dict[str, Any]]:
        shared_source_preferences = self._dedupe_strings(list(approved_scope.get("source_preferences") or []))
        deliverable_preferences = self._dedupe_strings(
            list(
                approved_scope.get("deliverable_preferences")
                or approved_scope.get("deliverable_constraints")
                or []
            )
        )
        constraints = self._dedupe_strings(list(approved_scope.get("constraints") or []))
        time_boundary = self._extract_time_boundary(approved_scope, constraints=constraints)
        sections: list[dict[str, Any]] = []
        for index, item in enumerate(raw_sections, 1):
            if not isinstance(item, dict):
                continue
            core_question = str(
                item.get("core_question")
                or item.get("objective")
                or item.get("title")
                or ""
            ).strip()
            objective = str(item.get("objective") or core_question).strip()
            if not objective or not core_question:
                continue
            title = str(item.get("title") or "").strip() or f"问题 {index}: {core_question}"
            section = OutlineSection(
                id=_new_id("section"),
                title=title,
                objective=objective,
                core_question=core_question,
                acceptance_checks=self._dedupe_strings(
                    list(item.get("acceptance_checks") or [core_question])
                ),
                source_requirements=self._dedupe_strings(
                    list(item.get("source_requirements") or _DEFAULT_SECTION_SOURCE_REQUIREMENTS)
                ),
                coverage_targets=self._dedupe_strings(
                    list(item.get("coverage_targets") or [core_question])
                ),
                source_preferences=self._dedupe_strings(
                    list(item.get("source_preferences") or shared_source_preferences)
                ),
                authority_preferences=self._dedupe_strings(
                    list(
                        item.get("authority_preferences")
                        or item.get("source_preferences")
                        or shared_source_preferences
                    )
                ),
                freshness_policy=str(item.get("freshness_policy") or "default_advisory").strip(),
                follow_up_policy="bounded",
                branch_stop_policy="coverage_or_budget",
                section_order=index,
                status="planned",
            )
            payload = section.to_dict()
            if deliverable_preferences:
                payload["deliverable_constraints"] = list(deliverable_preferences)
            if constraints:
                payload["constraints"] = list(constraints)
            if time_boundary:
                payload["time_boundary"] = time_boundary
            sections.append(payload)
        return sections

    def _build_research_task_spec(
        self,
        payload: dict[str, Any],
        *,
        section_map: dict[str, dict[str, Any]],
        pending_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        section_id = str(payload.get("section_id") or "").strip()
        if not section_id or section_id not in section_map:
            return {}
        section = section_map.get(section_id) or {}
        pending = pending_map.get(section_id) or {}
        replan_kind = str(payload.get("replan_kind") or "").strip().lower()
        if replan_kind not in _TOOL_CALLING_REPLAN_KINDS:
            issue_types = self._dedupe_strings(pending.get("issue_types") or [])
            if bool(pending.get("needs_counterevidence_query")) or "limited_source_diversity" in issue_types:
                replan_kind = "counterevidence"
            else:
                replan_kind = "follow_up_research"
        follow_up_queries = self._dedupe_strings(
            [
                *list(payload.get("queries") or []),
                *list(pending.get("follow_up_queries") or []),
                *list(pending.get("missing_topics") or []),
                *list(pending.get("open_questions") or []),
                str(section.get("core_question") or "").strip(),
                str(section.get("objective") or "").strip(),
            ]
        )
        if replan_kind == "freshness_recheck" and not follow_up_queries:
            objective = str(section.get("objective") or section.get("core_question") or "").strip()
            if objective:
                follow_up_queries = [f"{objective} latest official update"]
        return {
            "section_id": section_id,
            "section_order": int(section.get("section_order", pending.get("section_order", 0)) or 0),
            "task_kind": "section_research",
            "replan_kind": replan_kind,
            "reason": str(payload.get("reason") or pending.get("reason") or "需要补充研究").strip(),
            "issue_types": self._dedupe_strings(pending.get("issue_types") or []),
            "issue_ids": self._dedupe_strings(
                [
                    *list(payload.get("issue_ids") or []),
                    *list(pending.get("issue_ids") or []),
                ]
            ),
            "follow_up_queries": follow_up_queries,
            "objective": str(section.get("objective") or pending.get("objective") or "").strip(),
            "core_question": str(section.get("core_question") or pending.get("core_question") or "").strip(),
            "reportability": str(pending.get("reportability") or "").strip(),
            "quality_band": str(pending.get("quality_band") or "").strip(),
        }

    def _build_revision_task_spec(
        self,
        payload: dict[str, Any],
        *,
        section_map: dict[str, dict[str, Any]],
        pending_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        section_id = str(payload.get("section_id") or "").strip()
        if not section_id or section_id not in section_map:
            return {}
        section = section_map.get(section_id) or {}
        pending = pending_map.get(section_id) or {}
        return {
            "section_id": section_id,
            "section_order": int(section.get("section_order", pending.get("section_order", 0)) or 0),
            "task_kind": "section_revision",
            "replan_kind": "revision",
            "reason": str(payload.get("reason") or pending.get("reason") or "需要修订章节").strip(),
            "issue_types": self._dedupe_strings(pending.get("issue_types") or []),
            "issue_ids": self._dedupe_strings(
                [
                    *list(payload.get("target_issue_ids") or []),
                    *list(pending.get("issue_ids") or []),
                ]
            ),
            "follow_up_queries": [],
            "objective": str(section.get("objective") or pending.get("objective") or "").strip(),
            "core_question": str(section.get("core_question") or pending.get("core_question") or "").strip(),
            "reportability": str(pending.get("reportability") or "").strip(),
            "quality_band": str(pending.get("quality_band") or "").strip(),
        }

    @staticmethod
    def _dedupe_strings(values: list[Any]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in values:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            deduped.append(text)
        return deduped

    @staticmethod
    def _extract_time_boundary(
        scope: dict[str, Any],
        *,
        constraints: list[str] | None = None,
    ) -> str:
        time_boundary = str(scope.get("time_boundary") or "").strip()
        if time_boundary:
            return time_boundary
        for item in constraints or []:
            if item.lower().startswith("time range:"):
                return item.split(":", 1)[1].strip()
        return ""


__all__ = [
    "ResearchSupervisor",
    "SupervisorAction",
    "SupervisorDecision",
]
