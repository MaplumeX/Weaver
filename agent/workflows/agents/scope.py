"""
Deep Research scope agent.

Generates the structured scope draft that must be approved before planning.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


SCOPE_PROMPT = """
# Role
You are the Deep Research scope agent.

# Original topic
{topic}

# Normalized intake summary
{intake_summary}

# Previous scope draft
{previous_scope}

# Latest scope feedback
{scope_feedback}

# Task
Produce a structured scope draft for the research planner.

# Requirements
1. The draft must be concrete and reviewable by a human.
2. Capture goals, key questions, in-scope items, out-of-scope items, constraints, and source preferences.
3. Include 3-7 concrete `research_steps` that explain how the research will be carried out.
4. The `research_steps` must read like a reviewable step outline for the user, not like raw search queries.
5. If scope_feedback is present, rewrite the draft based on the previous draft and the feedback.
6. Do not generate final answers, exhaustive evidence, or low-level execution logs.

# Output
Return a JSON object:
```json
{{
  "research_goal": "Primary research goal",
  "research_steps": ["Step 1", "Step 2"],
  "core_questions": ["Question 1", "Question 2"],
  "in_scope": ["In-scope item 1"],
  "out_of_scope": ["Out-of-scope item 1"],
  "constraints": ["Constraint 1"],
  "source_preferences": ["Preferred source 1"],
  "deliverable_preferences": ["Preferred report style"],
  "assumptions": ["Assumption 1"]
}}
```
"""


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _default_research_steps(
    *,
    topic: str,
    research_goal: str,
    core_questions: list[str],
    in_scope: list[str],
    constraints: list[str],
    source_preferences: list[str],
    deliverable_preferences: list[str],
    scope_feedback: str,
) -> list[str]:
    focus_items = in_scope or core_questions
    focus_text = "; ".join(item for item in focus_items[:3] if item) or research_goal or topic
    question_text = "; ".join(item for item in core_questions[:3] if item)
    source_text = "、".join(item for item in source_preferences[:2] if item)
    constraint_text = "; ".join(item for item in constraints[:2] if item)
    deliverable_text = "、".join(item for item in deliverable_preferences[:2] if item)

    steps = [
        f"先确认本次调研的核心目标与覆盖范围, 重点聚焦: {focus_text}.",
    ]
    if question_text:
        steps.append(f"围绕这些关键问题收集最新信息与事实依据: {question_text}.")
    else:
        steps.append(f'围绕"{research_goal or topic}"拆解关键问题, 并补齐必要背景信息.')

    steps.append("对比不同来源中的数据, 观点和时间线, 识别主要趋势, 差异与潜在风险.")

    if source_text or constraint_text:
        parts: list[str] = []
        if source_text:
            parts.append(f"优先参考: {source_text}")
        if constraint_text:
            parts.append(f"同时遵守这些约束: {constraint_text}")
        steps.append("; ".join(parts) + ".")

    if scope_feedback:
        steps.append(f"在综合分析时, 特别落实这次修改要求: {scope_feedback}.")

    if deliverable_text:
        steps.append(f"最后整理成{deliverable_text}, 给出结构化结论与行动建议.")
    else:
        steps.append("最后输出结构化结论, 并补充面向决策或执行的建议.")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in steps:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped[:6]


def _extract_json_object(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        return {}
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if end > start:
            block = text[start + 3 : end].strip()
            if block.lower().startswith("json"):
                block = block[4:].strip()
            text = block
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        text = text[brace_start : brace_end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class DeepResearchScopeAgent:
    """Creates or rewrites the structured scope draft."""

    def __init__(self, llm: BaseChatModel, config: dict[str, Any] | None = None):
        self.llm = llm
        self.config = config or {}

    def create_scope(
        self,
        topic: str,
        *,
        intake_summary: dict[str, Any] | None = None,
        previous_scope: dict[str, Any] | None = None,
        scope_feedback: str = "",
    ) -> dict[str, Any]:
        prompt = ChatPromptTemplate.from_messages([("user", SCOPE_PROMPT)])
        msg = prompt.format_messages(
            topic=topic,
            intake_summary=json.dumps(intake_summary or {}, ensure_ascii=False, indent=2),
            previous_scope=json.dumps(previous_scope or {}, ensure_ascii=False, indent=2),
            scope_feedback=scope_feedback or "None",
        )
        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""
        return self._parse_response(
            content,
            topic=topic,
            intake_summary=intake_summary or {},
            previous_scope=previous_scope or {},
            scope_feedback=scope_feedback,
        )

    def _parse_response(
        self,
        content: str,
        *,
        topic: str,
        intake_summary: dict[str, Any],
        previous_scope: dict[str, Any],
        scope_feedback: str,
    ) -> dict[str, Any]:
        payload = _extract_json_object(content)
        if not payload:
            payload = {}

        research_goal = str(
            payload.get("research_goal")
            or intake_summary.get("research_goal")
            or previous_scope.get("research_goal")
            or topic
        ).strip() or topic
        background = str(intake_summary.get("background") or "").strip()
        constraints = _coerce_string_list(payload.get("constraints")) or _coerce_string_list(
            intake_summary.get("constraints")
        )
        source_preferences = _coerce_string_list(payload.get("source_preferences")) or _coerce_string_list(
            intake_summary.get("source_preferences")
        )
        out_of_scope = _coerce_string_list(payload.get("out_of_scope")) or _coerce_string_list(
            intake_summary.get("exclusions")
        )
        research_steps = _coerce_string_list(payload.get("research_steps"))
        core_questions = _coerce_string_list(payload.get("core_questions"))
        if not core_questions:
            core_questions = [
                research_goal,
                f"Key trade-offs and constraints for {topic}",
            ]
        in_scope = _coerce_string_list(payload.get("in_scope"))
        if not in_scope:
            in_scope = [research_goal]
            if background:
                in_scope.append(background)
        deliverable_preferences = _coerce_string_list(payload.get("deliverable_preferences"))
        assumptions = _coerce_string_list(payload.get("assumptions"))
        if not research_steps:
            research_steps = _default_research_steps(
                topic=topic,
                research_goal=research_goal,
                core_questions=core_questions,
                in_scope=in_scope,
                constraints=constraints,
                source_preferences=source_preferences,
                deliverable_preferences=deliverable_preferences,
                scope_feedback=scope_feedback,
            )
        if scope_feedback:
            assumptions.append(f"Revision requested: {scope_feedback}")

        return {
            "research_goal": research_goal,
            "research_steps": research_steps,
            "core_questions": core_questions,
            "in_scope": in_scope,
            "out_of_scope": out_of_scope,
            "constraints": constraints,
            "source_preferences": source_preferences,
            "deliverable_preferences": deliverable_preferences,
            "assumptions": assumptions,
        }


__all__ = ["DeepResearchScopeAgent"]
