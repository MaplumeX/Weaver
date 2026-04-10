"""Claim-unit helpers for branch research."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from agent.deep_research.branch_research.shared import (
    clamp_text as _clamp_text,
)
from agent.deep_research.branch_research.shared import (
    dedupe_strings as _dedupe_strings,
)
from agent.deep_research.branch_research.shared import (
    tokenize as _tokenize,
)
from agent.deep_research.branch_research.synthesis import parse_synthesis_payload
from agent.deep_research.schema import ClaimUnit
from agent.prompting.runtime_templates import DEEP_RESEARCHER_CLAIM_GROUNDING_PROMPT


def build_claim_units(
    llm: Any,
    config: dict[str, Any],
    *,
    summary: str,
    key_findings: list[str],
    passages: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grounded_claims = _build_claim_units_with_llm(
        llm,
        config,
        summary=summary,
        key_findings=key_findings,
        passages=passages,
    )
    if grounded_claims:
        finalized = _finalize_claim_units(grounded_claims, passages, sources)
        if finalized:
            return finalized

    claims: list[tuple[str, str]] = []
    summary_text = str(summary or "").strip()
    if summary_text:
        claims.append((summary_text, "primary"))
    for index, finding in enumerate(_dedupe_strings(key_findings or [], limit=4), 1):
        importance = "primary" if index <= 2 else "secondary"
        claims.append((finding, importance))

    source_urls = [
        str(item.get("url") or "").strip()
        for item in sources or []
        if str(item.get("url") or "").strip()
    ]
    built: list[dict[str, Any]] = []
    for index, (claim_text, importance) in enumerate(claims, 1):
        claim_tokens = _tokenize(claim_text)
        matched_passages: list[dict[str, Any]] = []
        for passage in passages or []:
            passage_text = str(passage.get("text") or passage.get("quote") or "").strip()
            if not passage_text:
                continue
            overlap = len(claim_tokens & _tokenize(passage_text))
            if overlap <= 0:
                continue
            matched_passages.append(
                {
                    "overlap": overlap,
                    "id": str(passage.get("id") or "").strip(),
                    "url": str(passage.get("url") or "").strip(),
                }
            )
        matched_passages.sort(key=lambda item: (-int(item["overlap"]), item["id"]))
        evidence_passage_ids = [
            str(item["id"]).strip()
            for item in matched_passages[:2]
            if str(item["id"]).strip()
        ]
        evidence_urls = list(
            dict.fromkeys(
                [
                    str(item["url"]).strip()
                    for item in matched_passages[:2]
                    if str(item["url"]).strip()
                ]
                or source_urls[:1]
            )
        )
        built.append(
            ClaimUnit(
                id=f"claim_{index}",
                text=claim_text,
                importance=importance,
                evidence_passage_ids=evidence_passage_ids,
                evidence_urls=evidence_urls,
                grounded=bool(evidence_passage_ids),
            ).to_dict()
        )
    return built


def _build_claim_units_with_llm(
    llm: Any,
    config: dict[str, Any],
    *,
    summary: str,
    key_findings: list[str],
    passages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not passages:
        return []

    claims: list[dict[str, Any]] = []
    summary_text = str(summary or "").strip()
    if summary_text:
        claims.append({"text": summary_text, "importance": "primary"})
    for index, finding in enumerate(_dedupe_strings(key_findings or [], limit=4), 1):
        claims.append({"text": finding, "importance": "primary" if index <= 2 else "secondary"})
    if not claims:
        return []

    passage_lines: list[dict[str, Any]] = []
    for item in passages[:8]:
        passage_id = str(item.get("id") or "").strip()
        if not passage_id:
            continue
        passage_lines.append(
            {
                "id": passage_id,
                "url": str(item.get("url") or "").strip(),
                "source_title": str(item.get("source_title") or item.get("page_title") or "").strip(),
                "quote": _clamp_text(item.get("quote") or item.get("text") or "", 200),
            }
        )
    if not passage_lines:
        return []

    prompt = ChatPromptTemplate.from_messages([("user", DEEP_RESEARCHER_CLAIM_GROUNDING_PROMPT)])
    messages = prompt.format_messages(
        claims=json.dumps(claims, ensure_ascii=False, indent=2),
        passages=json.dumps(passage_lines, ensure_ascii=False, indent=2),
    )
    try:
        response = llm.invoke(messages, config=config)
    except Exception:
        return []
    payload = parse_synthesis_payload(getattr(response, "content", "") or "")
    items = payload.get("claims")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _finalize_claim_units(
    grounded_claims: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    passage_index = {
        str(item.get("id") or "").strip(): item
        for item in passages or []
        if str(item.get("id") or "").strip()
    }
    source_urls = [
        str(item.get("url") or "").strip()
        for item in sources or []
        if str(item.get("url") or "").strip()
    ]
    built: list[dict[str, Any]] = []
    for index, claim in enumerate(grounded_claims, 1):
        text = str(claim.get("text") or "").strip()
        if not text:
            continue
        evidence_passage_ids = [
            str(item).strip()
            for item in list(claim.get("evidence_passage_ids") or [])
            if str(item).strip() in passage_index
        ][:2]
        evidence_urls = list(
            dict.fromkeys(
                [
                    str(passage_index[passage_id].get("url") or "").strip()
                    for passage_id in evidence_passage_ids
                    if str(passage_index[passage_id].get("url") or "").strip()
                ]
                or source_urls[:1]
            )
        )
        built.append(
            ClaimUnit(
                id=f"claim_{index}",
                text=text,
                importance=str(claim.get("importance") or "secondary").strip() or "secondary",
                evidence_passage_ids=evidence_passage_ids,
                evidence_urls=evidence_urls,
                grounded=bool(evidence_passage_ids),
            ).to_dict()
        )
    return built
