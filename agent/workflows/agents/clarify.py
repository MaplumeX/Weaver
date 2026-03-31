"""
Deep Research clarify agent.

Collects missing intake details before the scope draft is generated.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


CLARIFY_PROMPT = """
# Role
You are the Deep Research intake clarifier.

# Task
Decide whether the current request has enough information to draft a research scope.

# Original topic
{topic}

# Clarification transcript so far
{clarify_history}

# Requirements
1. If key details are missing, ask one focused follow-up question.
2. If the request is already specific enough, do not ask another question.
3. Always produce a normalized intake summary for the scope agent.
4. Keep missing_information concise and actionable.
5. Ground the intake summary in the full clarification transcript, not just the latest answer.

# Output
Return a JSON object:
```json
{{
  "needs_clarification": true,
  "question": "One focused question for the user",
  "missing_information": ["goal", "time_range"],
  "intake_summary": {{
    "research_goal": "What the user wants to learn",
    "background": "Relevant context already known",
    "constraints": ["Any hard constraints"],
    "time_range": "Time period if specified",
    "source_preferences": ["Preferred source types"],
    "exclusions": ["Out-of-scope items"]
  }}
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


def _coerce_history_answers(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    answers: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        answer = str(item.get("answer") or "").strip()
        if answer:
            answers.append(answer)
    return answers


def _format_clarify_history(value: Any, fallback_answers: list[str] | None = None) -> str:
    if isinstance(value, list):
        lines: list[str] = []
        for index, item in enumerate(value, 1):
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            answer = str(item.get("answer") or "").strip()
            if not question and not answer:
                continue
            lines.append(f"{index}. Q: {question or '(missing question)'}")
            lines.append(f"   A: {answer or '(missing answer)'}")
        if lines:
            return "\n".join(lines)

    answers = [item for item in (fallback_answers or []) if str(item or "").strip()]
    if answers:
        return "\n".join(f"- {item}" for item in answers)
    return "None"


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


class DeepResearchClarifyAgent:
    """Normalizes topic intake and decides whether another user answer is required."""

    def __init__(self, llm: BaseChatModel, config: dict[str, Any] | None = None):
        self.llm = llm
        self.config = config or {}

    def assess_intake(
        self,
        topic: str,
        *,
        clarify_answers: list[str] | None = None,
        clarify_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        normalized_answers = [
            item
            for item in (clarify_answers or _coerce_history_answers(clarify_history))
            if str(item or "").strip()
        ]
        prompt = ChatPromptTemplate.from_messages([("user", CLARIFY_PROMPT)])
        msg = prompt.format_messages(
            topic=topic,
            clarify_history=_format_clarify_history(clarify_history, normalized_answers),
        )
        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""
        return self._parse_response(content, topic=topic, clarify_answers=normalized_answers)

    def _parse_response(
        self,
        content: str,
        *,
        topic: str,
        clarify_answers: list[str],
    ) -> dict[str, Any]:
        payload = _extract_json_object(content)
        intake_summary = payload.get("intake_summary") if isinstance(payload.get("intake_summary"), dict) else {}

        research_goal = str(intake_summary.get("research_goal") or topic).strip() or topic
        summary = {
            "research_goal": research_goal,
            "background": str(intake_summary.get("background") or "").strip(),
            "constraints": _coerce_string_list(intake_summary.get("constraints")),
            "time_range": str(intake_summary.get("time_range") or "").strip(),
            "source_preferences": _coerce_string_list(intake_summary.get("source_preferences")),
            "exclusions": _coerce_string_list(intake_summary.get("exclusions")),
        }

        missing_information = _coerce_string_list(payload.get("missing_information"))
        question = str(payload.get("question") or "").strip()
        needs_clarification = bool(payload.get("needs_clarification"))

        if not summary["constraints"] and clarify_answers:
            summary["constraints"] = [item for item in clarify_answers if item]

        if not summary["source_preferences"] and clarify_answers:
            for answer in clarify_answers:
                lowered = answer.lower()
                if "source" in lowered or "来源" in answer:
                    summary["source_preferences"].append(answer)

        if not summary["time_range"] and clarify_answers:
            for answer in clarify_answers:
                if any(token in answer for token in ("202", "19", "20", "季度", "年", "月", "周")):
                    summary["time_range"] = answer
                    break

        if not question and needs_clarification:
            question = "Please clarify your primary goal, time range, preferred sources, and exclusions for this research."

        if not missing_information and needs_clarification:
            missing_information = ["research_goal", "time_range", "source_preferences", "exclusions"]

        if not payload:
            needs_clarification = len(topic.split()) <= 5 and not clarify_answers
            if needs_clarification:
                question = "Please clarify your primary goal, time range, preferred sources, and exclusions for this research."
                missing_information = ["research_goal", "time_range", "source_preferences", "exclusions"]

        if clarify_answers and needs_clarification and not question:
            needs_clarification = False

        return {
            "needs_clarification": needs_clarification,
            "question": question,
            "missing_information": missing_information,
            "intake_summary": summary,
        }


__all__ = ["DeepResearchClarifyAgent"]
