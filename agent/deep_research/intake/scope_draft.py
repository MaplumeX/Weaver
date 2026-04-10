"""Scope-draft parsing and intake transforms for Deep Research."""

from __future__ import annotations

import copy
from typing import Any

from agent.deep_research.ids import _new_id
from agent.deep_research.schema import ScopeDraft, _now_iso


def coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def scope_draft_from_payload(payload: dict[str, Any] | None) -> ScopeDraft | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return ScopeDraft(
        id=str(payload.get("id") or _new_id("scope")),
        version=max(1, int(payload.get("version", 1) or 1)),
        topic=str(payload.get("topic") or ""),
        research_goal=str(payload.get("research_goal") or ""),
        research_steps=coerce_string_list(payload.get("research_steps")),
        core_questions=coerce_string_list(payload.get("core_questions")),
        in_scope=coerce_string_list(payload.get("in_scope")),
        out_of_scope=coerce_string_list(payload.get("out_of_scope")),
        constraints=coerce_string_list(payload.get("constraints")),
        source_preferences=coerce_string_list(payload.get("source_preferences")),
        deliverable_preferences=coerce_string_list(payload.get("deliverable_preferences")),
        assumptions=coerce_string_list(payload.get("assumptions")),
        clarification_context=copy.deepcopy(payload.get("clarification_context") or {}),
        feedback=str(payload.get("feedback") or ""),
        status=str(payload.get("status") or "awaiting_review"),
        created_by=str(payload.get("created_by") or "scope"),
        created_at=str(payload.get("created_at") or _now_iso()),
        updated_at=str(payload.get("updated_at") or _now_iso()),
    )


def format_scope_draft_markdown(payload: dict[str, Any] | ScopeDraft | None) -> str:
    draft = payload if isinstance(payload, ScopeDraft) else scope_draft_from_payload(payload)
    if not draft:
        return ""

    research_steps = list(draft.research_steps or [])
    if not research_steps:
        focus_items = draft.in_scope or draft.core_questions or [draft.research_goal or draft.topic]
        focus_text = "; ".join(item for item in focus_items[:3] if item) or (draft.research_goal or draft.topic)
        question_text = "; ".join(item for item in draft.core_questions[:3] if item)
        research_steps = [
            f"先确认这次调研的目标与覆盖范围, 重点聚焦: {focus_text}.",
            (
                f"围绕这些关键问题收集最新信息与事实依据: {question_text}."
                if question_text
                else f'围绕"{draft.research_goal or draft.topic}"拆解关键问题并补齐必要背景信息.'
            ),
            "对比不同来源中的数据, 观点和时间线, 识别主要趋势, 差异与潜在风险.",
            "最后整合证据, 输出结构化结论与可执行建议.",
        ]

    sections = [
        f"# 研究计划草案 v{draft.version}",
        "",
        "如果按这个方向开始调研, 我会大致这样推进:",
        "",
    ]
    sections.extend(f"{index}. {item}" for index, item in enumerate(research_steps, 1))
    if draft.feedback:
        sections.extend(
            [
                "",
                "已吸收的最新修改要求:",
                f"> {draft.feedback}",
            ]
        )
    return "\n".join(sections)


def extract_interrupt_text(
    payload: Any,
    *,
    keys: tuple[str, ...],
) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_clarify_transcript(
    question_history: list[str] | None,
    answer_history: list[str] | None,
) -> list[dict[str, str]]:
    questions = [str(item or "").strip() for item in (question_history or [])]
    answers = [str(item or "").strip() for item in (answer_history or [])]
    transcript: list[dict[str, str]] = []
    for index in range(max(len(questions), len(answers))):
        question = questions[index] if index < len(questions) else ""
        answer = answers[index] if index < len(answers) else ""
        if not question and not answer:
            continue
        transcript.append({"question": question, "answer": answer})
    return transcript


def build_scope_draft(
    *,
    topic: str,
    version: int,
    draft_payload: dict[str, Any],
    clarification_context: dict[str, Any],
    feedback: str,
    agent_id: str,
    previous: dict[str, Any] | None = None,
) -> ScopeDraft:
    previous_draft = scope_draft_from_payload(previous)
    return ScopeDraft(
        id=previous_draft.id if previous_draft else _new_id("scope"),
        version=max(1, int(version or 1)),
        topic=topic,
        research_goal=str(
            draft_payload.get("research_goal")
            or (previous_draft.research_goal if previous_draft else "")
            or topic
        ).strip()
        or topic,
        research_steps=coerce_string_list(draft_payload.get("research_steps"))
        or (previous_draft.research_steps if previous_draft else []),
        core_questions=coerce_string_list(draft_payload.get("core_questions"))
        or (previous_draft.core_questions if previous_draft else []),
        in_scope=coerce_string_list(draft_payload.get("in_scope"))
        or (previous_draft.in_scope if previous_draft else []),
        out_of_scope=coerce_string_list(draft_payload.get("out_of_scope"))
        or (previous_draft.out_of_scope if previous_draft else []),
        constraints=coerce_string_list(draft_payload.get("constraints"))
        or coerce_string_list(
            (clarification_context.get("resolved_slots") or {}).get("constraints")
            if isinstance(clarification_context.get("resolved_slots"), dict)
            else []
        )
        or (previous_draft.constraints if previous_draft else []),
        source_preferences=coerce_string_list(draft_payload.get("source_preferences"))
        or coerce_string_list(
            (clarification_context.get("resolved_slots") or {}).get("source_preferences")
            if isinstance(clarification_context.get("resolved_slots"), dict)
            else []
        )
        or (previous_draft.source_preferences if previous_draft else []),
        deliverable_preferences=coerce_string_list(draft_payload.get("deliverable_preferences"))
        or (previous_draft.deliverable_preferences if previous_draft else []),
        assumptions=coerce_string_list(draft_payload.get("assumptions"))
        or (previous_draft.assumptions if previous_draft else []),
        clarification_context=copy.deepcopy(clarification_context),
        feedback=feedback,
        status="awaiting_review",
        created_by=agent_id,
    )


__all__ = [
    "build_clarify_transcript",
    "build_scope_draft",
    "coerce_string_list",
    "extract_interrupt_text",
    "format_scope_draft_markdown",
    "scope_draft_from_payload",
]
