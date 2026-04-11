"""Planning helpers for Deep Research engine."""

from __future__ import annotations

from typing import Any

from agent.deep_research.engine.section_logic import _section_title
from agent.deep_research.engine.text_analysis import _dedupe_texts
from agent.deep_research.ids import _new_id
from agent.deep_research.schema import ResearchTask


def outline_sections(outline: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [
        item
        for item in list(outline.get("sections") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    return sorted(
        sections,
        key=lambda item: (
            int(item.get("section_order", 0) or 0),
            str(item.get("id") or ""),
        ),
    )


def build_outline_tasks(
    *,
    outline: dict[str, Any],
    scope: dict[str, Any],
    topic: str,
    domain_config: dict[str, Any] | None = None,
) -> list[ResearchTask]:
    tasks: list[ResearchTask] = []
    for index, section in enumerate(outline_sections(outline), 1):
        core_question = str(section.get("core_question") or section.get("objective") or "").strip()
        title = _section_title(section)
        query_hints = _dedupe_texts([
            core_question,
            f"{topic} {core_question}".strip(),
            title,
        ])
        query = query_hints[0] if query_hints else core_question or title
        task = ResearchTask(
            id=_new_id("task"),
            goal=core_question or title,
            query=query,
            priority=max(1, int(section.get("section_order", index) or index)),
            objective=str(section.get("objective") or core_question or title).strip(),
            task_kind="section_research",
            acceptance_criteria=_dedupe_texts(section.get("acceptance_checks") or [core_question]),
            allowed_tools=["search", "read", "extract", "synthesize"],
            source_preferences=_dedupe_texts(
                section.get("source_preferences") or scope.get("source_preferences") or []
            ),
            authority_preferences=_dedupe_texts(
                section.get("authority_preferences") or scope.get("source_preferences") or []
            ),
            coverage_targets=_dedupe_texts(
                section.get("coverage_targets") or section.get("acceptance_checks") or [core_question]
            ),
            language_hints=_dedupe_texts((domain_config or {}).get("language_hints") or []),
            deliverable_constraints=_dedupe_texts(
                section.get("deliverable_constraints")
                or scope.get("deliverable_constraints")
                or scope.get("deliverable_preferences")
                or []
            ),
            source_requirements=_dedupe_texts(section.get("source_requirements") or []),
            freshness_policy=str(section.get("freshness_policy") or "default_advisory").strip(),
            time_boundary=str(section.get("time_boundary") or scope.get("time_boundary") or "").strip(),
            input_artifact_ids=[
                str(item).strip()
                for item in [
                    str(scope.get("id") or "").strip(),
                    str(outline.get("id") or "").strip(),
                ]
                if str(item).strip()
            ],
            output_artifact_types=["section_draft", "evidence_bundle"],
            query_hints=query_hints or [core_question or title],
            title=title,
            aspect="section",
            section_id=str(section.get("id") or "").strip(),
        )
        tasks.append(task)
    return tasks


def section_map(outline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or "").strip(): item
        for item in outline_sections(outline)
        if str(item.get("id") or "").strip()
    }


def build_revision_task(
    *,
    section: dict[str, Any],
    draft: dict[str, Any],
    review: dict[str, Any],
    scope: dict[str, Any],
    revision_count: int,
) -> ResearchTask:
    del revision_count
    core_question = str(section.get("core_question") or section.get("objective") or draft.get("objective") or "").strip()
    return ResearchTask(
        id=_new_id("task"),
        goal=core_question,
        query=str(draft.get("summary") or core_question).strip() or core_question,
        priority=max(1, int(section.get("section_order", 1) or 1)),
        objective=str(section.get("objective") or core_question).strip(),
        task_kind="section_revision",
        acceptance_criteria=_dedupe_texts(section.get("acceptance_checks") or [core_question]),
        allowed_tools=["synthesize"],
        input_artifact_ids=[
            str(item).strip()
            for item in [
                str(scope.get("id") or "").strip(),
                str(section.get("id") or "").strip(),
                str(draft.get("id") or "").strip(),
                str(review.get("id") or "").strip(),
            ]
            if str(item).strip()
        ],
        output_artifact_types=["section_draft"],
        query_hints=[core_question],
        title=f"修订章节: {_section_title(section)}",
        aspect="section_revision",
        section_id=str(section.get("id") or "").strip(),
        parent_task_id=str(draft.get("task_id") or "") or None,
        revision_kind="reviewer_revision",
        target_issue_ids=[
            str(item.get("id") or "").strip()
            for item in review.get("advisory_issues", []) or []
            if str(item.get("id") or "").strip()
        ],
    )


def build_research_retry_task(
    *,
    section: dict[str, Any],
    draft: dict[str, Any],
    review: dict[str, Any],
    scope: dict[str, Any],
) -> ResearchTask:
    follow_up_queries = _dedupe_texts(review.get("follow_up_queries") or [section.get("core_question")])
    query = follow_up_queries[0] if follow_up_queries else str(section.get("core_question") or "").strip()
    return ResearchTask(
        id=_new_id("task"),
        goal=str(section.get("core_question") or section.get("objective") or "").strip(),
        query=query,
        priority=max(1, int(section.get("section_order", 1) or 1)),
        objective=str(section.get("objective") or section.get("core_question") or "").strip(),
        task_kind="section_research",
        acceptance_criteria=_dedupe_texts(section.get("acceptance_checks") or [section.get("core_question")]),
        allowed_tools=["search", "read", "extract", "synthesize"],
        input_artifact_ids=[
            str(item).strip()
            for item in [
                str(scope.get("id") or "").strip(),
                str(section.get("id") or "").strip(),
                str(draft.get("id") or "").strip(),
                str(review.get("id") or "").strip(),
            ]
            if str(item).strip()
        ],
        output_artifact_types=["section_draft", "evidence_bundle"],
        query_hints=follow_up_queries or [query],
        title=f"补充研究: {_section_title(section)}",
        aspect="section_retry",
        section_id=str(section.get("id") or "").strip(),
        parent_task_id=str(draft.get("task_id") or "") or None,
        target_issue_ids=[
            str(item.get("id") or "").strip()
            for item in review.get("blocking_issues", []) or []
            if str(item.get("id") or "").strip()
        ],
    )
