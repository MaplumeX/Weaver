"""
Bounded tool-agent helpers for Deep Research multi-agent runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, tool

import agent.runtime.deep.support.runtime_support as support
from agent.runtime.deep.schema import (
    AnswerUnit,
    BranchSynthesis,
    ClaimUnit,
    ControlPlaneHandoff,
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
    validate_control_plane_agent,
    validate_coordination_request_type,
)
from agent.runtime.deep.services.verification import (
    derive_answer_units,
    evaluate_obligations,
    ground_claim_units,
    latest_branch_syntheses,
)
from agent.builders.agent_factory import build_deep_research_tool_agent, classify_deep_research_role


_CONTROL_PLANE_HANDOFF_TARGETS: dict[str, set[str]] = {
    "clarify": {"scope"},
    "scope": {"supervisor"},
    "supervisor": {"scope"},
}


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
    if artifact_key == "answer_unit_ids":
        values = [item.id for item in session.answer_units if item.id]
        if not values and session.branch_synthesis:
            values = [item for item in session.branch_synthesis.answer_unit_ids if item]
        if not values:
            values = [
                str(item.get("id") or "").strip()
                for item in session.related_artifacts.get("answer_units", [])
                if isinstance(item, dict)
            ]
        if not values:
            values = [item.id for item in session.claim_units if item.id]
        return {item for item in values if item}
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
    answer_unit_ids: list[str] | None,
    claim_ids: list[str] | None,
    obligation_ids: list[str] | None,
    consistency_result_ids: list[str] | None,
    issue_ids: list[str] | None,
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    normalized_answer_unit_ids = _normalize_ids(answer_unit_ids)
    normalized_claim_ids = _normalize_ids(claim_ids)
    normalized_obligation_ids = _normalize_ids(obligation_ids)
    normalized_consistency_ids = _normalize_ids(consistency_result_ids)
    normalized_issue_ids = _normalize_ids(issue_ids)
    if not normalized_answer_unit_ids and normalized_claim_ids:
        normalized_answer_unit_ids = list(normalized_claim_ids)
    if not normalized_claim_ids and normalized_answer_unit_ids:
        normalized_claim_ids = list(normalized_answer_unit_ids)

    stage_requirements = {
        "claim_check": ("answer_unit_ids", normalized_answer_unit_ids),
        "coverage_check": ("obligation_ids", normalized_obligation_ids),
        "consistency_check": ("consistency_result_ids", normalized_consistency_ids),
    }
    required = stage_requirements.get(str(validation_stage or "").strip())
    if required is not None and not required[1]:
        raise ValueError(f"{validation_stage} submissions must include {required[0]}")

    if not any(
        (
            normalized_answer_unit_ids,
            normalized_claim_ids,
            normalized_obligation_ids,
            normalized_consistency_ids,
            normalized_issue_ids,
        )
    ):
        raise ValueError("verifier submissions must reference answer_unit_ids, claim_ids, obligation_ids, consistency_result_ids, or issue_ids")

    for field_name, values in (
        ("answer_unit_ids", normalized_answer_unit_ids),
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
        normalized_answer_unit_ids,
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
    active_agent: str = ""
    handoff_envelope: dict[str, Any] = field(default_factory=dict)
    handoff_history: list[dict[str, Any]] = field(default_factory=list)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    source_candidates: list[SourceCandidate] = field(default_factory=list)
    fetched_documents: list[FetchedDocument] = field(default_factory=list)
    evidence_passages: list[EvidencePassage] = field(default_factory=list)
    evidence_cards: list[EvidenceCard] = field(default_factory=list)
    branch_synthesis: BranchSynthesis | None = None
    section_draft: ReportSectionDraft | None = None
    answer_units: list[AnswerUnit] = field(default_factory=list)
    claim_units: list[ClaimUnit] = field(default_factory=list)
    verification_results: list[VerificationResult] = field(default_factory=list)
    coordination_requests: list[CoordinationRequest] = field(default_factory=list)
    submissions: list[ResearchSubmission] = field(default_factory=list)
    final_report: FinalReportArtifact | None = None
    control_plane_result: dict[str, Any] = field(default_factory=dict)
    supervisor_decision: dict[str, Any] = field(default_factory=dict)
    plan_items: list[dict[str, Any]] = field(default_factory=list)
    searches_used: int = 0
    tokens_used: int = 0
    notes: list[str] = field(default_factory=list)
    role_kind: str = field(init=False)

    def __post_init__(self) -> None:
        self.role = str(self.role or "").strip().lower()
        self.role_kind = classify_deep_research_role(self.role)
        normalized_active_agent = str(self.active_agent or "").strip().lower()
        if self.role_kind == "control_plane":
            self.active_agent = validate_control_plane_agent(normalized_active_agent or self.role)
        else:
            self.active_agent = normalized_active_agent or "supervisor"
        self.handoff_envelope = dict(self.handoff_envelope or {})
        self.handoff_history = [
            dict(item)
            for item in self.handoff_history
            if isinstance(item, dict)
        ]
        self.control_plane_result = dict(self.control_plane_result or {})
        self.supervisor_decision = dict(self.supervisor_decision or {})
        self.plan_items = [
            dict(item)
            for item in self.plan_items
            if isinstance(item, dict)
        ]

    def ensure_capability(self, capability: str) -> None:
        if capability not in self.allowed_capabilities:
            raise RuntimeError(f"{self.role} role is not allowed to use capability: {capability}")

    def ensure_control_plane_owner(self) -> None:
        if self.role_kind != "control_plane":
            raise RuntimeError(f"{self.role} is not allowed to modify control-plane ownership")
        if self.active_agent != self.role:
            raise RuntimeError(f"only active control-plane owner '{self.active_agent}' may hand off ownership")

    def submit_control_plane_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.role_kind != "control_plane":
            raise RuntimeError(f"{self.role} is not a control-plane role")
        self.control_plane_result = dict(payload or {})
        return dict(self.control_plane_result)

    def submit_control_plane_handoff(
        self,
        *,
        to_agent: str,
        reason: str,
        context_refs: list[str] | None = None,
        scope_snapshot: dict[str, Any] | None = None,
        review_state: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ControlPlaneHandoff:
        self.ensure_control_plane_owner()
        normalized_to_agent = validate_control_plane_agent(to_agent)
        allowed_targets = _CONTROL_PLANE_HANDOFF_TARGETS.get(self.role, set())
        if allowed_targets and normalized_to_agent not in allowed_targets:
            allowed = ", ".join(sorted(allowed_targets))
            raise ValueError(f"{self.role} can only hand off to: {allowed}")
        handoff = ControlPlaneHandoff(
            id=support._new_id("handoff"),
            from_agent=validate_control_plane_agent(self.role),
            to_agent=normalized_to_agent,
            reason=str(reason or "").strip(),
            context_refs=[str(item).strip() for item in (context_refs or []) if str(item).strip()],
            scope_snapshot=dict(scope_snapshot or {}),
            review_state=str(review_state or "").strip(),
            created_by=self.role,
            metadata=dict(metadata or {}),
        )
        payload = handoff.to_dict()
        self.active_agent = handoff.to_agent
        self.handoff_envelope = payload
        self.handoff_history = [*self.handoff_history, payload][-20:]
        return handoff

    def submit_supervisor_decision(
        self,
        *,
        action: str,
        reasoning: str,
        priority_topics: list[str] | None = None,
        retry_task_ids: list[str] | None = None,
        request_ids: list[str] | None = None,
        issue_ids: list[str] | None = None,
        target_branch_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.role != "supervisor":
            raise RuntimeError("only supervisor may submit a supervisor decision")
        self.ensure_control_plane_owner()
        self.supervisor_decision = {
            "action": str(action or "").strip(),
            "reasoning": str(reasoning or "").strip(),
            "priority_topics": _normalize_ids(priority_topics),
            "retry_task_ids": _normalize_ids(retry_task_ids),
            "request_ids": _normalize_ids(request_ids),
            "issue_ids": _normalize_ids(issue_ids),
            "target_branch_ids": _normalize_ids(target_branch_ids),
        }
        return dict(self.supervisor_decision)

    def submit_plan_items(self, items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if self.role != "supervisor":
            raise RuntimeError("only supervisor may submit plan items")
        self.ensure_control_plane_owner()
        self.plan_items = [dict(item) for item in (items or []) if isinstance(item, dict)]
        return list(self.plan_items)

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
        answer_units: list[dict[str, Any]] | None = None,
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
        if self.task and self.branch_synthesis:
            if answer_units:
                self.branch_synthesis.metadata["answer_units"] = list(answer_units)
            self.answer_units = derive_answer_units(
                claim_verifier=self.runtime.claim_verifier,
                task=self.task,
                synthesis=self.branch_synthesis,
                created_by=self.role,
                existing_answer_units=self.answer_units,
                existing_claim_units=self.claim_units,
            )
            self.claim_units = [item.to_claim_unit() for item in self.answer_units]
        else:
            self.answer_units = []
            self.claim_units = []
        if self.branch_synthesis:
            self.branch_synthesis.answer_unit_ids = [item.id for item in self.answer_units]
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
                *[item.id for item in self.answer_units],
                *[item.id for item in self.claim_units],
                self.branch_synthesis.id,
                self.section_draft.id,
            ],
            answer_unit_ids=[item.id for item in self.answer_units],
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
        answer_unit_ids: list[str] | None = None,
        claim_ids: list[str] | None = None,
        obligation_ids: list[str] | None = None,
        consistency_result_ids: list[str] | None = None,
        issue_ids: list[str] | None = None,
    ) -> tuple[VerificationResult, ResearchSubmission]:
        (
            normalized_answer_unit_ids,
            normalized_claim_ids,
            normalized_obligation_ids,
            normalized_consistency_ids,
            normalized_issue_ids,
        ) = _validate_verifier_contract_submission(
            self,
            validation_stage=validation_stage,
            answer_unit_ids=answer_unit_ids,
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
                "answer_unit_ids": normalized_answer_unit_ids,
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
            answer_unit_ids=normalized_answer_unit_ids,
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
            "role_kind": session.role_kind,
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

    @tool
    def fabric_get_handoff_state() -> dict[str, Any]:
        """Return the authoritative control-plane owner and recent handoff context."""
        return {
            "role": session.role,
            "role_kind": session.role_kind,
            "active_agent": session.active_agent,
            "latest_handoff": dict(session.handoff_envelope),
            "handoff_history": list(session.handoff_history),
            "allowed_targets": sorted(_CONTROL_PLANE_HANDOFF_TARGETS.get(session.role, set())),
        }

    base_tools.extend(
        [
            fabric_get_scope,
            fabric_get_research_brief,
            fabric_get_task,
            fabric_get_related_artifacts,
            fabric_get_verification_contracts,
            fabric_get_control_plane,
            fabric_get_handoff_state,
        ]
    )

    if session.role_kind == "control_plane":
        @tool
        def fabric_submit_handoff(
            to_agent: str,
            reason: str,
            context_refs: list[str] | None = None,
            scope_snapshot: dict[str, Any] | None = None,
            review_state: str = "",
        ) -> dict[str, Any]:
            """Submit a structured control-plane handoff. Only the current active owner may call this tool."""
            handoff = session.submit_control_plane_handoff(
                to_agent=to_agent,
                reason=reason,
                context_refs=list(context_refs or []),
                scope_snapshot=dict(scope_snapshot or {}),
                review_state=review_state,
            )
            return handoff.to_dict()

        base_tools.append(fabric_submit_handoff)

    if session.role == "clarify":
        @tool
        def fabric_submit_intake_assessment(
            needs_clarification: bool,
            question: str = "",
            missing_information: list[str] | None = None,
            research_goal: str = "",
            background: str = "",
            constraints: list[str] | None = None,
            time_range: str = "",
            source_preferences: list[str] | None = None,
            exclusions: list[str] | None = None,
        ) -> dict[str, Any]:
            """Submit the normalized clarify result for the current intake step."""
            payload = {
                "needs_clarification": bool(needs_clarification),
                "question": str(question or "").strip(),
                "missing_information": _normalize_ids(missing_information),
                "intake_summary": {
                    "research_goal": str(research_goal or session.topic).strip() or session.topic,
                    "background": str(background or "").strip(),
                    "constraints": _normalize_ids(constraints),
                    "time_range": str(time_range or "").strip(),
                    "source_preferences": _normalize_ids(source_preferences),
                    "exclusions": _normalize_ids(exclusions),
                },
            }
            return session.submit_control_plane_result(payload)

        base_tools.append(fabric_submit_intake_assessment)

    if session.role == "scope":
        @tool
        def fabric_submit_scope_draft(
            research_goal: str,
            research_steps: list[str] | None = None,
            core_questions: list[str] | None = None,
            in_scope: list[str] | None = None,
            out_of_scope: list[str] | None = None,
            constraints: list[str] | None = None,
            source_preferences: list[str] | None = None,
            deliverable_preferences: list[str] | None = None,
            assumptions: list[str] | None = None,
        ) -> dict[str, Any]:
            """Submit the structured scope draft that will be shown for review."""
            payload = {
                "research_goal": str(research_goal or session.topic).strip() or session.topic,
                "research_steps": _normalize_ids(research_steps),
                "core_questions": _normalize_ids(core_questions),
                "in_scope": _normalize_ids(in_scope),
                "out_of_scope": _normalize_ids(out_of_scope),
                "constraints": _normalize_ids(constraints),
                "source_preferences": _normalize_ids(source_preferences),
                "deliverable_preferences": _normalize_ids(deliverable_preferences),
                "assumptions": _normalize_ids(assumptions),
            }
            return session.submit_control_plane_result(payload)

        base_tools.append(fabric_submit_scope_draft)

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

        @tool
        def fabric_submit_supervisor_decision(
            action: str,
            reasoning: str,
            priority_topics: list[str] | None = None,
            retry_task_ids: list[str] | None = None,
            request_ids: list[str] | None = None,
            issue_ids: list[str] | None = None,
            target_branch_ids: list[str] | None = None,
        ) -> dict[str, Any]:
            """Submit the supervisor's next structured control-plane decision."""
            return session.submit_supervisor_decision(
                action=action,
                reasoning=reasoning,
                priority_topics=list(priority_topics or []),
                retry_task_ids=list(retry_task_ids or []),
                request_ids=list(request_ids or []),
                issue_ids=list(issue_ids or []),
                target_branch_ids=list(target_branch_ids or []),
            )

        @tool
        def fabric_submit_plan_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """Submit the next plan or replan task candidates for supervisor-owned dispatch."""
            return session.submit_plan_items(items)

        base_tools.extend(
            [
                fabric_get_task_queue,
                fabric_get_open_requests,
                fabric_submit_supervisor_decision,
                fabric_submit_plan_items,
            ]
        )
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
            answer_units: list[dict[str, Any]] | None = None,
            result_status: str = "completed",
            resolved_issue_ids: list[str] | None = None,
        ) -> dict[str, Any]:
            """Submit the current branch research bundle using extracted evidence and a branch summary."""
            submission = session.submit_research_bundle(
                summary=summary,
                findings=list(findings or []),
                answer_units=list(answer_units or []),
                result_status=result_status,
                resolved_issue_ids=list(resolved_issue_ids or []),
            )
            return {
                "submission_id": submission.id,
                "branch_synthesis_id": session.branch_synthesis.id if session.branch_synthesis else "",
                "answer_unit_ids": [item.id for item in session.answer_units],
                "claim_ids": [item.id for item in session.claim_units],
                "result_status": submission.result_status,
            }

        base_tools.extend([fabric_request_follow_up, fabric_submit_research_bundle])

    if session.role == "verifier":
        @tool
        def fabric_list_answer_units() -> list[dict[str, Any]]:
            """Return the current branch answer units as the authoritative unit-level validation targets."""
            if session.answer_units:
                return [item.to_dict() for item in session.answer_units]
            related = session.related_artifacts.get("answer_units", [])
            if isinstance(related, list) and related:
                return [item for item in related if isinstance(item, dict)]
            return [
                {
                    "id": item.id,
                    "task_id": item.task_id,
                    "branch_id": item.branch_id,
                    "text": item.claim,
                    "unit_type": str(item.metadata.get("unit_type") or "claim"),
                    "obligation_ids": list(item.metadata.get("obligation_ids") or []),
                    "supporting_passage_ids": list(item.evidence_passage_ids),
                }
                for item in session.claim_units
            ]

        @tool
        def fabric_get_obligations() -> list[dict[str, Any]]:
            """Return the current branch coverage obligations for unit-to-obligation validation."""
            related = session.related_artifacts.get("coverage_obligations", [])
            return [item for item in related if isinstance(item, dict)] if isinstance(related, list) else []

        @tool
        def fabric_get_evidence_passages() -> list[dict[str, Any]]:
            """Return admissible evidence passages available to the current verifier session."""
            if session.evidence_passages:
                return [item.to_dict() for item in session.evidence_passages]
            related = session.related_artifacts.get("evidence_passages", [])
            return [item for item in related if isinstance(item, dict)] if isinstance(related, list) else []

        @tool
        def fabric_validate_unit(answer_unit_id: str) -> dict[str, Any]:
            """Validate a single answer unit against admissible evidence passages."""
            unit_id = str(answer_unit_id or "").strip()
            answer_unit = next((item for item in session.answer_units if item.id == unit_id), None)
            if answer_unit is None:
                related = (
                    [item.to_dict() for item in session.answer_units]
                    if session.answer_units
                    else [
                        item for item in session.related_artifacts.get("answer_units", [])
                        if isinstance(item, dict)
                    ]
                )
                payload = next(
                    (
                        item
                        for item in related
                        if isinstance(item, dict) and str(item.get("id") or "").strip() == unit_id
                    ),
                    None,
                )
                if payload is None:
                    raise RuntimeError(f"unknown answer unit id: {unit_id}")
                answer_unit = AnswerUnit(
                    id=unit_id,
                    task_id=str(payload.get("task_id") or session.task.id if session.task else ""),
                    branch_id=payload.get("branch_id") or session.branch_id,
                    text=str(payload.get("text") or payload.get("claim") or "").strip(),
                    unit_type=str(payload.get("unit_type") or "claim"),
                    provenance=dict(payload.get("provenance") or {}),
                    supporting_passage_ids=_normalize_ids(
                        list(payload.get("supporting_passage_ids") or payload.get("evidence_passage_ids") or [])
                    ),
                    citation_urls=_normalize_ids(list(payload.get("citation_urls") or [])),
                    obligation_ids=_normalize_ids(list(payload.get("obligation_ids") or [])),
                    dependent_answer_unit_ids=_normalize_ids(list(payload.get("dependent_answer_unit_ids") or [])),
                    required=bool(payload.get("required", True)),
                    metadata=dict(payload.get("metadata") or {}),
                )
            results = ground_claim_units(
                claim_verifier=session.runtime.claim_verifier,
                claim_units=[],
                answer_units=[answer_unit],
                passages=(
                    [item.to_dict() for item in session.evidence_passages]
                    if session.evidence_passages
                    else [
                        item for item in session.related_artifacts.get("evidence_passages", [])
                        if isinstance(item, dict)
                    ]
                ),
                created_by=session.role,
            )
            result = results[0]
            return {
                "answer_unit_id": answer_unit.id,
                "status": result.status,
                "summary": result.summary,
                "evidence_urls": list(result.evidence_urls),
                "evidence_passage_ids": list(result.evidence_passage_ids),
            }

        @tool
        def fabric_validate_obligation(obligation_id: str) -> dict[str, Any]:
            """Validate a single obligation using mapped, grounded answer units."""
            from agent.runtime.deep.schema import CoverageObligation

            normalized_obligation_id = str(obligation_id or "").strip()
            obligation_payload = next(
                (
                    item
                    for item in (
                        [
                            item
                            for item in session.related_artifacts.get("coverage_obligations", [])
                            if isinstance(item, dict)
                        ]
                    )
                    if str(item.get("id") or "").strip() == normalized_obligation_id
                ),
                None,
            )
            if obligation_payload is None:
                raise RuntimeError(f"unknown obligation id: {obligation_id}")
            resolved = next(
                (
                    item
                    for item in session.runtime.artifact_store.coverage_obligations(task_id=session.task.id)
                    if item.id == normalized_obligation_id
                ),
                None,
            )
            if resolved is None:
                resolved = CoverageObligation(**obligation_payload)
            units = session.answer_units or [
                AnswerUnit(
                    id=str(item.get("id") or "").strip(),
                    task_id=str(item.get("task_id") or session.task.id if session.task else ""),
                    branch_id=item.get("branch_id") or session.branch_id,
                    text=str(item.get("text") or item.get("claim") or "").strip(),
                    unit_type=str(item.get("unit_type") or "claim"),
                    provenance=dict(item.get("provenance") or {}),
                    supporting_passage_ids=_normalize_ids(
                        list(item.get("supporting_passage_ids") or item.get("evidence_passage_ids") or [])
                    ),
                    citation_urls=_normalize_ids(list(item.get("citation_urls") or [])),
                    obligation_ids=_normalize_ids(list(item.get("obligation_ids") or [])),
                    dependent_answer_unit_ids=_normalize_ids(list(item.get("dependent_answer_unit_ids") or [])),
                    required=bool(item.get("required", True)),
                    metadata=dict(item.get("metadata") or {}),
                )
                for item in (
                    [item.to_dict() for item in session.answer_units]
                    if session.answer_units
                    else [
                        item for item in session.related_artifacts.get("answer_units", [])
                        if isinstance(item, dict)
                    ]
                )
                if isinstance(item, dict)
            ]
            groundings = ground_claim_units(
                claim_verifier=session.runtime.claim_verifier,
                claim_units=[],
                answer_units=units,
                passages=(
                    [item.to_dict() for item in session.evidence_passages]
                    if session.evidence_passages
                    else [
                        item for item in session.related_artifacts.get("evidence_passages", [])
                        if isinstance(item, dict)
                    ]
                ),
                created_by=session.role,
            )
            result = evaluate_obligations(
                task=session.task,
                synthesis=session.branch_synthesis or BranchSynthesis(
                    id="",
                    task_id=session.task.id if session.task else "",
                    branch_id=session.branch_id,
                    objective=session.task.objective if session.task else session.topic,
                    summary=session.branch_synthesis.summary if session.branch_synthesis else "",
                ),
                obligations=[resolved],
                claim_units=[item.to_claim_unit() for item in units],
                answer_units=units,
                grounding_results=groundings,
                created_by=session.role,
            )[0]
            return {
                "obligation_id": resolved.id,
                "status": result.status,
                "summary": result.summary,
                "evidence_urls": list(result.evidence_urls),
                "evidence_passage_ids": list(result.evidence_passage_ids),
                "supported_answer_unit_ids": list(result.metadata.get("supported_answer_unit_ids", [])),
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
            answer_unit_ids: list[str] | None = None,
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
                answer_unit_ids=list(answer_unit_ids or []),
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
                fabric_list_answer_units,
                fabric_get_obligations,
                fabric_get_evidence_passages,
                fabric_validate_unit,
                fabric_validate_obligation,
                fabric_analyze_coverage,
                fabric_submit_verification_bundle,
            ]
        )

    if session.role == "reporter":
        @tool
        def fabric_get_verified_branch_summaries() -> list[dict[str, Any]]:
            """Return only branch syntheses that are ready for report per canonical branch validation summaries."""
            latest_syntheses = latest_branch_syntheses(
                session.runtime.artifact_store.branch_syntheses(),
                session.runtime.artifact_store.branch_briefs(),
            )
            validation_summary_by_task: dict[str, dict[str, Any]] = {}
            for summary in sorted(
                session.runtime.artifact_store.branch_validation_summaries(),
                key=lambda item: (item.created_at, item.id),
            ):
                if summary.task_id:
                    validation_summary_by_task[summary.task_id] = summary.to_dict()
            items: list[dict[str, Any]] = []
            for synthesis in latest_syntheses:
                summary = validation_summary_by_task.get(synthesis.task_id)
                if not summary or not summary.get("ready_for_report") or summary.get("blocking"):
                    continue
                payload = synthesis.to_dict()
                payload["branch_validation_summary"] = summary
                payload["answer_unit_ids"] = list(summary.get("answer_unit_ids") or [])
                payload["issue_ids"] = list(summary.get("issue_ids") or [])
                items.append(payload)
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
    if session.role == "clarify" and not session.control_plane_result:
        intake_summary = payload.get("intake_summary") if isinstance(payload.get("intake_summary"), dict) else {}
        if intake_summary or "needs_clarification" in payload:
            session.submit_control_plane_result(
                {
                    "needs_clarification": bool(payload.get("needs_clarification")),
                    "question": str(payload.get("question") or "").strip(),
                    "missing_information": _normalize_ids(payload.get("missing_information")),
                    "intake_summary": {
                        "research_goal": str(intake_summary.get("research_goal") or session.topic).strip()
                        or session.topic,
                        "background": str(intake_summary.get("background") or "").strip(),
                        "constraints": _normalize_ids(intake_summary.get("constraints")),
                        "time_range": str(intake_summary.get("time_range") or "").strip(),
                        "source_preferences": _normalize_ids(intake_summary.get("source_preferences")),
                        "exclusions": _normalize_ids(intake_summary.get("exclusions")),
                    },
                }
            )
    elif session.role == "scope" and not session.control_plane_result:
        if any(
            key in payload
            for key in (
                "research_goal",
                "research_steps",
                "core_questions",
                "in_scope",
                "out_of_scope",
            )
        ):
            session.submit_control_plane_result(
                {
                    "research_goal": str(payload.get("research_goal") or session.topic).strip() or session.topic,
                    "research_steps": _normalize_ids(payload.get("research_steps")),
                    "core_questions": _normalize_ids(payload.get("core_questions")),
                    "in_scope": _normalize_ids(payload.get("in_scope")),
                    "out_of_scope": _normalize_ids(payload.get("out_of_scope")),
                    "constraints": _normalize_ids(payload.get("constraints")),
                    "source_preferences": _normalize_ids(payload.get("source_preferences")),
                    "deliverable_preferences": _normalize_ids(payload.get("deliverable_preferences")),
                    "assumptions": _normalize_ids(payload.get("assumptions")),
                }
            )
    elif session.role == "supervisor":
        if not session.plan_items and isinstance(payload.get("plan_items"), list):
            session.submit_plan_items(payload.get("plan_items"))
        if not session.supervisor_decision:
            action = str(payload.get("action") or payload.get("decision_type") or "").strip()
            reasoning = str(payload.get("reasoning") or payload.get("summary") or "").strip()
            if action and reasoning:
                session.submit_supervisor_decision(
                    action=action,
                    reasoning=reasoning,
                    priority_topics=_normalize_ids(payload.get("priority_topics")),
                    retry_task_ids=_normalize_ids(payload.get("retry_task_ids")),
                    request_ids=_normalize_ids(payload.get("request_ids")),
                    issue_ids=_normalize_ids(payload.get("issue_ids")),
                    target_branch_ids=_normalize_ids(payload.get("target_branch_ids")),
                )
    elif session.role == "researcher" and not session.submissions:
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
                answer_unit_ids=(
                    [item.id for item in session.answer_units]
                    if validation_stage == "claim_check"
                    else None
                ),
                claim_ids=list(payload.get("claim_ids") or []),
                obligation_ids=list(payload.get("obligation_ids") or []),
                consistency_result_ids=list(payload.get("consistency_result_ids") or []),
                issue_ids=list(payload.get("issue_ids") or []),
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
    if (
        session.role_kind == "control_plane"
        and not session.handoff_envelope
        and payload.get("to_agent")
        and payload.get("reason")
    ):
        try:
            session.submit_control_plane_handoff(
                to_agent=str(payload.get("to_agent") or "").strip(),
                reason=str(payload.get("reason") or "").strip(),
                context_refs=_normalize_ids(payload.get("context_refs")),
                scope_snapshot=(
                    dict(payload.get("scope_snapshot"))
                    if isinstance(payload.get("scope_snapshot"), dict)
                    else {}
                ),
                review_state=str(payload.get("review_state") or "").strip(),
                metadata=dict(payload.get("metadata") or {}),
            )
        except Exception:
            return


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
