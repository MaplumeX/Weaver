"""Helper types and transforms for the multi-agent Deep Research graph."""

from __future__ import annotations

import copy
import re
from typing import Annotated, Any, TypedDict

import agent.runtime.deep.support.runtime_support as support
from agent.runtime.deep.schema import (
    AgentRunRecord,
    ControlPlaneHandoff,
    ResearchTask,
    ScopeDraft,
    _now_iso,
    is_control_plane_agent,
    validate_control_plane_agent,
)
from agent.runtime.deep.services.knowledge_gap import GapAnalysisResult

_COVERAGE_STOPWORDS = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "from",
    "into",
    "were",
    "was",
    "are",
    "for",
    "has",
    "have",
    "had",
    "will",
    "about",
    "explain",
    "describe",
    "summarize",
    "analyze",
    "说明",
    "解释",
    "总结",
    "分析",
    "介绍",
}


def _coverage_tokens(text: str) -> list[str]:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return []

    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", normalized):
        if len(token) <= 1 or token in _COVERAGE_STOPWORDS:
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)

    for chunk in re.findall(r"[\u4e00-\u9fff]+", normalized):
        if len(chunk) == 1:
            if chunk not in _COVERAGE_STOPWORDS and chunk not in seen:
                seen.add(chunk)
                tokens.append(chunk)
            continue
        for index in range(len(chunk) - 1):
            token = chunk[index:index + 2]
            if token in _COVERAGE_STOPWORDS or token in seen:
                continue
            seen.add(token)
            tokens.append(token)

    return tokens


def reduce_worker_payloads(
    existing: list[dict[str, Any]] | None,
    new: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    current = list(existing or [])
    if not new:
        return current

    reset = any(isinstance(item, dict) and item.get("__reset__") for item in new)
    payloads = [
        item
        for item in new
        if isinstance(item, dict) and not item.get("__reset__")
    ]
    if reset:
        return payloads
    return current + payloads


class MultiAgentGraphState(TypedDict, total=False):
    shared_state: dict[str, Any]
    topic: str
    graph_run_id: str
    graph_attempt: int
    root_branch_id: str
    task_queue: dict[str, Any]
    artifact_store: dict[str, Any]
    runtime_state: dict[str, Any]
    agent_runs: list[dict[str, Any]]
    current_iteration: int
    planning_mode: str
    next_step: str
    latest_gap_result: dict[str, Any]
    latest_decision: dict[str, Any]
    latest_verification_summary: dict[str, Any]
    pending_worker_tasks: list[dict[str, Any]]
    worker_task: dict[str, Any]
    worker_results: Annotated[list[dict[str, Any]], reduce_worker_payloads]
    final_result: dict[str, Any]


def restore_agent_runs(items: list[dict[str, Any]]) -> list[AgentRunRecord]:
    restored: list[AgentRunRecord] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        restored.append(AgentRunRecord(**item))
    return restored


def gap_result_from_payload(payload: dict[str, Any] | None) -> GapAnalysisResult | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return GapAnalysisResult.from_dict(payload)


def derive_role_counters(agent_runs: list[AgentRunRecord]) -> dict[str, int]:
    counters: dict[str, int] = {}
    for run in agent_runs:
        agent_id = str(run.agent_id or "")
        if "-" not in agent_id:
            continue
        role, _, suffix = agent_id.rpartition("-")
        if not role:
            role = str(run.role)
        try:
            counters[role] = max(counters.get(role, 0), int(suffix))
        except ValueError:
            continue
    return counters


def coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def normalize_control_plane_agent(value: Any, *, default: str = "clarify") -> str:
    normalized = str(value or "").strip()
    if is_control_plane_agent(normalized):
        return normalized
    return validate_control_plane_agent(default)


def control_plane_handoff_from_payload(payload: dict[str, Any] | None) -> ControlPlaneHandoff | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return ControlPlaneHandoff(
        id=str(payload.get("id") or support._new_id("handoff")),
        from_agent=normalize_control_plane_agent(payload.get("from_agent"), default="clarify"),
        to_agent=normalize_control_plane_agent(payload.get("to_agent"), default="clarify"),
        reason=str(payload.get("reason") or "").strip(),
        context_refs=coerce_string_list(payload.get("context_refs")),
        scope_snapshot=copy.deepcopy(payload.get("scope_snapshot") or {}),
        review_state=str(payload.get("review_state") or ""),
        created_at=str(payload.get("created_at") or _now_iso()),
        created_by=str(payload.get("created_by") or payload.get("from_agent") or ""),
        metadata=copy.deepcopy(payload.get("metadata") or {}),
    )


def restore_handoff_history(items: list[dict[str, Any]] | None) -> list[ControlPlaneHandoff]:
    restored: list[ControlPlaneHandoff] = []
    for item in items or []:
        handoff = control_plane_handoff_from_payload(item if isinstance(item, dict) else None)
        if handoff is not None:
            restored.append(handoff)
    return restored


def split_findings(summary: str) -> list[str]:
    text = str(summary or "").strip()
    if not text:
        return []
    parts = [item.strip(" -•\t") for item in text.replace("\r", "\n").split("\n") if item.strip()]
    findings = [part for part in parts if len(part) >= 12]
    if findings:
        return findings[:6]
    return [text[:300]]


def derive_branch_queries(task: ResearchTask, limit: int = 3) -> list[str]:
    candidates = list(task.query_hints or [])
    if not candidates and task.query:
        candidates.append(task.query)
    if not candidates and task.objective:
        candidates.append(task.objective)
    if not candidates and task.title:
        candidates.append(task.title)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def scope_draft_from_payload(payload: dict[str, Any] | None) -> ScopeDraft | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return ScopeDraft(
        id=str(payload.get("id") or support._new_id("scope")),
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


def scope_version(payload: dict[str, Any] | None) -> int:
    draft = scope_draft_from_payload(payload)
    return int(draft.version) if draft else 0


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
        id=previous_draft.id if previous_draft else support._new_id("scope"),
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
    "MultiAgentGraphState",
    "build_clarify_transcript",
    "build_scope_draft",
    "coerce_string_list",
    "control_plane_handoff_from_payload",
    "derive_branch_queries",
    "derive_role_counters",
    "extract_interrupt_text",
    "format_scope_draft_markdown",
    "gap_result_from_payload",
    "normalize_control_plane_agent",
    "reduce_worker_payloads",
    "restore_agent_runs",
    "restore_handoff_history",
    "scope_draft_from_payload",
    "scope_version",
    "split_findings",
]
