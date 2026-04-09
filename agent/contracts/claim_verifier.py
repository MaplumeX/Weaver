"""
Claim verifier that matches report claims against collected evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.contracts.source_registry import SourceRegistry

_CLAIM_MARKERS = (
    "research",
    "study",
    "report",
    "data",
    "according to",
    "shows",
    "found",
    "研究",
    "报告",
    "数据显示",
    "统计",
    "增长",
    "下降",
)

_NEGATION_MARKERS = (
    "not",
    "no",
    "never",
    "without",
    "didn't",
    "doesn't",
    "isn't",
    "wasn't",
    "不是",
    "并非",
    "没有",
    "未",
    "无",
)

_UP_MARKERS = ("increase", "increased", "grow", "growth", "up", "rise", "rose", "增长", "上升")
_DOWN_MARKERS = ("decrease", "decreased", "decline", "down", "fell", "drop", "下降", "减少")

_STOPWORDS = {
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
    "在",
    "是",
    "了",
    "和",
    "与",
    "对",
    "将",
    "及",
}


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    return [
        part.strip()
        for part in re.split(r"(?<=[。！？])|(?<=[.!?])\s+|\n+", text)
        if part and part.strip()
    ]


def _contains_marker(text: str, marker: str) -> bool:
    lower = (text or "").lower()
    if not lower:
        return False
    if re.search(r"[a-z]", marker):
        return re.search(rf"(?<![a-z]){re.escape(marker.lower())}(?![a-z])", lower) is not None
    return marker in lower


def _token_fragments(text: str) -> set[str]:
    normalized = (text or "").lower()
    fragments: set[str] = set()
    for token in re.findall(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?|[\u4e00-\u9fff]+", normalized):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) == 1:
                if token not in _STOPWORDS:
                    fragments.add(token)
                continue
            for index in range(len(token)):
                single = token[index]
                if single not in _STOPWORDS:
                    fragments.add(single)
                if index < len(token) - 1:
                    fragments.add(token[index : index + 2])
            continue
        if token not in _STOPWORDS:
            fragments.add(token)
    return fragments


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"


@dataclass
class ClaimCheck:
    claim: str
    status: ClaimStatus
    claim_id: str = ""
    evidence_urls: list[str] = field(default_factory=list)
    evidence_passages: list[dict[str, Any]] = field(default_factory=list)
    evidence_passage_ids: list[str] = field(default_factory=list)
    score: float = 0.0
    notes: str = ""


class ClaimVerifier:
    """Deterministic claim-to-evidence matcher."""

    def __init__(self, min_overlap_tokens: int = 2, *, max_evidence_per_claim: int = 5):
        self.min_overlap_tokens = max(1, int(min_overlap_tokens))
        self.max_evidence_per_claim = max(1, int(max_evidence_per_claim))

    def extract_claims(self, report: str, max_claims: int = 10) -> list[str]:
        if not report:
            return []

        candidates = _split_sentences(report)
        claims: list[str] = []
        fallback_claims: list[str] = []
        seen: set[str] = set()

        for sentence in candidates:
            text = sentence.strip()
            if len(text) < 20:
                continue
            fallback_claims.append(text)
            lower = text.lower()
            has_signal = any(marker in lower for marker in _CLAIM_MARKERS) or bool(
                re.search(r"\d{2,4}|\d+%|\d+\.\d+", text)
            )
            if not has_signal:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            claims.append(text)
            if len(claims) >= max_claims:
                break

        if claims:
            return claims

        deduped_fallbacks: list[str] = []
        seen_fallbacks: set[str] = set()
        for text in fallback_claims:
            key = text.lower()
            if key in seen_fallbacks:
                continue
            seen_fallbacks.add(key)
            deduped_fallbacks.append(text)
            if len(deduped_fallbacks) >= max_claims:
                break
        return deduped_fallbacks

    def verify_report(
        self,
        report: str,
        scraped_content: list[dict[str, Any]],
        max_claims: int = 10,
        passages: list[dict[str, Any]] | None = None,
    ) -> list[ClaimCheck]:
        claims = self.extract_claims(report, max_claims=max_claims)
        if not claims:
            return []
        evidence = self._extract_evidence(scraped_content, passages=passages)
        return [self.verify_claim(claim, evidence) for claim in claims]

    def verify_claim(self, claim: str, evidence: list[dict[str, Any]]) -> ClaimCheck:
        return self.verify_claim_unit({"claim": claim}, evidence)

    def verify_claim_unit(
        self,
        claim_unit: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> ClaimCheck:
        claim = str(claim_unit.get("claim") or "").strip()
        claim_id = str(claim_unit.get("id") or "").strip()
        claim_tokens = self._tokenize(claim)
        if not claim_tokens:
            return ClaimCheck(claim=claim, claim_id=claim_id, status=ClaimStatus.UNSUPPORTED)

        supported: list[tuple[int, str, dict[str, Any]]] = []
        contradicted: list[tuple[int, str, dict[str, Any]]] = []
        best_overlap = 0

        for item in evidence:
            if item.get("admissible") is False:
                continue
            url = str(item.get("url") or "").strip() or "unknown"
            text = str(item.get("text") or "").strip()
            evidence_tokens = self._tokenize(text)
            overlap = len(claim_tokens & evidence_tokens)
            if overlap < self.min_overlap_tokens:
                continue

            best_overlap = max(best_overlap, overlap)
            passage_payload: dict[str, Any] = {
                "url": url,
            }
            snippet_hash = str(item.get("snippet_hash") or "").strip()
            if snippet_hash:
                passage_payload["snippet_hash"] = snippet_hash
            quote = str(item.get("quote") or "").strip()
            if quote:
                passage_payload["quote"] = quote
            passage_id = str(item.get("passage_id") or item.get("id") or "").strip()
            if passage_id:
                passage_payload["passage_id"] = passage_id
            heading_path = item.get("heading_path")
            if isinstance(heading_path, list) and all(isinstance(p, str) for p in heading_path):
                passage_payload["heading_path"] = heading_path

            if self._is_contradiction(claim, text):
                contradicted.append((overlap, url, passage_payload))
            else:
                supported.append((overlap, url, passage_payload))

        contradicted.sort(key=lambda row: -row[0])
        supported.sort(key=lambda row: -row[0])
        limit = self.max_evidence_per_claim

        if contradicted:
            urls = list(dict.fromkeys([u for _o, u, _p in contradicted] + [u for _o, u, _p in supported]))
            evidence_passages = [p for _o, _u, p in (contradicted + supported)][:limit]
            return ClaimCheck(
                claim=claim,
                claim_id=claim_id,
                status=ClaimStatus.CONTRADICTED,
                evidence_urls=urls[:limit],
                evidence_passages=evidence_passages,
                evidence_passage_ids=[
                    str(p.get("passage_id") or "").strip()
                    for p in evidence_passages
                    if str(p.get("passage_id") or "").strip()
                ],
                score=float(best_overlap),
                notes="conflicting evidence found",
            )

        if supported:
            return ClaimCheck(
                claim=claim,
                claim_id=claim_id,
                status=ClaimStatus.VERIFIED,
                evidence_urls=list(dict.fromkeys([u for _o, u, _p in supported]))[:limit],
                evidence_passages=[p for _o, _u, p in supported][:limit],
                evidence_passage_ids=[
                    str(p.get("passage_id") or "").strip()
                    for _o, _u, p in supported[:limit]
                    if str(p.get("passage_id") or "").strip()
                ],
                score=float(best_overlap),
                notes="supported by evidence",
            )

        return ClaimCheck(
            claim=claim,
            claim_id=claim_id,
            status=ClaimStatus.UNSUPPORTED,
            evidence_urls=[],
            evidence_passages=[],
            evidence_passage_ids=[],
            score=0.0,
            notes="no matching evidence",
        )

    def _extract_evidence(
        self,
        scraped_content: list[dict[str, Any]],
        *,
        passages: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        source_registry = SourceRegistry()

        if passages:
            for passage in passages:
                if not isinstance(passage, dict):
                    continue
                url = str(passage.get("url") or "").strip()
                if not url:
                    continue
                canonical_url = source_registry.canonicalize_url(url) or url
                passage_id = str(passage.get("passage_id") or passage.get("id") or "").strip()
                text = str(passage.get("text") or "").strip()
                if not text or not passage_id:
                    continue
                has_locator = bool(
                    passage.get("quote")
                    or passage.get("heading_path")
                    or passage.get("locator")
                    or passage.get("document_id")
                )
                admissible = bool(passage.get("admissible", True)) and has_locator
                item: dict[str, Any] = {
                    "url": canonical_url,
                    "text": text,
                    "admissible": admissible,
                }
                item["passage_id"] = passage_id
                snippet_hash = str(passage.get("snippet_hash") or "").strip()
                if snippet_hash:
                    item["snippet_hash"] = snippet_hash
                quote = str(passage.get("quote") or "").strip()
                if quote:
                    item["quote"] = quote
                heading_path = passage.get("heading_path")
                if isinstance(heading_path, list) and all(isinstance(p, str) for p in heading_path):
                    item["heading_path"] = heading_path
                evidence.append(item)
            return evidence

        for item in scraped_content or []:
            for result in item.get("results", []) or []:
                url = str(result.get("url") or "").strip() or "unknown"
                canonical_url = source_registry.canonicalize_url(url) or url
                text = (
                    result.get("raw_excerpt")
                    or result.get("content")
                    or result.get("summary")
                    or result.get("snippet")
                    or ""
                )
                text = str(text).strip()
                if text:
                    evidence.append({"url": canonical_url, "text": text, "admissible": False})
        return evidence

    def _tokenize(self, text: str) -> set[str]:
        tokens = _token_fragments(text)
        return {t for t in tokens if len(t) > 1 or t.isdigit()}

    def _has_negation(self, text: str) -> bool:
        return any(_contains_marker(text, marker) for marker in _NEGATION_MARKERS)

    def _trend_direction(self, text: str) -> int:
        up = any(_contains_marker(text, marker) for marker in _UP_MARKERS)
        down = any(_contains_marker(text, marker) for marker in _DOWN_MARKERS)
        if up and not down:
            return 1
        if down and not up:
            return -1
        return 0

    def _primary_percentage_literal(self, text: str) -> str:
        matches = re.findall(r"\d+(?:\.\d+)?%", str(text or ""))
        if len(matches) == 1:
            return matches[0]
        return ""

    def _primary_date_literal(self, text: str) -> str:
        raw = str(text or "")
        explicit_dates = re.findall(
            r"\b\d{4}-\d{1,2}(?:-\d{1,2})?\b"
            r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
            r"|(?:19|20)\d{2}年(?:\d{1,2}月(?:\d{1,2}日)?)?"
            r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}\b",
            raw,
            flags=re.IGNORECASE,
        )
        if len(explicit_dates) == 1:
            return self._normalize_date_literal(explicit_dates[0])
        years = re.findall(r"\b(?:19|20)\d{2}\b|(?:19|20)\d{2}年", raw)
        if len(years) == 1:
            return self._normalize_date_literal(years[0])
        return ""

    def _normalize_date_literal(self, value: str) -> str:
        normalized = str(value or "").strip().lower()
        normalized = normalized.replace("年", "-").replace("月", "-").replace("日", "")
        normalized = normalized.replace("/", "-").replace(".", "-")
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"-+", "-", normalized).strip("- ")
        return normalized

    def _is_contradiction(self, claim: str, evidence: str) -> bool:
        claim_neg = self._has_negation(claim)
        evidence_neg = self._has_negation(evidence)
        if claim_neg != evidence_neg:
            return True

        claim_dir = self._trend_direction(claim)
        evidence_dir = self._trend_direction(evidence)
        if claim_dir != 0 and evidence_dir != 0 and claim_dir != evidence_dir:
            return True

        claim_percentage = self._primary_percentage_literal(claim)
        evidence_percentage = self._primary_percentage_literal(evidence)
        if claim_percentage and evidence_percentage and claim_percentage != evidence_percentage:
            return True

        claim_date = self._primary_date_literal(claim)
        evidence_date = self._primary_date_literal(evidence)
        if claim_date and evidence_date and claim_date != evidence_date:
            return True

        return False
