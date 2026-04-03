"""
Bounded tool-agent helpers for Deep Research multi-agent runtime.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, tool

import agent.runtime.deep.support.runtime_support as support
from agent.runtime.deep.schema import (
    BranchSynthesis,
    ClaimUnit,
    CoordinationRequest,
    EvidenceCard,
    EvidencePassage,
    FetchedDocument,
    FinalReportArtifact,
    ReportSectionDraft,
    ResearchSubmission,
    ResearchTask,
    SourceCandidate,
    VerificationResult,
    validate_coordination_request_type,
)
from agent.runtime.deep.services.verification import derive_claim_units
from agent.builders.agent_factory import build_deep_research_tool_agent
from agent.contracts.claim_verifier import ClaimStatus


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


def _extract_agent_text(response: Any) -> str:
    if isinstance(response, dict) and response.get("messages"):
        last = response["messages"][-1]
        return getattr(last, "content", "") if hasattr(last, "content") else str(last)
    return getattr(response, "content", None) or str(response or "")


def _split_findings(summary: str) -> list[str]:
    text = str(summary or "").strip()
    if not text:
        return []
    parts = [item.strip(" -•\t") for item in text.replace("\r", "\n").split("\n") if item.strip()]
    findings = [part for part in parts if len(part) >= 12]
    if findings:
        return findings[:6]
    return [text[:300]]


def _criterion_is_covered(summary: str, criterion: str) -> bool:
    criterion_text = str(criterion or "").strip().lower()
    summary_text = str(summary or "").strip().lower()
    if not criterion_text or not summary_text:
        return False
    tokens = [token for token in re.split(r"[\s,，]+", criterion_text) if len(token) > 1]
    if not tokens:
        return criterion_text in summary_text
    matches = sum(1 for token in tokens if token in summary_text)
    return matches >= max(1, min(2, len(tokens)))


def _normalize_ids(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _related_contract_ids(session: "DeepResearchToolAgentSession", artifact_key: str) -> set[str]:
    if artifact_key == "claim_ids":
        values = [item.id for item in session.claim_units if item.id]
        if not values and session.branch_synthesis:
            values = [item for item in session.branch_synthesis.claim_ids if item]
        if not values:
            values = [
                str(item.get("id") or "").strip()
                for item in session.related_artifacts.get("claim_units", [])
                if isinstance(item, dict)
            ]
        return {item for item in values if item}
    field_map = {
        "obligation_ids": "coverage_obligations",
        "consistency_result_ids": "consistency_results",
        "issue_ids": "revision_issues",
    }
    artifact_name = field_map.get(artifact_key, "")
    if not artifact_name:
        return set()
    return {
        str(item.get("id") or "").strip()
        for item in session.related_artifacts.get(artifact_name, [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _validate_verifier_contract_submission(
    session: "DeepResearchToolAgentSession",
    *,
    validation_stage: str,
    claim_ids: list[str] | None,
    obligation_ids: list[str] | None,
    consistency_result_ids: list[str] | None,
    issue_ids: list[str] | None,
) -> tuple[list[str], list[str], list[str], list[str]]:
    normalized_claim_ids = _normalize_ids(claim_ids)
    normalized_obligation_ids = _normalize_ids(obligation_ids)
    normalized_consistency_ids = _normalize_ids(consistency_result_ids)
    normalized_issue_ids = _normalize_ids(issue_ids)

    stage_requirements = {
        "claim_check": ("claim_ids", normalized_claim_ids),
        "coverage_check": ("obligation_ids", normalized_obligation_ids),
        "consistency_check": ("consistency_result_ids", normalized_consistency_ids),
    }
    required = stage_requirements.get(str(validation_stage or "").strip())
    if required is not None and not required[1]:
        raise ValueError(f"{validation_stage} submissions must include {required[0]}")

    if not any(
        (
            normalized_claim_ids,
            normalized_obligation_ids,
            normalized_consistency_ids,
            normalized_issue_ids,
        )
    ):
        raise ValueError("verifier submissions must reference claim_ids, obligation_ids, consistency_result_ids, or issue_ids")

    for field_name, values in (
        ("claim_ids", normalized_claim_ids),
        ("obligation_ids", normalized_obligation_ids),
        ("consistency_result_ids", normalized_consistency_ids),
        ("issue_ids", normalized_issue_ids),
    ):
        known_ids = _related_contract_ids(session, field_name)
        if known_ids and not set(values).issubset(known_ids):
            unknown_ids = sorted(set(values) - known_ids)
            raise ValueError(f"{field_name} contains unknown ids: {unknown_ids}")

    return (
        normalized_claim_ids,
        normalized_obligation_ids,
        normalized_consistency_ids,
        normalized_issue_ids,
    )


@dataclass
class DeepResearchToolAgentSession:
    runtime: Any
    role: str
    topic: str
    graph_run_id: str
    branch_id: str | None
    task: ResearchTask | None = None
    iteration: int = 0
    attempt: int = 1
    allowed_capabilities: set[str] = field(default_factory=set)
    approved_scope: dict[str, Any] = field(default_factory=dict)
    related_artifacts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    source_candidates: list[SourceCandidate] = field(default_factory=list)
    fetched_documents: list[FetchedDocument] = field(default_factory=list)
    evidence_passages: list[EvidencePassage] = field(default_factory=list)
    evidence_cards: list[EvidenceCard] = field(default_factory=list)
    branch_synthesis: BranchSynthesis | None = None
    section_draft: ReportSectionDraft | None = None
    claim_units: list[ClaimUnit] = field(default_factory=list)
    verification_results: list[VerificationResult] = field(default_factory=list)
    coordination_requests: list[CoordinationRequest] = field(default_factory=list)
    submissions: list[ResearchSubmission] = field(default_factory=list)
    final_report: FinalReportArtifact | None = None
    searches_used: int = 0
    tokens_used: int = 0
    notes: list[str] = field(default_factory=list)

    def ensure_capability(self, capability: str) -> None:
        if capability not in self.allowed_capabilities:
            raise RuntimeError(f"{self.role} role is not allowed to use capability: {capability}")

    def budget_stop_reason(self) -> str | None:
        return support._budget_stop_reason(
            start_ts=self.runtime.start_ts,
            searches_used=self.runtime.searches_used + self.searches_used,
            tokens_used=self.runtime.tokens_used + self.tokens_used,
            max_seconds=self.runtime.max_seconds,
            max_tokens=self.runtime.max_tokens,
            max_searches=self.runtime.max_searches,
        )

    def find_search_result(self, url: str) -> dict[str, Any] | None:
        normalized_url = str(url or "").strip()
        if not normalized_url:
            return None
        for item in self.search_results:
            if str(item.get("url") or "").strip() == normalized_url:
                return item
        return None

    def _ensure_extracted_result(self, result: dict[str, Any]) -> dict[str, str]:
        url = str(result.get("url") or "").strip()
        existing_candidate = next((item for item in self.source_candidates if item.url == url), None)
        existing_document = next((item for item in self.fetched_documents if item.url == url), None)
        existing_passage = next((item for item in self.evidence_passages if item.url == url), None)
        existing_card = next((item for item in self.evidence_cards if item.source_url == url), None)

        if existing_candidate and existing_document and existing_passage and existing_card:
            return {
                "source_candidate_id": existing_candidate.id,
                "document_id": existing_document.id,
                "passage_id": existing_passage.id,
                "evidence_id": existing_card.id,
            }

        source_candidate_id = existing_candidate.id if existing_candidate else support._new_id("source")
        document_id = existing_document.id if existing_document else support._new_id("document")
        passage_id = existing_passage.id if existing_passage else support._new_id("passage")
        evidence_id = existing_card.id if existing_card else support._new_id("evidence")
        task_id = self.task.id if self.task else ""
        title = str(result.get("title") or result.get("url") or "Untitled").strip()
        content = str(
            result.get("raw_excerpt")
            or result.get("content")
            or result.get("summary")
            or result.get("snippet")
            or ""
        ).strip()
        summary_text = str(result.get("summary") or result.get("snippet") or content[:280]).strip()

        if not existing_candidate:
            self.source_candidates.append(
                SourceCandidate(
                    id=source_candidate_id,
                    task_id=task_id,
                    branch_id=self.branch_id,
                    title=title,
                    url=url,
                    summary=summary_text[:400],
                    rank=len(self.source_candidates) + 1,
                    source_provider=str(result.get("provider") or ""),
                    published_date=result.get("published_date"),
                    created_by=self.role,
                    metadata={"graph_run_id": self.graph_run_id, "attempt": self.attempt},
                )
            )
        if not existing_document:
            self.fetched_documents.append(
                FetchedDocument(
                    id=document_id,
                    task_id=task_id,
                    branch_id=self.branch_id,
                    source_candidate_id=source_candidate_id,
                    url=url,
                    title=title,
                    content=content[:2400],
                    excerpt=content[:700],
                    created_by=self.role,
                    metadata={"graph_run_id": self.graph_run_id, "attempt": self.attempt},
                )
            )
        if not existing_passage:
            self.evidence_passages.append(
                EvidencePassage(
                    id=passage_id,
                    task_id=task_id,
                    branch_id=self.branch_id,
                    document_id=document_id,
                    url=url,
                    text=content[:900],
                    quote=content[:240],
                    source_title=title,
                    snippet_hash=f"{task_id}-{len(self.evidence_passages)+1}-{self.attempt}",
                    created_by=self.role,
                    metadata={"graph_run_id": self.graph_run_id, "attempt": self.attempt},
                )
            )
        if not existing_card:
            self.evidence_cards.append(
                EvidenceCard(
                    id=evidence_id,
                    task_id=task_id,
                    branch_id=self.branch_id,
                    source_title=title,
                    source_url=url,
                    summary=summary_text[:280],
                    excerpt=content[:700],
                    source_provider=str(result.get("provider") or ""),
                    published_date=result.get("published_date"),
                    created_by=self.role,
                    metadata={"graph_run_id": self.graph_run_id, "attempt": self.attempt},
                )
            )

        return {
            "source_candidate_id": source_candidate_id,
            "document_id": document_id,
            "passage_id": passage_id,
            "evidence_id": evidence_id,
        }

    def ensure_minimum_evidence(self) -> None:
        if self.source_candidates or not self.search_results:
            return
        for item in self.search_results[: min(3, len(self.search_results))]:
            self._ensure_extracted_result(item)

    def submit_research_bundle(
        self,
        *,
        summary: str,
        findings: list[str] | None = None,
        result_status: str = "completed",
        resolved_issue_ids: list[str] | None = None,
    ) -> ResearchSubmission:
        self.ensure_minimum_evidence()
        findings = list(findings or _split_findings(summary))
        citation_urls = list(dict.fromkeys([item.url for item in self.source_candidates if item.url]))
        if not self.branch_synthesis:
            self.branch_synthesis = BranchSynthesis(
                id=support._new_id("synthesis"),
                task_id=self.task.id if self.task else "",
                branch_id=self.branch_id,
                objective=(self.task.objective if self.task else self.topic),
                summary=summary,
                findings=findings,
                acceptance_criteria=list(self.task.acceptance_criteria if self.task else []),
                evidence_passage_ids=[item.id for item in self.evidence_passages],
                source_document_ids=[item.id for item in self.fetched_documents],
                citation_urls=citation_urls,
                revision_brief_id=self.task.revision_brief_id if self.task else None,
                created_by=self.role,
                metadata={"graph_run_id": self.graph_run_id, "attempt": self.attempt},
            )
        self.claim_units = derive_claim_units(
            claim_verifier=self.runtime.claim_verifier,
            task=self.task,
            synthesis=self.branch_synthesis,
            created_by=self.role,
            existing_claim_units=self.claim_units,
        ) if self.task and self.branch_synthesis else []
        if self.branch_synthesis:
            self.branch_synthesis.claim_ids = [item.id for item in self.claim_units]
            self.branch_synthesis.metadata.setdefault("addressed_issue_ids", list(self.task.target_issue_ids if self.task else []))
        if not self.section_draft:
            self.section_draft = ReportSectionDraft(
                id=support._new_id("section"),
                task_id=self.task.id if self.task else "",
                title=self.task.title if self.task else self.topic,
                summary=summary,
                branch_id=self.branch_id,
                evidence_ids=[item.id for item in self.evidence_cards],
                created_by=self.role,
            )
        submission = ResearchSubmission(
            id=support._new_id("submission"),
            submission_kind="research_bundle",
            summary=summary[:240],
            task_id=self.task.id if self.task else None,
            branch_id=self.branch_id,
            created_by=self.role,
            result_status=result_status,
            stage="submit",
            artifact_ids=[
                *[item.id for item in self.source_candidates],
                *[item.id for item in self.fetched_documents],
                *[item.id for item in self.evidence_passages],
                *[item.id for item in self.evidence_cards],
                *[item.id for item in self.claim_units],
                self.branch_synthesis.id,
                self.section_draft.id,
            ],
            claim_ids=[item.id for item in self.claim_units],
            resolved_issue_ids=list(resolved_issue_ids or []),
            metadata={"graph_run_id": self.graph_run_id, "attempt": self.attempt},
        )
        self.submissions.append(submission)
        return submission

    def submit_verification_bundle(
        self,
        *,
        validation_stage: str,
        outcome: str,
        summary: str,
        recommended_action: str,
        gap_ids: list[str] | None = None,
        evidence_urls: list[str] | None = None,
        evidence_passage_ids: list[str] | None = None,
        request_ids: list[str] | None = None,
        claim_ids: list[str] | None = None,
        obligation_ids: list[str] | None = None,
        consistency_result_ids: list[str] | None = None,
        issue_ids: list[str] | None = None,
    ) -> tuple[VerificationResult, ResearchSubmission]:
        (
            normalized_claim_ids,
            normalized_obligation_ids,
            normalized_consistency_ids,
            normalized_issue_ids,
        ) = _validate_verifier_contract_submission(
            self,
            validation_stage=validation_stage,
            claim_ids=claim_ids,
            obligation_ids=obligation_ids,
            consistency_result_ids=consistency_result_ids,
            issue_ids=issue_ids,
        )
        verification = VerificationResult(
            id=support._new_id("verification"),
            task_id=self.task.id if self.task else "",
            branch_id=self.branch_id,
            synthesis_id=self.branch_synthesis.id if self.branch_synthesis else None,
            validation_stage=validation_stage,
            outcome=outcome,
            summary=summary,
            recommended_action=recommended_action,
            evidence_urls=list(evidence_urls or []),
            evidence_passage_ids=list(evidence_passage_ids or []),
            gap_ids=list(gap_ids or []),
            created_by=self.role,
            metadata={
                "graph_run_id": self.graph_run_id,
                "attempt": self.attempt,
                "claim_ids": normalized_claim_ids,
                "obligation_ids": normalized_obligation_ids,
                "consistency_result_ids": normalized_consistency_ids,
                "issue_ids": normalized_issue_ids,
            },
        )
        submission = ResearchSubmission(
            id=support._new_id("submission"),
            submission_kind="verification_bundle",
            summary=summary[:240],
            task_id=self.task.id if self.task else None,
            branch_id=self.branch_id,
            created_by=self.role,
            result_status=outcome,
            stage="verify",
            validation_stage=validation_stage,
            artifact_ids=[verification.id],
            request_ids=list(request_ids or []),
            claim_ids=normalized_claim_ids,
            obligation_ids=normalized_obligation_ids,
            consistency_result_ids=normalized_consistency_ids,
            issue_ids=normalized_issue_ids,
            metadata={"recommended_action": recommended_action},
        )
        self.verification_results.append(verification)
        self.submissions.append(submission)
        return verification, submission

    def submit_report_bundle(
        self,
        *,
        report_markdown: str,
        executive_summary: str,
        citation_urls: list[str] | None = None,
    ) -> tuple[FinalReportArtifact, ResearchSubmission]:
        final_report = FinalReportArtifact(
            id=support._new_id("final_report"),
            report_markdown=report_markdown,
            executive_summary=executive_summary,
            citation_urls=list(citation_urls or []),
            created_by=self.role,
        )
        submission = ResearchSubmission(
            id=support._new_id("submission"),
            submission_kind="report_bundle",
            summary=executive_summary[:240] or report_markdown[:240],
            branch_id=self.branch_id,
            created_by=self.role,
            result_status="completed",
            stage="submit",
            artifact_ids=[final_report.id],
        )
        self.final_report = final_report
        self.submissions.append(submission)
        return final_report, submission

    def request_follow_up(
        self,
        *,
        request_type: str,
        summary: str,
        suggested_queries: list[str] | None = None,
        artifact_ids: list[str] | None = None,
        impact_scope: str = "",
        reason: str = "",
        blocking_level: str = "blocking",
        suggested_next_action: str = "",
    ) -> CoordinationRequest:
        request = CoordinationRequest(
            id=support._new_id("request"),
            request_type=validate_coordination_request_type(request_type),
            summary=summary,
            branch_id=self.branch_id,
            task_id=self.task.id if self.task else None,
            requested_by=self.role,
            artifact_ids=list(artifact_ids or []),
            suggested_queries=list(suggested_queries or []),
            impact_scope=impact_scope,
            reason=reason or summary,
            blocking_level=blocking_level,
            suggested_next_action=suggested_next_action,
            metadata={"graph_run_id": self.graph_run_id, "attempt": self.attempt},
        )
        self.coordination_requests.append(request)
        return request


def build_deep_research_fabric_tools(session: DeepResearchToolAgentSession) -> list[BaseTool]:
    base_tools: list[BaseTool] = []

    @tool
    def fabric_get_scope() -> dict[str, Any]:
        """Return the approved scope and current budget summary for the current Deep Research run."""
        return {
            "approved_scope": session.approved_scope,
            "budget": {
                "searches_used": session.runtime.searches_used + session.searches_used,
                "tokens_used": session.runtime.tokens_used + session.tokens_used,
                "max_searches": session.runtime.max_searches,
                "max_tokens": session.runtime.max_tokens,
                "max_seconds": session.runtime.max_seconds,
                "budget_stop_reason": session.budget_stop_reason(),
            },
        }

    @tool
    def fabric_get_research_brief() -> dict[str, Any]:
        """Return the canonical research brief when it has already been generated."""
        brief = session.related_artifacts.get("research_brief")
        return brief if isinstance(brief, dict) else {}

    @tool
    def fabric_get_task() -> dict[str, Any]:
        """Return the current branch task, role boundary and allowed capability summary."""
        return {
            "role": session.role,
            "topic": session.topic,
            "branch_id": session.branch_id,
            "allowed_capabilities": sorted(session.allowed_capabilities),
            "task": session.task.to_dict() if session.task else {},
        }

    @tool
    def fabric_get_related_artifacts() -> dict[str, Any]:
        """Return the related blackboard artifacts already available to the current role."""
        return session.related_artifacts

    @tool
    def fabric_get_verification_contracts() -> dict[str, Any]:
        """Return structured claim / obligation / issue / revision contracts for the active branch."""
        payload: dict[str, Any] = {}
        for key in (
            "claim_units",
            "coverage_obligations",
            "claim_grounding_results",
            "coverage_evaluation_results",
            "consistency_results",
            "revision_issues",
            "revision_briefs",
        ):
            value = session.related_artifacts.get(key)
            payload[key] = list(value) if isinstance(value, list) else []
        return payload

    @tool
    def fabric_get_control_plane() -> dict[str, Any]:
        """Return the structured control-plane artifacts relevant to the current role."""
        payload: dict[str, Any] = {}
        for key in (
            "task_ledger",
            "progress_ledger",
            "coverage_matrix",
            "contradiction_registry",
            "missing_evidence_list",
            "outline",
        ):
            value = session.related_artifacts.get(key)
            payload[key] = value if isinstance(value, dict) else {}
        return payload

    base_tools.extend(
        [
            fabric_get_scope,
            fabric_get_research_brief,
            fabric_get_task,
            fabric_get_related_artifacts,
            fabric_get_verification_contracts,
            fabric_get_control_plane,
        ]
    )

    if session.role == "supervisor":
        @tool
        def fabric_get_task_queue() -> dict[str, Any]:
            """Return the current task queue snapshot for supervisor planning or dispatch decisions."""
            return session.runtime.task_queue.snapshot()

        @tool
        def fabric_get_open_requests() -> list[dict[str, Any]]:
            """Return currently open coordination requests waiting for supervisor review."""
            return [
                request.to_dict()
                for request in session.runtime.artifact_store.coordination_requests(status="open")
            ]

        base_tools.extend([fabric_get_task_queue, fabric_get_open_requests])
        return base_tools

    if "search" in session.allowed_capabilities:
        @tool
        def fabric_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
            """Search current web sources for the active Deep Research task and cache the normalized results."""
            session.ensure_capability("search")
            reason = session.budget_stop_reason()
            if reason:
                raise RuntimeError(reason)
            results = session.runtime._search_with_tracking(
                {"query": query, "max_results": max(1, int(max_results or 5))},
                session.runtime.config,
            )
            session.searches_used += 1
            session.tokens_used += support._estimate_tokens_from_results(results)
            for item in results:
                if isinstance(item, dict):
                    session.search_results.append(dict(item))
            return support._compact_sources(results, limit=max(1, int(max_results or 5)))

        base_tools.append(fabric_search)

    if "read" in session.allowed_capabilities:
        @tool
        def fabric_read(url: str) -> dict[str, Any]:
            """Read the cached content or excerpt for a previously discovered source URL."""
            session.ensure_capability("read")
            result = session.find_search_result(url)
            if result:
                text = str(
                    result.get("raw_excerpt")
                    or result.get("content")
                    or result.get("summary")
                    or result.get("snippet")
                    or ""
                )
                session.tokens_used += support._estimate_tokens_from_text(text)
                return {
                    "url": url,
                    "title": str(result.get("title") or url),
                    "content": text,
                    "summary": str(result.get("summary") or result.get("snippet") or text[:280]),
                }
            for item in session.related_artifacts.get("fetched_documents", []):
                if str(item.get("url") or "") == str(url or ""):
                    text = str(item.get("content") or item.get("excerpt") or "")
                    session.tokens_used += support._estimate_tokens_from_text(text)
                    return {
                        "url": url,
                        "title": str(item.get("title") or url),
                        "content": text,
                        "summary": str(item.get("excerpt") or text[:280]),
                    }
            return {"url": url, "title": url, "content": "", "summary": ""}

        base_tools.append(fabric_read)

    if "extract" in session.allowed_capabilities:
        @tool
        def fabric_extract(url: str) -> dict[str, Any]:
            """Convert a discovered source URL into structured source/document/passage/evidence artifacts."""
            session.ensure_capability("extract")
            result = session.find_search_result(url)
            if not result:
                raise RuntimeError(f"no cached search result for url: {url}")
            artifact_ids = session._ensure_extracted_result(result)
            return {"url": url, **artifact_ids}

        base_tools.append(fabric_extract)

    if session.role == "researcher":
        @tool
        def fabric_request_follow_up(
            request_type: str,
            summary: str,
            suggested_queries: list[str] | None = None,
        ) -> dict[str, Any]:
            """Create a structured supervisor request using one of the registered request types only."""
            request = session.request_follow_up(
                request_type=request_type,
                summary=summary,
                suggested_queries=list(suggested_queries or []),
                impact_scope=str(session.branch_id or session.task.id if session.task else ""),
                reason=summary,
                suggested_next_action=request_type,
            )
            return request.to_dict()

        @tool
        def fabric_submit_research_bundle(
            summary: str,
            findings: list[str] | None = None,
            result_status: str = "completed",
            resolved_issue_ids: list[str] | None = None,
        ) -> dict[str, Any]:
            """Submit the current branch research bundle using extracted evidence and a branch summary."""
            submission = session.submit_research_bundle(
                summary=summary,
                findings=list(findings or []),
                result_status=result_status,
                resolved_issue_ids=list(resolved_issue_ids or []),
            )
            return {
                "submission_id": submission.id,
                "branch_synthesis_id": session.branch_synthesis.id if session.branch_synthesis else "",
                "claim_ids": [item.id for item in session.claim_units],
                "result_status": submission.result_status,
            }

        base_tools.extend([fabric_request_follow_up, fabric_submit_research_bundle])

    if session.role == "verifier":
        @tool
        def fabric_challenge_summary(summary: str) -> dict[str, Any]:
            """Challenge a branch summary against current evidence passages and return contradiction or support signals."""
            passages = [
                {
                    "url": passage.url,
                    "text": passage.text,
                    "quote": passage.quote,
                    "snippet_hash": passage.snippet_hash,
                    "heading_path": passage.heading_path,
                }
                for passage in session.evidence_passages
            ] or session.related_artifacts.get("evidence_passages", [])
            claim_checks = session.runtime.claim_verifier.verify_report(summary, [], passages=passages)
            return {
                "claims": [
                    {
                        "claim": check.claim,
                        "status": check.status.value,
                        "evidence_urls": check.evidence_urls,
                        "notes": check.notes,
                    }
                    for check in claim_checks
                ],
                "has_contradiction": any(check.status == ClaimStatus.CONTRADICTED for check in claim_checks),
                "has_unsupported": any(check.status == ClaimStatus.UNSUPPORTED for check in claim_checks),
            }

        @tool
        def fabric_compare_coverage(summary: str, criteria: list[str]) -> dict[str, Any]:
            """Compare a branch summary against acceptance criteria and return missing criteria."""
            missing = [criterion for criterion in (criteria or []) if not _criterion_is_covered(summary, criterion)]
            return {
                "missing_criteria": missing,
                "covered": not missing,
            }

        @tool
        def fabric_analyze_coverage(collected_knowledge: str, executed_queries: list[str] | None = None) -> dict[str, Any]:
            """Run the repository knowledge-gap analyzer to evaluate remaining coverage gaps."""
            result = session.runtime.verifier.analyze(
                session.topic,
                executed_queries=list(executed_queries or []),
                collected_knowledge=collected_knowledge,
            )
            return result.to_dict()

        @tool
        def fabric_submit_verification_bundle(
            validation_stage: str,
            outcome: str,
            summary: str,
            recommended_action: str,
            gap_ids: list[str] | None = None,
            evidence_urls: list[str] | None = None,
            claim_ids: list[str] | None = None,
            obligation_ids: list[str] | None = None,
            consistency_result_ids: list[str] | None = None,
            issue_ids: list[str] | None = None,
        ) -> dict[str, Any]:
            """Submit a structured verification bundle for the current branch using stage-addressable contracts."""
            request_ids: list[str] = []
            if recommended_action in {
                "retry_branch",
                "need_counterevidence",
                "contradiction_found",
                "blocked_by_tooling",
            }:
                request = session.request_follow_up(
                    request_type=recommended_action,
                    summary=summary,
                    suggested_queries=[],
                    impact_scope=str(session.branch_id or session.task.id if session.task else ""),
                    reason=summary,
                    suggested_next_action="supervisor_review",
                )
                request_ids.append(request.id)
            verification, submission = session.submit_verification_bundle(
                validation_stage=validation_stage,
                outcome=outcome,
                summary=summary,
                recommended_action=recommended_action,
                gap_ids=list(gap_ids or []),
                evidence_urls=list(evidence_urls or []),
                evidence_passage_ids=[item.id for item in session.evidence_passages],
                request_ids=request_ids,
                claim_ids=list(claim_ids or []),
                obligation_ids=list(obligation_ids or []),
                consistency_result_ids=list(consistency_result_ids or []),
                issue_ids=list(issue_ids or []),
            )
            return {
                "verification_id": verification.id,
                "submission_id": submission.id,
                "request_ids": request_ids,
            }

        base_tools.extend(
            [
                fabric_challenge_summary,
                fabric_compare_coverage,
                fabric_analyze_coverage,
                fabric_submit_verification_bundle,
            ]
        )

    if session.role == "reporter":
        @tool
        def fabric_get_verified_branch_summaries() -> list[dict[str, Any]]:
            """Return only branch syntheses that have passed both claim and coverage verification."""
            coverage_results = {
                result.task_id: result
                for result in session.runtime.artifact_store.verification_results(validation_stage="coverage_check")
            }
            claim_results = {
                result.task_id: result
                for result in session.runtime.artifact_store.verification_results(validation_stage="claim_check")
            }
            blocking_issue_branch_ids = {
                issue.branch_id
                for issue in session.runtime.artifact_store.revision_issues()
                if issue.blocking and issue.status in {"open", "accepted"} and issue.branch_id
            }
            items: list[dict[str, Any]] = []
            for synthesis in session.runtime.artifact_store.branch_syntheses():
                if (
                    claim_results.get(synthesis.task_id)
                    and coverage_results.get(synthesis.task_id)
                    and claim_results[synthesis.task_id].outcome == "passed"
                    and coverage_results[synthesis.task_id].outcome == "passed"
                    and synthesis.branch_id not in blocking_issue_branch_ids
                ):
                    items.append(synthesis.to_dict())
            return items

        @tool
        def fabric_get_outline_artifact() -> dict[str, Any]:
            """Return the current outline artifact that gates final report generation."""
            outline = session.related_artifacts.get("outline")
            return outline if isinstance(outline, dict) else {}

        @tool
        def fabric_format_report_section(title: str, body: str, sources: list[str] | None = None) -> str:
            """Format one report section in markdown with an optional flat source list."""
            source_lines = ""
            if sources:
                source_lines = "\n" + "\n".join(f"- {url}" for url in sources if url)
            return f"## {title}\n\n{body.strip()}{source_lines}"

        @tool
        def fabric_submit_report_bundle(
            report_markdown: str,
            executive_summary: str,
            citation_urls: list[str] | None = None,
        ) -> dict[str, Any]:
            """Submit the final report bundle derived from verified artifacts only."""
            outline = session.related_artifacts.get("outline")
            if not isinstance(outline, dict) or not outline.get("is_ready"):
                raise RuntimeError("outline_not_ready")
            if outline.get("blocking_gaps"):
                raise RuntimeError("outline_gap_blocking")
            final_report, submission = session.submit_report_bundle(
                report_markdown=report_markdown,
                executive_summary=executive_summary,
                citation_urls=list(citation_urls or []),
            )
            return {"final_report_id": final_report.id, "submission_id": submission.id}

        base_tools.extend(
            [
                fabric_get_verified_branch_summaries,
                fabric_get_outline_artifact,
                fabric_format_report_section,
                fabric_submit_report_bundle,
            ]
        )

    return base_tools


def materialize_session_from_text(session: DeepResearchToolAgentSession, text: str) -> None:
    payload = _extract_json_object(text)
    if not payload:
        return
    if session.role == "researcher" and not session.submissions:
        summary = str(payload.get("summary") or payload.get("result_summary") or "").strip()
        if summary:
            session.submit_research_bundle(
                summary=summary,
                findings=list(payload.get("findings") or []),
                result_status=str(payload.get("result_status") or "completed"),
            )
    elif session.role == "verifier" and not session.submissions:
        summary = str(payload.get("summary") or "").strip()
        outcome = str(payload.get("outcome") or "").strip()
        validation_stage = str(payload.get("validation_stage") or "coverage_check").strip()
        if summary and outcome:
            session.submit_verification_bundle(
                validation_stage=validation_stage,
                outcome=outcome,
                summary=summary,
                recommended_action=str(payload.get("recommended_action") or "report"),
                gap_ids=list(payload.get("gap_ids") or []),
                evidence_urls=list(payload.get("evidence_urls") or []),
                evidence_passage_ids=[item.id for item in session.evidence_passages],
            )
    elif session.role == "reporter" and session.final_report is None:
        report_markdown = str(payload.get("report_markdown") or "").strip()
        executive_summary = str(payload.get("executive_summary") or "").strip()
        if report_markdown:
            session.submit_report_bundle(
                report_markdown=report_markdown,
                executive_summary=executive_summary,
                citation_urls=list(payload.get("citation_urls") or []),
            )


def run_bounded_tool_agent(
    session: DeepResearchToolAgentSession,
    *,
    model: str,
    allowed_tools: list[str] | None,
    system_prompt: str,
    user_prompt: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    tools = build_deep_research_fabric_tools(session)
    agent, agent_tools = build_deep_research_tool_agent(
        model=model,
        role=session.role,
        allowed_tools=allowed_tools,
        extra_tools=tools,
        temperature=0.1,
    )
    response = agent.invoke(
        {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        },
        config=config,
    )
    text = _extract_agent_text(response)
    materialize_session_from_text(session, text)
    return {
        "response": response,
        "text": text,
        "tool_names": [tool.name for tool in agent_tools if getattr(tool, "name", None)],
    }


__all__ = [
    "DeepResearchToolAgentSession",
    "build_deep_research_fabric_tools",
    "materialize_session_from_text",
    "run_bounded_tool_agent",
]
