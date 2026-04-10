"""
Deep Research clarify agent.

Acts as a clarification gate before scope drafting.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agent.prompting.runtime_templates import DEEP_CLARIFY_PROMPT as CLARIFY_PROMPT

logger = logging.getLogger(__name__)

_ALLOWED_SLOTS = (
    "goal",
    "time_range",
    "source_preferences",
    "exclusions",
    "constraints",
    "deliverable_preferences",
)
_QUESTION_DEFAULTS = {
    "goal": "What question should this research ultimately answer for you?",
    "time_range": "What time range should the research cover?",
    "source_preferences": "Should this research prioritize any specific source types, such as official filings or academic papers?",
    "exclusions": "Is there anything this research should explicitly leave out?",
    "constraints": "Are there any hard constraints the research should follow?",
    "deliverable_preferences": "Do you want the final research delivered in a specific format?",
}
_TIME_RANGE_HINTS = ("202", "19", "20", "quarter", "year", "month", "week", "季度", "年", "月", "周")
_EXCLUSION_HINTS = ("exclude", "excluding", "out of scope", "不包括", "排除", "不要", "无需", "忽略")
_CONSTRAINT_HINTS = ("must", "only", "at most", "no more than", "必须", "只能", "仅限", "限制")
_DELIVERABLE_HINTS = ("report", "memo", "brief", "table", "slides", "presentation", "报告", "简报", "表格", "PPT")


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


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


def _normalize_slot(value: Any) -> str:
    slot = str(value or "").strip().lower()
    return slot if slot in _ALLOWED_SLOTS else "none"


def _coerce_slot_list(value: Any) -> list[str]:
    slots: list[str] = []
    seen: set[str] = set()
    for item in value if isinstance(value, list) else []:
        slot = _normalize_slot(item)
        if slot == "none" or slot in seen:
            continue
        seen.add(slot)
        slots.append(slot)
    return slots


def _infer_slot_from_text(text: str) -> str:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return "none"
    if "time range" in normalized or "cover" in normalized or any(token in normalized for token in ("季度", "时间", "年份", "时间范围")):
        return "time_range"
    if "source" in normalized or "来源" in normalized:
        return "source_preferences"
    if any(marker in normalized for marker in ("exclude", "out of scope", "不包括", "排除", "不要", "忽略")):
        return "exclusions"
    if any(marker in normalized for marker in ("constraint", "限制", "must", "only")):
        return "constraints"
    if any(marker in normalized for marker in ("format", "deliverable", "报告", "简报", "表格", "slides")):
        return "deliverable_preferences"
    if "ultimate" in normalized or "goal" in normalized or "question" in normalized or "learn" in normalized or "问题" in normalized or "目标" in normalized:
        return "goal"
    return "none"


def _empty_resolved_slots() -> dict[str, Any]:
    return {
        "goal": "",
        "time_range": "",
        "source_preferences": [],
        "constraints": [],
        "exclusions": [],
        "deliverable_preferences": [],
    }


def _append_unique(items: list[str], candidate: str) -> None:
    text = str(candidate or "").strip()
    if text and text not in items:
        items.append(text)

def _normalize_resolved_slots(
    payload: dict[str, Any],
    *,
    clarify_answers: list[str],
    asked_slots: list[str],
) -> dict[str, Any]:
    source = payload.get("resolved_slots") if isinstance(payload.get("resolved_slots"), dict) else {}

    resolved = _empty_resolved_slots()
    resolved["goal"] = str(source.get("goal") or "").strip()
    resolved["time_range"] = str(source.get("time_range") or "").strip()
    resolved["source_preferences"] = _coerce_string_list(source.get("source_preferences"))
    resolved["constraints"] = _coerce_string_list(source.get("constraints"))
    resolved["exclusions"] = _coerce_string_list(source.get("exclusions"))
    resolved["deliverable_preferences"] = _coerce_string_list(source.get("deliverable_preferences"))

    last_answer = str(clarify_answers[-1] or "").strip() if clarify_answers else ""
    last_asked_slot = asked_slots[-1] if asked_slots else "none"
    if last_answer and last_asked_slot != "none":
        if last_asked_slot in {"goal", "time_range"} and not resolved[last_asked_slot]:
            resolved[last_asked_slot] = last_answer
        elif (
            last_asked_slot in {"source_preferences", "constraints", "exclusions", "deliverable_preferences"}
            and not resolved[last_asked_slot]
        ):
            resolved[last_asked_slot] = [last_answer]

    if not resolved["time_range"]:
        for answer in clarify_answers:
            if any(token in answer for token in _TIME_RANGE_HINTS):
                resolved["time_range"] = answer
                break

    if not resolved["source_preferences"]:
        for answer in clarify_answers:
            lowered = answer.lower()
            if "source" in lowered or "sources" in lowered or "来源" in answer:
                _append_unique(resolved["source_preferences"], answer)

    if not resolved["exclusions"]:
        for answer in clarify_answers:
            lowered = answer.lower()
            if any(marker in lowered for marker in _EXCLUSION_HINTS[:3]) or any(
                marker in answer for marker in _EXCLUSION_HINTS[3:]
            ):
                _append_unique(resolved["exclusions"], answer)

    if not resolved["constraints"]:
        for answer in clarify_answers:
            lowered = answer.lower()
            if any(marker in lowered for marker in _CONSTRAINT_HINTS[:4]) or any(
                marker in answer for marker in _CONSTRAINT_HINTS[4:]
            ):
                _append_unique(resolved["constraints"], answer)

    if not resolved["deliverable_preferences"]:
        for answer in clarify_answers:
            lowered = answer.lower()
            if any(marker in lowered for marker in _DELIVERABLE_HINTS[:6]) or any(
                marker in answer for marker in _DELIVERABLE_HINTS[6:]
            ):
                _append_unique(resolved["deliverable_preferences"], answer)

    return resolved


def _default_status(topic: str, clarify_answers: list[str]) -> str:
    if clarify_answers:
        return "ready_for_scope"
    return "needs_user_input" if len(topic.split()) <= 5 else "ready_for_scope"


def _default_blocking_slot(topic: str, clarify_answers: list[str]) -> str:
    if clarify_answers:
        return "none"
    return "goal" if len(topic.split()) <= 5 else "none"


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
            str(item or "").strip()
            for item in (clarify_answers or [])
            if str(item or "").strip()
        ]
        normalized_history = [
            {
                "question": str(item.get("question") or "").strip(),
                "answer": str(item.get("answer") or "").strip(),
            }
            for item in (clarify_history or [])
            if isinstance(item, dict)
        ]
        prompt = ChatPromptTemplate.from_messages([("user", CLARIFY_PROMPT)])
        msg = prompt.format_messages(
            topic=topic,
            clarify_history=_format_clarify_history(normalized_history, normalized_answers),
        )
        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""
        return self._parse_response(
            content,
            topic=topic,
            clarify_answers=normalized_answers,
            clarify_history=normalized_history,
        )

    def _parse_response(
        self,
        content: str,
        *,
        topic: str,
        clarify_answers: list[str],
        clarify_history: list[dict[str, str]],
    ) -> dict[str, Any]:
        payload = _extract_json_object(content)

        inferred_asked_slots = [
            slot
            for slot in (
                _infer_slot_from_text(item.get("question", ""))
                for item in clarify_history
            )
            if slot != "none"
        ]
        asked_slots = _coerce_slot_list(payload.get("asked_slots")) or list(inferred_asked_slots)

        status = str(payload.get("status") or "").strip().lower()
        if status not in {"needs_user_input", "ready_for_scope"}:
            status = _default_status(topic, clarify_answers)

        unresolved_slots = _coerce_slot_list(payload.get("unresolved_slots"))
        blocking_slot = _normalize_slot(payload.get("blocking_slot"))
        if blocking_slot == "none" and unresolved_slots:
            blocking_slot = unresolved_slots[0]
        if blocking_slot == "none" and status == "needs_user_input":
            blocking_slot = _default_blocking_slot(topic, clarify_answers)
        if blocking_slot != "none" and blocking_slot not in unresolved_slots:
            unresolved_slots.insert(0, blocking_slot)
        if status == "needs_user_input" and blocking_slot != "none" and blocking_slot not in asked_slots:
            asked_slots.append(blocking_slot)

        resolved_slots = _normalize_resolved_slots(
            payload,
            clarify_answers=clarify_answers,
            asked_slots=asked_slots,
        )

        follow_up_question = str(payload.get("follow_up_question") or "").strip()
        if status == "needs_user_input" and not follow_up_question:
            follow_up_question = _QUESTION_DEFAULTS.get(
                blocking_slot,
                "What is the most important clarification this research should lock down before proceeding?",
            )
        if status == "ready_for_scope":
            follow_up_question = ""
            blocking_slot = "none"

        return {
            "status": status,
            "follow_up_question": follow_up_question,
            "blocking_slot": blocking_slot,
            "resolved_slots": resolved_slots,
            "unresolved_slots": unresolved_slots,
            "asked_slots": asked_slots,
        }


__all__ = ["DeepResearchClarifyAgent"]
