"""Synthesis helpers for branch research."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from agent.deep_research.branch_research.shared import (
    clamp_text as _clamp_text,
)
from agent.deep_research.branch_research.shared import (
    dedupe_strings as _dedupe_strings,
)
from agent.deep_research.schema import ResearchTask
from agent.prompting.runtime_templates import DEEP_RESEARCHER_EVIDENCE_SYNTHESIS_PROMPT

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


def synthesize(
    llm: Any,
    config: dict[str, Any],
    task: ResearchTask,
    *,
    topic: str,
    passages: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    existing_summary: str,
) -> dict[str, Any]:
    evidence_lines: list[str] = []
    for index, item in enumerate(passages[:8], 1):
        title = str(item.get("source_title") or item.get("page_title") or item.get("url") or "").strip()
        evidence_lines.append(
            "\n".join(
                [
                    f"[{index}] 标题: {title}",
                    f"URL: {item.get('url', '')}",
                    f"Heading: {' > '.join(item.get('heading_path') or []) or 'N/A'}",
                    f"Authoritative: {bool(item.get('authoritative', False))}",
                    f"Quote: {_clamp_text(item.get('quote') or item.get('text') or '', 280)}",
                ]
            )
        )

    if not evidence_lines:
        for index, item in enumerate(documents[:4], 1):
            evidence_lines.append(
                "\n".join(
                    [
                        f"[{index}] 标题: {item.get('title', '')}",
                        f"URL: {item.get('url', '')}",
                        f"Authoritative: {bool(item.get('authoritative', False))}",
                        f"Excerpt: {_clamp_text(item.get('excerpt') or item.get('content') or '', 280)}",
                    ]
                )
            )

    prompt = ChatPromptTemplate.from_messages([("user", DEEP_RESEARCHER_EVIDENCE_SYNTHESIS_PROMPT)])
    messages = prompt.format_messages(
        topic=topic,
        branch_title=task.title or task.objective or task.goal,
        branch_objective=task.objective or task.goal or task.query,
        acceptance_criteria="\n".join(f"- {item}" for item in task.acceptance_criteria) or "- 无显式验收标准",
        existing_summary=_clamp_text(existing_summary, 1_200) or "暂无",
        evidence="\n\n".join(evidence_lines),
    )
    response = llm.invoke(messages, config=config)
    payload = parse_synthesis_payload(getattr(response, "content", "") or "")

    summary = str(payload.get("summary") or "").strip()
    key_findings = _dedupe_strings(payload.get("key_findings") or [], limit=5)
    open_questions = _dedupe_strings(payload.get("open_questions") or [], limit=3)
    confidence_note = str(payload.get("confidence_note") or "").strip()

    if not summary:
        summary = fallback_summary(task, passages, documents)
    if not key_findings:
        key_findings = fallback_findings(passages, documents)

    return {
        "summary": summary,
        "key_findings": key_findings,
        "open_questions": open_questions,
        "confidence_note": confidence_note,
    }


def parse_synthesis_payload(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        return {}
    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("[deep-research-researcher] failed to parse synthesis payload")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def fallback_summary(
    task: ResearchTask,
    passages: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> str:
    if passages:
        top = passages[0]
        return (
            f"{task.objective or task.goal}: 基于 {top.get('source_title') or top.get('url')} 的证据, "
            f"{_clamp_text(top.get('quote') or top.get('text') or '', 160)}"
        )
    if documents:
        top = documents[0]
        return (
            f"{task.objective or task.goal}: 已收集到 {top.get('title') or top.get('url')} 的相关材料, "
            f"但结构化综合结果生成失败。"
        )
    return f"{task.objective or task.goal}: 未形成有效证据摘要。"


def fallback_findings(
    passages: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> list[str]:
    findings: list[str] = []
    for item in passages[:3]:
        text = _clamp_text(item.get("quote") or item.get("text") or "", 120)
        if text:
            findings.append(text)
    if findings:
        return _dedupe_strings(findings, limit=3)
    for item in documents[:2]:
        text = _clamp_text(item.get("excerpt") or item.get("content") or "", 120)
        if text:
            findings.append(text)
    return _dedupe_strings(findings, limit=3)
