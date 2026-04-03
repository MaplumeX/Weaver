"""
LangGraph-backed multi-agent Deep Research runtime.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Send, interrupt

from agent.contracts.events import get_emitter_sync
from agent.core.llm_factory import create_chat_model
from agent.core.context import (
    ResearchWorkerContext,
    build_research_worker_context,
    merge_research_worker_context,
)
from agent.core.state import build_deep_runtime_snapshot
from agent.runtime.deep.config import resolve_max_searches, resolve_parallel_workers
from agent.runtime.deep.state import read_deep_runtime_snapshot
import agent.runtime.deep.orchestration.dispatcher as dispatcher
import agent.runtime.deep.orchestration.events as events
from agent.runtime.deep.artifacts.public_artifacts import build_public_deep_research_artifacts
from agent.runtime.deep.schema import (
    AgentRunRecord,
    BranchBrief,
    BranchRevisionBrief,
    BranchSynthesis,
    ClaimGroundingResult,
    ClaimUnit,
    ConsistencyResult,
    ContradictionRegistryArtifact,
    CoordinationRequest,
    CoverageMatrixArtifact,
    CoverageEvaluationResult,
    CoverageObligation,
    EvidenceCard,
    EvidencePassage,
    FetchedDocument,
    FinalReportArtifact,
    GraphScopeSnapshot,
    KnowledgeGap,
    MissingEvidenceListArtifact,
    OutlineArtifact,
    ProgressLedgerArtifact,
    ReportSectionDraft,
    ResearchBriefArtifact,
    ResearchSubmission,
    ResearchTask,
    RevisionIssue,
    SourceCandidate,
    ScopeDraft,
    SupervisorDecisionArtifact,
    TaskLedgerArtifact,
    VerificationResult,
    WorkerExecutionResult,
    WorkerScopeSnapshot,
    _now_iso,
)
from agent.runtime.deep.store import ArtifactStore, ResearchTaskQueue
from agent.runtime.deep.support.tool_agents import (
    DeepResearchToolAgentSession,
    run_bounded_tool_agent,
)
import agent.runtime.deep.support.runtime_support as support
from agent.runtime.deep.support.graph_helpers import (
    MultiAgentGraphState,
    build_clarify_transcript as _build_clarify_transcript,
    build_scope_draft as _build_scope_draft,
    coerce_string_list as _coerce_string_list,
    criterion_is_covered as _criterion_is_covered,
    derive_branch_queries as _derive_branch_queries,
    derive_role_counters as _derive_role_counters,
    extract_interrupt_text as _extract_interrupt_text,
    format_scope_draft_markdown as _format_scope_draft_markdown,
    gap_result_from_payload as _gap_result_from_payload,
    restore_agent_runs as _restore_agent_runs,
    restore_worker_result as _restore_worker_result,
    scope_draft_from_payload as _scope_draft_from_payload,
    scope_version as _scope_version,
    split_findings as _split_findings,
)
from agent.contracts.claim_verifier import ClaimStatus, ClaimVerifier
from agent.research.source_url_utils import canonicalize_source_url
from agent.runtime.deep.roles.clarify import DeepResearchClarifyAgent
from agent.runtime.deep.roles.reporter import (
    ReportContext,
    ReportSectionContext,
    ReportSource,
    ResearchReporter,
)
from agent.runtime.deep.roles.researcher import ResearchAgent
from agent.runtime.deep.roles.scope import DeepResearchScopeAgent
from agent.runtime.deep.roles.supervisor import (
    ResearchSupervisor,
    SupervisorAction,
    SupervisorDecision,
)
from agent.runtime.deep.services.knowledge_gap import GapAnalysisResult
from agent.runtime.deep.services.knowledge_gap import KnowledgeGapAnalyzer
from agent.runtime.deep.services.verification import (
    aggregate_revision_issues,
    build_gap_result,
    derive_claim_units,
    derive_coverage_obligations,
    evaluate_consistency,
    evaluate_obligations,
    ground_claim_units,
    latest_branch_syntheses,
    summarize_issue_statuses,
    summarize_revision_lineage,
)
from common.cancellation import check_cancellation as _check_cancel_token
from common.config import settings

logger = logging.getLogger(__name__)


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


def _dedupe_texts(values: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values or []:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _merge_report_source(
    catalog: dict[str, ReportSource],
    *,
    url: Any,
    title: Any = "",
    provider: Any = "",
    published_date: Any = None,
) -> None:
    normalized_url = canonicalize_source_url(url)
    if not normalized_url:
        return
    normalized_title = str(title or "").strip() or normalized_url
    normalized_provider = str(provider or "").strip()
    normalized_published_date = str(published_date).strip() if published_date else None
    existing = catalog.get(normalized_url)
    if existing is None:
        catalog[normalized_url] = ReportSource(
            url=normalized_url,
            title=normalized_title,
            provider=normalized_provider,
            published_date=normalized_published_date,
        )
        return
    if (not existing.title or existing.title == existing.url) and normalized_title:
        existing.title = normalized_title
    if not existing.provider and normalized_provider:
        existing.provider = normalized_provider
    if not existing.published_date and normalized_published_date:
        existing.published_date = normalized_published_date


def _build_report_source_catalog(view: "_RuntimeView") -> dict[str, ReportSource]:
    catalog: dict[str, ReportSource] = {}
    for item in view.artifact_store.evidence_cards():
        _merge_report_source(
            catalog,
            url=item.source_url,
            title=item.source_title,
            provider=item.source_provider,
            published_date=item.published_date,
        )
    for item in view.artifact_store.fetched_documents():
        _merge_report_source(
            catalog,
            url=item.url,
            title=item.title,
        )
    for item in view.artifact_store.source_candidates():
        _merge_report_source(
            catalog,
            url=item.url,
            title=item.title,
            provider=item.source_provider,
            published_date=item.published_date,
        )
    return catalog


def _resolve_report_sources(
    ordered_urls: list[str],
    *,
    source_catalog: dict[str, ReportSource],
) -> list[ReportSource]:
    sources: list[ReportSource] = []
    seen: set[str] = set()
    for raw_url in ordered_urls:
        url = canonicalize_source_url(raw_url)
        if not url or url in seen:
            continue
        seen.add(url)
        source = source_catalog.get(url)
        if source is None:
            source = ReportSource(url=url, title=url)
        else:
            source = copy.deepcopy(source)
        sources.append(source)
    return sources


def _match_outline_section_syntheses(
    section: dict[str, Any],
    verified_syntheses: list[BranchSynthesis],
) -> list[BranchSynthesis]:
    artifact_ids = {str(item).strip() for item in section.get("artifact_ids", []) if str(item).strip()}
    task_ids = {str(item).strip() for item in section.get("task_ids", []) if str(item).strip()}
    branch_ids = {str(item).strip() for item in section.get("branch_ids", []) if str(item).strip()}
    matched: list[BranchSynthesis] = []
    for synthesis in verified_syntheses:
        if (
            synthesis.id in artifact_ids
            or synthesis.task_id in task_ids
            or (synthesis.branch_id and synthesis.branch_id in branch_ids)
        ):
            matched.append(synthesis)
    return matched


def _build_report_context(
    *,
    topic: str,
    outline_artifact: OutlineArtifact,
    verified_syntheses: list[BranchSynthesis],
    source_catalog: dict[str, ReportSource],
) -> ReportContext:
    sections: list[ReportSectionContext] = []
    ordered_urls: list[str] = []
    for raw_section in outline_artifact.sections:
        if not isinstance(raw_section, dict):
            continue
        matched_syntheses = _match_outline_section_syntheses(raw_section, verified_syntheses)
        branch_summaries = _dedupe_texts(
            [
                f"{item.objective or item.branch_id or '研究分支'}: {item.summary}"
                for item in matched_syntheses
                if item.summary
            ]
        )
        findings = _dedupe_texts(
            [
                finding
                for item in matched_syntheses
                for finding in item.findings
                if finding
            ]
        )
        citation_urls = _dedupe_texts(
            list(raw_section.get("citation_urls") or [])
            + [url for item in matched_syntheses for url in item.citation_urls if url]
        )
        ordered_urls.extend(citation_urls)
        sections.append(
            ReportSectionContext(
                title=str(raw_section.get("title") or "").strip() or "核心发现",
                summary=str(raw_section.get("summary") or "").strip() or "\n".join(branch_summaries[:2]),
                branch_summaries=branch_summaries,
                findings=findings,
                citation_urls=citation_urls,
            )
        )

    if not sections:
        for synthesis in verified_syntheses:
            ordered_urls.extend(synthesis.citation_urls)
            sections.append(
                ReportSectionContext(
                    title=synthesis.objective or synthesis.branch_id or "研究结论",
                    summary=synthesis.summary,
                    branch_summaries=[synthesis.summary] if synthesis.summary else [],
                    findings=_dedupe_texts(list(synthesis.findings)),
                    citation_urls=_dedupe_texts(list(synthesis.citation_urls)),
                )
            )

    if not ordered_urls:
        ordered_urls = _dedupe_texts(
            [url for synthesis in verified_syntheses for url in synthesis.citation_urls if url]
        )

    return ReportContext(
        topic=topic,
        sections=sections,
        sources=_resolve_report_sources(ordered_urls, source_catalog=source_catalog),
    )


def _append_shared_error(shared_state: dict[str, Any], message: str) -> None:
    reason = str(message or "").strip()
    if not reason:
        return
    existing = shared_state.get("errors")
    if not isinstance(existing, list):
        existing = []
        shared_state["errors"] = existing
    if reason not in existing:
        existing.append(reason)


def _tool_contract_ids(
    result: VerificationResult | None,
    submission: ResearchSubmission | None,
    field_name: str,
) -> list[str]:
    values: list[str] = []
    if submission is not None:
        values.extend(getattr(submission, field_name, []) or [])
    metadata = result.metadata if result is not None and isinstance(result.metadata, dict) else {}
    values.extend(metadata.get(field_name, []) or [])
    return _dedupe_texts(values)


def _tool_result_evidence_urls(
    result: VerificationResult,
    fallback_urls: list[str] | None = None,
) -> list[str]:
    return _dedupe_texts(list(result.evidence_urls) + list(fallback_urls or []))


def _tool_result_evidence_passage_ids(
    result: VerificationResult,
    fallback_passage_ids: list[str] | None = None,
) -> list[str]:
    return _dedupe_texts(list(result.evidence_passage_ids) + list(fallback_passage_ids or []))


def _merge_tool_claim_groundings(
    *,
    claim_units: list[ClaimUnit],
    claim_groundings: list[ClaimGroundingResult],
    tool_result: VerificationResult | None,
    tool_submission: ResearchSubmission | None,
    fallback_urls: list[str] | None = None,
    fallback_passage_ids: list[str] | None = None,
) -> list[ClaimGroundingResult]:
    if tool_result is None or tool_submission is None:
        return claim_groundings

    addressed_claim_ids = _tool_contract_ids(tool_result, tool_submission, "claim_ids")
    if not addressed_claim_ids:
        return claim_groundings

    status_map = {
        "passed": ("grounded", "low"),
        "failed": ("contradicted", "high"),
        "needs_follow_up": ("unsupported", "medium"),
    }
    mapped = status_map.get(tool_result.outcome)
    if mapped is None:
        return claim_groundings

    status, severity = mapped
    evidence_urls = _tool_result_evidence_urls(tool_result, fallback_urls)
    evidence_passage_ids = _tool_result_evidence_passage_ids(tool_result, fallback_passage_ids)
    existing_by_claim = {item.claim_id: item for item in claim_groundings}
    claim_by_id = {item.id: item for item in claim_units}
    merged: list[ClaimGroundingResult] = []

    for claim_unit in claim_units:
        existing = existing_by_claim.get(claim_unit.id)
        if claim_unit.id not in addressed_claim_ids:
            if existing is not None:
                merged.append(existing)
            continue
        merged.append(
            ClaimGroundingResult(
                id=support._new_id("claim_grounding"),
                task_id=claim_unit.task_id,
                branch_id=claim_unit.branch_id,
                claim_id=claim_unit.id,
                status=status,
                summary=tool_result.summary or f"{status} via verifier tool-agent: {claim_unit.claim}",
                evidence_urls=list(evidence_urls),
                evidence_passage_ids=list(evidence_passage_ids),
                severity=severity,
                created_by=tool_result.created_by or (existing.created_by if existing else "verifier"),
                metadata={
                    **(existing.metadata if existing else {}),
                    "claim": claim_unit.claim,
                    "verified_by_tool_agent": True,
                    "tool_verification_id": tool_result.id,
                    "tool_submission_id": tool_submission.id,
                },
            )
        )

    for claim_id in addressed_claim_ids:
        if claim_id in existing_by_claim or claim_id not in claim_by_id:
            continue
        claim_unit = claim_by_id[claim_id]
        merged.append(
            ClaimGroundingResult(
                id=support._new_id("claim_grounding"),
                task_id=claim_unit.task_id,
                branch_id=claim_unit.branch_id,
                claim_id=claim_unit.id,
                status=status,
                summary=tool_result.summary or f"{status} via verifier tool-agent: {claim_unit.claim}",
                evidence_urls=list(evidence_urls),
                evidence_passage_ids=list(evidence_passage_ids),
                severity=severity,
                created_by=tool_result.created_by or "verifier",
                metadata={
                    "claim": claim_unit.claim,
                    "verified_by_tool_agent": True,
                    "tool_verification_id": tool_result.id,
                    "tool_submission_id": tool_submission.id,
                },
            )
        )

    return merged


def _merge_tool_coverage_results(
    *,
    obligations: list[CoverageObligation],
    coverage_results: list[CoverageEvaluationResult],
    tool_result: VerificationResult | None,
    tool_submission: ResearchSubmission | None,
    fallback_urls: list[str] | None = None,
    fallback_passage_ids: list[str] | None = None,
) -> list[CoverageEvaluationResult]:
    if tool_result is None or tool_submission is None:
        return coverage_results

    addressed_obligation_ids = _tool_contract_ids(tool_result, tool_submission, "obligation_ids")
    if not addressed_obligation_ids:
        return coverage_results

    status_map = {
        "passed": "satisfied",
        "failed": "unsatisfied",
        "needs_follow_up": "partially_satisfied",
    }
    merged_status = status_map.get(tool_result.outcome)
    if merged_status is None:
        return coverage_results

    evidence_urls = _tool_result_evidence_urls(tool_result, fallback_urls)
    evidence_passage_ids = _tool_result_evidence_passage_ids(tool_result, fallback_passage_ids)
    existing_by_obligation = {item.obligation_id: item for item in coverage_results}
    obligation_by_id = {item.id: item for item in obligations}
    merged: list[CoverageEvaluationResult] = []

    for obligation in obligations:
        existing = existing_by_obligation.get(obligation.id)
        if obligation.id not in addressed_obligation_ids:
            if existing is not None:
                merged.append(existing)
            continue
        criteria = _dedupe_texts(obligation.completion_criteria or [obligation.target])
        if merged_status == "satisfied":
            covered_criteria = list(criteria)
        elif merged_status == "partially_satisfied":
            covered_criteria = list(existing.metadata.get("covered_criteria", []) if existing else [])
            if not covered_criteria and criteria:
                covered_criteria = [criteria[0]]
        else:
            covered_criteria = []
        missing_criteria = [criterion for criterion in criteria if criterion not in covered_criteria]
        merged.append(
            CoverageEvaluationResult(
                id=support._new_id("coverage_eval"),
                task_id=obligation.task_id,
                branch_id=obligation.branch_id,
                obligation_id=obligation.id,
                status=merged_status,
                summary=tool_result.summary or f"{merged_status} via verifier tool-agent: {obligation.target}",
                evidence_urls=list(evidence_urls),
                evidence_passage_ids=list(evidence_passage_ids),
                created_by=tool_result.created_by or (existing.created_by if existing else "verifier"),
                metadata={
                    **(existing.metadata if existing else {}),
                    "covered_criteria": covered_criteria,
                    "missing_criteria": missing_criteria,
                    "target": obligation.target,
                    "verified_by_tool_agent": True,
                    "tool_verification_id": tool_result.id,
                    "tool_submission_id": tool_submission.id,
                    "used_synthesis_summary_as_authority": False,
                },
            )
        )

    return merged


def _coverage_dimensions_from_brief(brief: ResearchBriefArtifact | dict[str, Any] | None) -> list[str]:
    if not brief:
        return []
    payload = brief.to_dict() if hasattr(brief, "to_dict") else brief
    if not isinstance(payload, dict):
        return []
    return _dedupe_texts(
        list(payload.get("coverage_dimensions") or [])
        + list(payload.get("core_questions") or [])
        + list(payload.get("acceptance_criteria") or [])
    )


def _build_research_brief(
    *,
    topic: str,
    approved_scope: dict[str, Any],
    intake_summary: dict[str, Any],
    existing_id: str | None = None,
) -> ResearchBriefArtifact:
    coverage_dimensions = _dedupe_texts(
        list(approved_scope.get("core_questions") or [])
        + list(approved_scope.get("in_scope") or [])
        + list(approved_scope.get("research_steps") or [])[:3]
    )
    deliverable_constraints = _dedupe_texts(
        list(approved_scope.get("constraints") or [])
        + list(approved_scope.get("deliverable_preferences") or [])
    )
    time_boundary = str(
        intake_summary.get("time_range")
        or intake_summary.get("time_boundary")
        or approved_scope.get("time_range")
        or ""
    ).strip()
    return ResearchBriefArtifact(
        id=existing_id or support._new_id("research_brief"),
        scope_id=str(approved_scope.get("id") or support._new_id("scope")),
        scope_version=max(1, int(approved_scope.get("version", 1) or 1)),
        topic=topic,
        user_goal=str(
            intake_summary.get("research_goal") or approved_scope.get("research_goal") or topic
        ).strip()
        or topic,
        research_goal=str(approved_scope.get("research_goal") or topic).strip() or topic,
        core_questions=_dedupe_texts(approved_scope.get("core_questions")),
        coverage_dimensions=coverage_dimensions,
        in_scope=_dedupe_texts(approved_scope.get("in_scope")),
        out_of_scope=_dedupe_texts(approved_scope.get("out_of_scope")),
        deliverable_constraints=deliverable_constraints,
        source_preferences=_dedupe_texts(
            approved_scope.get("source_preferences") or intake_summary.get("source_preferences")
        ),
        time_boundary=time_boundary,
        acceptance_criteria=coverage_dimensions
        or _dedupe_texts(approved_scope.get("core_questions"))
        or [str(approved_scope.get("research_goal") or topic).strip() or topic],
        metadata={
            "approved_scope_snapshot": copy.deepcopy(approved_scope),
            "intake_summary": copy.deepcopy(intake_summary),
        },
    )


def _build_task_ledger_entries(
    tasks: list[ResearchTask],
    requests: list[CoordinationRequest],
    revision_issues: list[RevisionIssue] | None = None,
) -> list[dict[str, Any]]:
    task_requests: dict[str, list[CoordinationRequest]] = {}
    branch_requests: dict[str, list[CoordinationRequest]] = {}
    issues_by_task: dict[str, list[RevisionIssue]] = {}
    issues_by_branch: dict[str, list[RevisionIssue]] = {}
    for request in requests:
        if request.task_id:
            task_requests.setdefault(request.task_id, []).append(request)
        if request.branch_id:
            branch_requests.setdefault(request.branch_id, []).append(request)
    for issue in revision_issues or []:
        if issue.task_id:
            issues_by_task.setdefault(issue.task_id, []).append(issue)
        if issue.branch_id:
            issues_by_branch.setdefault(issue.branch_id, []).append(issue)
    entries: list[dict[str, Any]] = []
    for task in sorted(tasks, key=lambda item: (item.priority, item.created_at, item.id)):
        related_requests = task_requests.get(task.id, []) + branch_requests.get(task.branch_id or "", [])
        related_issues = issues_by_task.get(task.id, []) + issues_by_branch.get(task.branch_id or "", [])
        open_issue_ids = [
            issue.id
            for issue in related_issues
            if issue.status in {"open", "accepted"}
        ]
        resolved_issue_ids = [
            issue.id
            for issue in related_issues
            if issue.status == "resolved"
        ]
        entries.append(
            {
                "task_id": task.id,
                "branch_id": task.branch_id,
                "title": task.title or task.goal,
                "objective": task.objective,
                "task_kind": task.task_kind,
                "revision_kind": task.revision_kind,
                "revision_of_task_id": task.revision_of_task_id,
                "revision_brief_id": task.revision_brief_id,
                "priority": task.priority,
                "status": task.status,
                "stage": task.stage,
                "coverage_targets": list(task.acceptance_criteria or [task.objective or task.goal]),
                "request_ids": [request.id for request in related_requests if request.status == "open"],
                "request_types": [
                    request.request_type for request in related_requests if request.status == "open"
                ],
                "input_artifact_ids": list(task.input_artifact_ids),
                "target_issue_ids": list(dict.fromkeys(task.target_issue_ids + open_issue_ids)),
                "resolved_issue_ids": list(dict.fromkeys(task.resolved_issue_ids + resolved_issue_ids)),
                "last_error": task.last_error,
                "attempts": task.attempts,
                "updated_at": task.updated_at,
            }
        )
    return entries


def _build_progress_blockers(
    requests: list[CoordinationRequest],
    revision_issues: list[RevisionIssue] | None = None,
    *,
    budget_stop_reason: str | None = None,
) -> list[dict[str, Any]]:
    blockers = [
        {
            "request_id": request.id,
            "request_type": request.request_type,
            "summary": request.summary,
            "impact_scope": request.impact_scope,
            "blocking_level": request.blocking_level,
            "reason": request.reason,
            "issue_ids": list(request.issue_ids),
        }
        for request in requests
        if request.status == "open"
    ]
    blockers.extend(
        {
            "request_id": "",
            "request_type": "revision_issue",
            "summary": issue.summary,
            "impact_scope": str(issue.branch_id or issue.task_id or ""),
            "blocking_level": "blocking" if issue.blocking else "non_blocking",
            "reason": issue.issue_type,
            "issue_ids": [issue.id],
        }
        for issue in (revision_issues or [])
        if issue.status in {"open", "accepted"}
    )
    if budget_stop_reason:
        blockers.append(
            {
                "request_id": "",
                "request_type": "blocked_by_tooling",
                "summary": budget_stop_reason,
                "impact_scope": "runtime_budget",
                "blocking_level": "blocking",
                "reason": budget_stop_reason,
                "issue_ids": [],
            }
        )
    return blockers


def _build_coverage_matrix_artifact(
    *,
    view: "_RuntimeView",
    research_brief: ResearchBriefArtifact | None,
    obligations: list[CoverageObligation],
    coverage_results: list[CoverageEvaluationResult],
    revision_issues: list[RevisionIssue],
    syntheses: list[BranchSynthesis],
) -> CoverageMatrixArtifact:
    coverage_by_obligation = {result.obligation_id: result for result in coverage_results}
    rows: list[dict[str, Any]] = []
    for obligation in obligations:
        evaluation = coverage_by_obligation.get(obligation.id)
        matched_syntheses = [
            synthesis
            for synthesis in syntheses
            if synthesis.task_id == obligation.task_id or synthesis.branch_id == obligation.branch_id
        ]
        related_issues = [
            issue
            for issue in revision_issues
            if obligation.id in issue.obligation_ids and issue.status in {"open", "accepted"}
        ]
        related_issue_ids = [issue.id for issue in related_issues]
        blocking_issue_ids = [issue.id for issue in related_issues if issue.blocking]
        status = "gap"
        if evaluation:
            if evaluation.status == "satisfied":
                status = "covered"
            elif evaluation.status == "partially_satisfied":
                status = "partial"
            elif evaluation.status == "unresolved":
                status = "unresolved"
        rows.append(
            {
                "dimension": obligation.target,
                "status": status,
                "branch_ids": [synthesis.branch_id for synthesis in matched_syntheses if synthesis.branch_id],
                "task_ids": [synthesis.task_id for synthesis in matched_syntheses],
                "artifact_ids": [synthesis.id for synthesis in matched_syntheses],
                "gap_ids": related_issue_ids,
                "issue_ids": related_issue_ids,
                "blocking_issue_ids": blocking_issue_ids,
                "blocking": bool(blocking_issue_ids),
                "obligation_id": obligation.id,
                "source": obligation.source,
            }
        )

    covered_count = sum(1 for row in rows if row["status"] == "covered")
    overall_coverage = covered_count / len(rows) if rows else 0.0
    existing = view.artifact_store.coverage_matrix()
    return CoverageMatrixArtifact(
        id=existing.id if existing else support._new_id("coverage_matrix"),
        research_brief_id=research_brief.id if research_brief else None,
        rows=rows,
        overall_coverage=overall_coverage,
        status="completed",
        metadata={"dimension_count": len(rows), "issue_count": len(revision_issues)},
    )


def _build_contradiction_registry_artifact(
    *,
    view: "_RuntimeView",
    research_brief: ResearchBriefArtifact | None,
    grounding_results: list[ClaimGroundingResult],
    consistency_results: list[ConsistencyResult],
) -> ContradictionRegistryArtifact:
    entries: list[dict[str, Any]] = []
    for result in grounding_results:
        if result.status != "contradicted":
            continue
        entries.append(
            {
                "task_id": result.task_id,
                "branch_id": result.branch_id,
                "claim_id": result.claim_id,
                "claim": str(result.metadata.get("claim") or "").strip(),
                "evidence_urls": list(result.evidence_urls),
                "notes": result.summary,
                "verification_id": result.id,
            }
        )
    for result in consistency_results:
        if result.status != "contradicted":
            continue
        entries.append(
            {
                "task_id": result.task_id,
                "branch_id": result.branch_id,
                "claim_ids": list(result.claim_ids),
                "claim": result.summary,
                "evidence_urls": list(result.evidence_urls),
                "notes": result.summary,
                "verification_id": result.id,
            }
        )
    existing = view.artifact_store.contradiction_registry()
    return ContradictionRegistryArtifact(
        id=existing.id if existing else support._new_id("contradiction_registry"),
        research_brief_id=research_brief.id if research_brief else None,
        entries=entries,
        status="completed",
        metadata={"entry_count": len(entries)},
    )


def _build_missing_evidence_list_artifact(
    *,
    view: "_RuntimeView",
    research_brief: ResearchBriefArtifact | None,
    revision_issues: list[RevisionIssue],
    gap_artifacts: list[KnowledgeGap],
) -> MissingEvidenceListArtifact:
    items: list[dict[str, Any]] = []
    for gap in gap_artifacts:
        if getattr(gap, "advisory", True):
            continue
        items.append(
            {
                "kind": "coverage_gap",
                "aspect": gap.aspect,
                "reason": gap.reason,
                "branch_id": gap.branch_id,
                "suggested_queries": list(gap.suggested_queries),
                "artifact_id": gap.id,
                "blocking": True,
            }
        )
    for issue in revision_issues:
        if issue.status not in {"open", "accepted"} or not issue.blocking:
            continue
        items.append(
            {
                "kind": issue.issue_type,
                "aspect": issue.summary,
                "reason": issue.summary,
                "branch_id": issue.branch_id,
                "task_id": issue.task_id,
                "artifact_id": issue.id,
                "claim_ids": list(issue.claim_ids),
                "obligation_ids": list(issue.obligation_ids),
                "consistency_result_ids": list(issue.consistency_result_ids),
                "blocking": issue.blocking,
            }
        )
    existing = view.artifact_store.missing_evidence_list()
    return MissingEvidenceListArtifact(
        id=existing.id if existing else support._new_id("missing_evidence_list"),
        research_brief_id=research_brief.id if research_brief else None,
        items=items,
        status="completed",
        metadata={"item_count": len(items)},
    )


def _build_outline_artifact(
    *,
    view: "_RuntimeView",
    research_brief: ResearchBriefArtifact | None,
    verified_syntheses: list[BranchSynthesis],
    coverage_matrix: CoverageMatrixArtifact | None,
    contradiction_registry: ContradictionRegistryArtifact | None,
    missing_evidence_list: MissingEvidenceListArtifact | None,
    revision_issues: list[RevisionIssue] | None = None,
) -> OutlineArtifact:
    sections: list[dict[str, Any]] = []
    coverage_rows = coverage_matrix.rows if coverage_matrix else []
    for row in coverage_rows:
        if str(row.get("status") or "").strip().lower() != "covered":
            continue
        related = [
            synthesis
            for synthesis in verified_syntheses
            if synthesis.id in set(row.get("artifact_ids") or [])
            or synthesis.task_id in set(row.get("task_ids") or [])
        ]
        summary_parts = [synthesis.summary for synthesis in related if synthesis.summary][:3]
        sections.append(
            {
                "title": str(row.get("dimension") or "核心部分").strip() or "核心部分",
                "branch_ids": [synthesis.branch_id for synthesis in related if synthesis.branch_id],
                "task_ids": [synthesis.task_id for synthesis in related],
                "artifact_ids": [synthesis.id for synthesis in related],
                "summary": "\n\n".join(summary_parts)[:1200],
                "citation_urls": list(
                    dict.fromkeys(
                        url for synthesis in related for url in synthesis.citation_urls if url
                    )
                ),
            }
        )
    if not sections:
        for synthesis in verified_syntheses:
            sections.append(
                {
                    "title": synthesis.objective or synthesis.branch_id or "研究结论",
                    "branch_ids": [synthesis.branch_id] if synthesis.branch_id else [],
                    "task_ids": [synthesis.task_id],
                    "artifact_ids": [synthesis.id],
                    "summary": synthesis.summary[:1200],
                    "citation_urls": list(synthesis.citation_urls),
                }
            )

    blocking_gaps: list[dict[str, Any]] = []
    for row in coverage_rows:
        if str(row.get("status") or "").strip().lower() == "covered" or not bool(row.get("blocking")):
            continue
        blocking_gaps.append(
            {
                "dimension": row.get("dimension"),
                "status": row.get("status"),
                "artifact_ids": list(row.get("artifact_ids") or []),
                "gap_ids": list(row.get("gap_ids") or []),
                "issue_ids": list(row.get("blocking_issue_ids") or row.get("issue_ids") or []),
            }
        )
    if contradiction_registry:
        for item in contradiction_registry.entries:
            blocking_gaps.append(
                {
                    "dimension": item.get("claim") or "contradiction",
                    "status": "contradiction",
                    "artifact_ids": [item.get("verification_id")] if item.get("verification_id") else [],
                }
            )
    if missing_evidence_list:
        for item in missing_evidence_list.items[:8]:
            if not bool(item.get("blocking", True)):
                continue
            blocking_gaps.append(
                {
                    "dimension": item.get("aspect") or item.get("kind") or "missing_evidence",
                    "status": "missing_evidence",
                    "artifact_ids": [item.get("artifact_id")] if item.get("artifact_id") else [],
                }
            )
    for issue in revision_issues or []:
        if issue.status not in {"open", "accepted"} or not issue.blocking:
            continue
        blocking_gaps.append(
            {
                "dimension": issue.summary,
                "status": issue.issue_type,
                "artifact_ids": [issue.id],
                "issue_ids": [issue.id],
            }
        )

    existing = view.artifact_store.outline()
    return OutlineArtifact(
        id=existing.id if existing else support._new_id("outline"),
        research_brief_id=research_brief.id if research_brief else None,
        sections=sections,
        blocking_gaps=blocking_gaps,
        is_ready=bool(sections) and not blocking_gaps,
        status="completed" if sections and not blocking_gaps else "updated",
        metadata={
            "section_count": len(sections),
            "brief_goal": research_brief.research_goal if research_brief else "",
        },
    )


@dataclass
class _RuntimeView:
    owner: MultiAgentDeepResearchRuntime
    shared_state: dict[str, Any]
    task_queue: ResearchTaskQueue
    artifact_store: ArtifactStore
    agent_runs: list[AgentRunRecord]
    runtime_state: dict[str, Any]
    graph_run_id: str
    graph_attempt: int
    current_iteration: int
    root_branch_id: str | None
    current_node_id: str

    def __post_init__(self) -> None:
        self.runtime_state.setdefault("engine", "multi_agent")
        self.runtime_state.setdefault("role_counters", _derive_role_counters(self.agent_runs))
        self.runtime_state.setdefault("searches_used", 0)
        self.runtime_state.setdefault("tokens_used", 0)
        self.runtime_state.setdefault("budget_stop_reason", "")
        self.runtime_state.setdefault("started_at_ts", self.owner.start_ts)
        self.runtime_state.setdefault("next_step", "")
        self.runtime_state.setdefault("planning_mode", "")
        self.runtime_state.setdefault("last_gap_result", {})
        self.runtime_state.setdefault("last_decision", {})
        self.runtime_state.setdefault("last_verification_summary", {})
        self.runtime_state.setdefault("supervisor_phase", "")
        self.runtime_state.setdefault("supervisor_plan", {})
        self.runtime_state.setdefault("supervisor_request_ids", [])
        self.runtime_state.setdefault("research_brief_id", "")
        self.runtime_state.setdefault("task_ledger_id", "")
        self.runtime_state.setdefault("progress_ledger_id", "")
        self.runtime_state.setdefault("outline_id", "")
        self.runtime_state.setdefault("outline_status", "pending")
        self.runtime_state.setdefault("intake_status", "pending")
        self.runtime_state.setdefault("clarify_question", "")
        self.runtime_state.setdefault("clarify_question_history", [])
        self.runtime_state.setdefault("clarify_answer_history", [])
        self.runtime_state.setdefault("intake_summary", {})
        self.runtime_state.setdefault("scope_revision_count", 0)
        self.runtime_state.setdefault("scope_feedback_history", [])
        self.runtime_state.setdefault("pending_scope_feedback", "")
        self.runtime_state.setdefault("current_scope_draft", {})
        self.runtime_state.setdefault("approved_scope_draft", {})
        self.runtime_state.setdefault("terminal_status", "")
        self.runtime_state.setdefault("terminal_reason", "")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.owner, name)

    @property
    def emitter(self) -> Any:
        return self.owner.emitter

    @property
    def start_ts(self) -> float:
        return float(self.runtime_state.get("started_at_ts") or self.owner.start_ts)

    @property
    def searches_used(self) -> int:
        return int(self.runtime_state.get("searches_used", 0) or 0)

    @searches_used.setter
    def searches_used(self, value: int) -> None:
        self.runtime_state["searches_used"] = max(0, int(value))

    @property
    def tokens_used(self) -> int:
        return int(self.runtime_state.get("tokens_used", 0) or 0)

    @tokens_used.setter
    def tokens_used(self, value: int) -> None:
        self.runtime_state["tokens_used"] = max(0, int(value))

    @property
    def budget_stop_reason(self) -> str | None:
        value = str(self.runtime_state.get("budget_stop_reason") or "").strip()
        return value or None

    @budget_stop_reason.setter
    def budget_stop_reason(self, value: str | None) -> None:
        self.runtime_state["budget_stop_reason"] = str(value or "")

    @property
    def terminal_status(self) -> str:
        return str(self.runtime_state.get("terminal_status") or "").strip()

    @property
    def terminal_reason(self) -> str:
        return str(self.runtime_state.get("terminal_reason") or "").strip()

    def set_terminal_state(self, *, status: str, reason: str) -> None:
        normalized_status = str(status or "").strip()
        normalized_reason = str(reason or "").strip()
        self.runtime_state["terminal_status"] = normalized_status
        self.runtime_state["terminal_reason"] = normalized_reason
        if normalized_reason:
            _append_shared_error(self.shared_state, normalized_reason)

    def next_agent_id(self, role: str) -> str:
        counters = self.runtime_state.setdefault("role_counters", {})
        counters[role] = int(counters.get(role, 0) or 0) + 1
        return f"{role}-{counters[role]}"

    def _check_cancel(self) -> None:
        if self.shared_state.get("is_cancelled"):
            raise asyncio.CancelledError("Task was cancelled (flag)")
        token_id = self.shared_state.get("cancel_token_id")
        if token_id:
            _check_cancel_token(token_id)

    def _knowledge_summary(self) -> str:
        syntheses = [synthesis.summary for synthesis in self.artifact_store.branch_syntheses() if synthesis.summary]
        if syntheses:
            return "\n\n".join(syntheses[:8])
        sections = [section.summary for section in self.artifact_store.section_drafts() if section.summary]
        if sections:
            return "\n\n".join(sections[:8])
        notes = self.shared_state.get("summary_notes", [])
        if isinstance(notes, list) and notes:
            return "\n\n".join(str(note) for note in notes[:8])
        return ""

    def _quality_summary(self, gap_result: GapAnalysisResult | None) -> dict[str, Any]:
        passages = self.artifact_store.evidence_passages()
        evidence_cards = self.artifact_store.evidence_cards()
        unique_urls = {passage.url for passage in passages if passage.url}
        if not unique_urls:
            unique_urls = {card.source_url for card in evidence_cards if card.source_url}
        syntheses = self.artifact_store.branch_syntheses()
        verification_results = self.artifact_store.verification_results(validation_stage="coverage_check")
        grounding_results = self.artifact_store.claim_grounding_results()
        revision_issues = self.artifact_store.revision_issues()
        advisory_gaps = self.artifact_store.gap_artifacts()
        verified_branch_ids = {
            result.branch_id
            for result in verification_results
            if result.branch_id and result.outcome == "passed"
        }
        coverage = float(gap_result.overall_coverage) if gap_result else 0.0
        citation_denominator = max(1, len(passages) or len(evidence_cards) or len(syntheses))
        citation_coverage = min(1.0, len(unique_urls) / citation_denominator) if unique_urls else 0.0
        grounded_claims = sum(1 for result in grounding_results if result.status == "grounded")
        total_checked_claims = len(grounding_results)
        resolved_issue_count = sum(1 for issue in revision_issues if issue.status == "resolved")
        unresolved_issue_count = sum(
            1 for issue in revision_issues if issue.status in {"open", "accepted"} and issue.blocking
        )
        verification_precision = grounded_claims / max(1, total_checked_claims)
        revision_convergence = resolved_issue_count / max(1, len(revision_issues))
        return {
            "engine": "multi_agent",
            "stage": "final" if self.task_queue.ready_count() == 0 else "iteration",
            "query_coverage_score": coverage,
            "citation_coverage_score": citation_coverage,
            "verification_precision": verification_precision,
            "unresolved_issue_count": unresolved_issue_count,
            "blocking_verification_debt_count": unresolved_issue_count,
            "revision_convergence": revision_convergence,
            "knowledge_gap_count": sum(1 for gap in advisory_gaps if getattr(gap, "advisory", True)),
            "advisory_gap_count": sum(1 for gap in advisory_gaps if getattr(gap, "advisory", True)),
            "suggested_queries": gap_result.suggested_queries if gap_result else [],
            "analysis": gap_result.analysis if gap_result else "",
            "freshness_warning": "",
            "verified_branch_count": len(verified_branch_ids),
            "branch_synthesis_count": len(syntheses),
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "node_id": self.current_node_id,
            "branch_id": self.root_branch_id,
        }

    def _research_topology_snapshot(self) -> dict[str, Any]:
        tasks = sorted(self.task_queue.all_tasks(), key=lambda task: (task.priority, task.created_at, task.id))
        return {
            "id": "deep_research_multi_agent",
            "topic": self.owner.topic,
            "engine": "multi_agent",
            "graph_run_id": self.graph_run_id,
            "branch_id": self.root_branch_id,
            "children": [
                {
                    "id": task.id,
                    "title": task.title or task.objective or task.goal,
                    "objective": task.objective,
                    "task_kind": task.task_kind,
                    "revision_kind": task.revision_kind,
                    "revision_of_task_id": task.revision_of_task_id,
                    "revision_brief_id": task.revision_brief_id,
                    "target_issue_ids": list(task.target_issue_ids),
                    "resolved_issue_ids": list(task.resolved_issue_ids),
                    "stage": task.stage,
                    "query": task.query,
                    "status": task.status,
                    "priority": task.priority,
                    "branch_id": task.branch_id,
                    "parent_context_id": task.parent_context_id,
                    "attempts": task.attempts,
                }
                for task in tasks
            ],
        }

    def _scope_summary(self) -> dict[str, Any]:
        task_snapshot = self.task_queue.snapshot()
        briefs = self.artifact_store.branch_briefs()
        current_scope = copy.deepcopy(self.runtime_state.get("current_scope_draft") or {})
        approved_scope = copy.deepcopy(self.runtime_state.get("approved_scope_draft") or {})
        graph_scope: GraphScopeSnapshot = {
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "topic": self.owner.topic,
            "phase": self.current_node_id,
            "current_iteration": self.current_iteration,
            "intake_status": str(self.runtime_state.get("intake_status") or "pending"),
            "scope_revision_count": int(self.runtime_state.get("scope_revision_count", 0) or 0),
            "current_scope_version": _scope_version(current_scope),
            "approved_scope_version": _scope_version(approved_scope),
            "supervisor_phase": str(self.runtime_state.get("supervisor_phase") or ""),
            "supervisor_plan_id": str(
                (self.runtime_state.get("supervisor_plan") or {}).get("id") or ""
            ),
            "research_brief_id": str(self.runtime_state.get("research_brief_id") or ""),
            "task_ledger_id": str(self.runtime_state.get("task_ledger_id") or ""),
            "progress_ledger_id": str(self.runtime_state.get("progress_ledger_id") or ""),
            "outline_id": str(self.runtime_state.get("outline_id") or ""),
            "outline_status": str(self.runtime_state.get("outline_status") or "pending"),
            "latest_supervisor_decision_id": (
                self.artifact_store.supervisor_decisions()[-1].id
                if self.artifact_store.supervisor_decisions()
                else ""
            ),
            "open_request_count": len(self.artifact_store.coordination_requests(status="open")),
            "budget": {
                "searches_used": self.searches_used,
                "tokens_used": self.tokens_used,
                "max_searches": self.max_searches,
                "max_tokens": self.max_tokens,
                "max_seconds": self.max_seconds,
                "budget_stop_reason": self.budget_stop_reason,
            },
            "task_queue_stats": task_snapshot.get("stats", {}),
            "artifact_counts": {
                "has_research_brief": self.artifact_store.research_brief() is not None,
                "has_task_ledger": self.artifact_store.task_ledger() is not None,
                "has_progress_ledger": self.artifact_store.progress_ledger() is not None,
                "has_coverage_matrix": self.artifact_store.coverage_matrix() is not None,
                "has_contradiction_registry": self.artifact_store.contradiction_registry() is not None,
                "has_missing_evidence_list": self.artifact_store.missing_evidence_list() is not None,
                "has_outline": self.artifact_store.outline() is not None,
                "branch_briefs": len(briefs),
                "source_candidates": len(self.artifact_store.source_candidates()),
                "fetched_documents": len(self.artifact_store.fetched_documents()),
                "evidence_passages": len(self.artifact_store.evidence_passages()),
                "evidence_cards": len(self.artifact_store.evidence_cards()),
                "branch_syntheses": len(self.artifact_store.branch_syntheses()),
                "verification_results": len(self.artifact_store.verification_results()),
                "coordination_requests": len(self.artifact_store.coordination_requests()),
                "submissions": len(self.artifact_store.submissions()),
                "supervisor_decisions": len(self.artifact_store.supervisor_decisions()),
                "knowledge_gaps": len(self.artifact_store.gap_artifacts()),
                "report_section_drafts": len(self.artifact_store.section_drafts()),
                "has_final_report": self.artifact_store.final_report() is not None,
            },
            "final_status": (
                self.terminal_status
                or ("completed" if self.artifact_store.final_report() else "running")
            ),
            "terminal_status": self.terminal_status,
            "terminal_reason": self.terminal_reason,
        }
        branch_scopes = [
            {
                "branch_id": brief.id,
                "topic": brief.topic,
                "summary": brief.summary,
                "status": brief.status,
                "parent_branch_id": brief.parent_branch_id,
                "objective": brief.objective,
                "task_kind": brief.task_kind,
                "current_stage": brief.current_stage,
                "verification_status": brief.verification_status,
                "latest_task_id": brief.latest_task_id,
                "latest_submission_id": (
                    next(
                        (
                            submission.id
                            for submission in reversed(self.artifact_store.submissions(branch_id=brief.id))
                        ),
                        None,
                    )
                ),
                "open_request_ids": [
                    request.id
                    for request in self.artifact_store.coordination_requests(branch_id=brief.id, status="open")
                ],
                "task_ids": [task.id for task in self.task_queue.all_tasks() if task.branch_id == brief.id],
            }
            for brief in briefs
        ]
        worker_scopes: list[WorkerScopeSnapshot] = []
        sub_contexts = self.shared_state.get("sub_agent_contexts", {})
        if isinstance(sub_contexts, dict):
            for scope_id, item in sub_contexts.items():
                if not isinstance(item, dict):
                    continue
                worker_scopes.append(
                    {
                        "scope_id": str(scope_id),
                        "task_id": str(item.get("task_id") or ""),
                        "branch_id": item.get("parent_scope_id"),
                        "agent_id": str(item.get("agent_id") or ""),
                        "role": "researcher",
                        "query": str(item.get("query") or ""),
                        "objective": str((item.get("brief") or {}).get("objective") or ""),
                        "task_kind": str((item.get("brief") or {}).get("task_kind") or ""),
                        "stage": str((item.get("brief") or {}).get("stage") or ""),
                        "attempt": int(item.get("attempt") or 0),
                        "status": "completed" if item.get("is_complete") else "running",
                        "artifact_ids": [
                            str(artifact.get("id"))
                            for artifact in item.get("artifacts_created", [])
                            if isinstance(artifact, dict) and artifact.get("id")
                        ],
                    }
                )
        return {
            "graph_scope": graph_scope,
            "branch_scopes": branch_scopes,
            "worker_scopes": worker_scopes,
            "intake": {
                "clarify_question": str(self.runtime_state.get("clarify_question") or ""),
                "clarify_question_history": copy.deepcopy(
                    self.runtime_state.get("clarify_question_history", [])
                ),
                "clarify_answer_history": copy.deepcopy(
                    self.runtime_state.get("clarify_answer_history", [])
                ),
                "intake_summary": copy.deepcopy(self.runtime_state.get("intake_summary", {})),
                "scope_feedback_history": copy.deepcopy(
                    self.runtime_state.get("scope_feedback_history", [])
                ),
                "current_scope_draft": current_scope,
                "approved_scope_draft": approved_scope,
            },
        }

    def runtime_state_snapshot(self) -> dict[str, Any]:
        return {
            "engine": "multi_agent",
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "phase": self.current_node_id,
            "next_step": self.runtime_state.get("next_step", ""),
            "planning_mode": self.runtime_state.get("planning_mode", ""),
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_epochs,
            "searches_used": self.searches_used,
            "tokens_used": self.tokens_used,
            "max_searches": self.max_searches,
            "max_tokens": self.max_tokens,
            "max_seconds": self.max_seconds,
            "budget_stop_reason": self.budget_stop_reason,
            "elapsed_seconds": round(max(0.0, time.time() - self.start_ts), 3),
            "started_at_ts": self.start_ts,
            "root_branch_id": self.root_branch_id,
            "role_counters": copy.deepcopy(self.runtime_state.get("role_counters", {})),
            "last_gap_result": copy.deepcopy(self.runtime_state.get("last_gap_result", {})),
            "last_decision": copy.deepcopy(self.runtime_state.get("last_decision", {})),
            "last_verification_summary": copy.deepcopy(
                self.runtime_state.get("last_verification_summary", {})
            ),
            "supervisor_phase": str(self.runtime_state.get("supervisor_phase") or ""),
            "supervisor_plan": copy.deepcopy(self.runtime_state.get("supervisor_plan", {})),
            "supervisor_request_ids": copy.deepcopy(
                self.runtime_state.get("supervisor_request_ids", [])
            ),
            "research_brief_id": str(self.runtime_state.get("research_brief_id") or ""),
            "task_ledger_id": str(self.runtime_state.get("task_ledger_id") or ""),
            "progress_ledger_id": str(self.runtime_state.get("progress_ledger_id") or ""),
            "outline_id": str(self.runtime_state.get("outline_id") or ""),
            "outline_status": str(self.runtime_state.get("outline_status") or "pending"),
            "intake_status": str(self.runtime_state.get("intake_status") or "pending"),
            "clarify_question": str(self.runtime_state.get("clarify_question") or ""),
            "clarify_question_history": copy.deepcopy(
                self.runtime_state.get("clarify_question_history", [])
            ),
            "clarify_answer_history": copy.deepcopy(
                self.runtime_state.get("clarify_answer_history", [])
            ),
            "intake_summary": copy.deepcopy(self.runtime_state.get("intake_summary", {})),
            "scope_revision_count": int(self.runtime_state.get("scope_revision_count", 0) or 0),
            "scope_feedback_history": copy.deepcopy(
                self.runtime_state.get("scope_feedback_history", [])
            ),
            "pending_scope_feedback": str(self.runtime_state.get("pending_scope_feedback") or ""),
            "current_scope_draft": copy.deepcopy(self.runtime_state.get("current_scope_draft", {})),
            "approved_scope_draft": copy.deepcopy(self.runtime_state.get("approved_scope_draft", {})),
            "terminal_status": self.terminal_status,
            "terminal_reason": self.terminal_reason,
            "scope_summary": self._scope_summary(),
        }

    def snapshot_patch(self, **extra: Any) -> dict[str, Any]:
        self.runtime_state["phase"] = self.current_node_id
        self.runtime_state["next_step"] = extra.get("next_step", self.runtime_state.get("next_step", ""))
        self.runtime_state["planning_mode"] = extra.get(
            "planning_mode",
            self.runtime_state.get("planning_mode", ""),
        )
        latest_gap = extra.get("latest_gap_result")
        if latest_gap is not None:
            self.runtime_state["last_gap_result"] = copy.deepcopy(latest_gap)
        latest_decision = extra.get("latest_decision")
        if latest_decision is not None:
            self.runtime_state["last_decision"] = copy.deepcopy(latest_decision)
        latest_verification = extra.get("latest_verification_summary")
        if latest_verification is not None:
            self.runtime_state["last_verification_summary"] = copy.deepcopy(latest_verification)
        patch: dict[str, Any] = {
            "shared_state": copy.deepcopy(self.shared_state),
            "graph_run_id": self.graph_run_id,
            "graph_attempt": self.graph_attempt,
            "root_branch_id": self.root_branch_id,
            "task_queue": self.task_queue.snapshot(),
            "artifact_store": self.artifact_store.snapshot(),
            "runtime_state": self.runtime_state_snapshot(),
            "agent_runs": [run.to_dict() for run in self.agent_runs],
            "current_iteration": self.current_iteration,
            "planning_mode": self.runtime_state.get("planning_mode", ""),
            "next_step": self.runtime_state.get("next_step", ""),
        }
        for key, value in extra.items():
            if key in {
                "latest_gap_result",
                "latest_decision",
                "latest_verification_summary",
                "pending_worker_tasks",
                "worker_results",
                "final_result",
            }:
                patch[key] = value
        return patch

    def _emit(self, event_type: events.ToolEventType | str, payload: dict[str, Any]) -> None:
        events.emit(self.emitter, event_type, payload)

    def _emit_task_update(
        self,
        *,
        task: ResearchTask,
        status: str,
        iteration: int | None = None,
        attempt: int | None = None,
        reason: str | None = None,
    ) -> None:
        events.emit_task_update(
            self,
            task=task,
            status=status,
            iteration=iteration,
            attempt=attempt,
            reason=reason,
        )

    def _emit_artifact_update(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        status: str,
        task_id: str | None = None,
        branch_id: str | None = None,
        agent_id: str | None = None,
        summary: str | None = None,
        source_url: str | None = None,
        task_kind: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
        iteration: int | None = None,
        attempt: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        events.emit_artifact_update(
            self,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            status=status,
            task_id=task_id,
            branch_id=branch_id,
            agent_id=agent_id,
            summary=summary,
            source_url=source_url,
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            iteration=iteration,
            attempt=attempt,
            extra=extra,
        )

    def _emit_agent_start(
        self,
        *,
        agent_id: str,
        role: str,
        phase: str,
        task_id: str | None = None,
        iteration: int | None = None,
        branch_id: str | None = None,
        attempt: int | None = None,
        task_kind: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
        objective_summary: str | None = None,
    ) -> None:
        events.emit_agent_start(
            self,
            agent_id=agent_id,
            role=role,
            phase=phase,
            task_id=task_id,
            iteration=iteration,
            branch_id=branch_id,
            attempt=attempt,
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            objective_summary=objective_summary,
        )

    def _emit_agent_complete(
        self,
        *,
        agent_id: str,
        role: str,
        phase: str,
        status: str,
        task_id: str | None = None,
        iteration: int | None = None,
        summary: str | None = None,
        branch_id: str | None = None,
        attempt: int | None = None,
        task_kind: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
        objective_summary: str | None = None,
    ) -> None:
        events.emit_agent_complete(
            self,
            agent_id=agent_id,
            role=role,
            phase=phase,
            status=status,
            task_id=task_id,
            iteration=iteration,
            summary=summary,
            branch_id=branch_id,
            attempt=attempt,
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            objective_summary=objective_summary,
        )

    def _emit_decision(
        self,
        *,
        decision_type: str,
        reason: str,
        iteration: int | None = None,
        coverage: float | None = None,
        gap_count: int | None = None,
        attempt: int | None = None,
        branch_id: str | None = None,
        task_id: str | None = None,
        task_kind: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        events.emit_decision(
            self,
            decision_type=decision_type,
            reason=reason,
            iteration=iteration,
            coverage=coverage,
            gap_count=gap_count,
            attempt=attempt,
            branch_id=branch_id,
            task_id=task_id,
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            extra=extra,
        )

    def _emit_deep_research_topology_update(self) -> None:
        events.emit_deep_research_topology_update(self)

    def record_supervisor_decision(
        self,
        *,
        phase: str,
        decision_type: str,
        summary: str,
        next_step: str,
        planning_mode: str = "",
        task_ids: list[str] | None = None,
        request_ids: list[str] | None = None,
        issue_ids: list[str] | None = None,
        revision_brief_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SupervisorDecisionArtifact:
        artifact = SupervisorDecisionArtifact(
            id=support._new_id("supervisor_decision"),
            phase=phase,
            decision_type=decision_type,
            summary=summary,
            branch_id=self.root_branch_id,
            task_ids=list(task_ids or []),
            request_ids=list(request_ids or []),
            issue_ids=list(issue_ids or []),
            revision_brief_ids=list(revision_brief_ids or []),
            next_step=next_step,
            planning_mode=planning_mode,
            iteration=self.current_iteration,
            metadata=copy.deepcopy(metadata or {}),
        )
        self.artifact_store.add_supervisor_decision(artifact)
        self.runtime_state["supervisor_phase"] = phase
        self.runtime_state["last_decision"] = {
            "id": artifact.id,
            "decision_type": decision_type,
            "summary": summary,
            "next_step": next_step,
            "planning_mode": planning_mode,
            "task_ids": list(task_ids or []),
            "request_ids": list(request_ids or []),
            "issue_ids": list(issue_ids or []),
            "revision_brief_ids": list(revision_brief_ids or []),
        }
        self._emit_artifact_update(
            artifact_id=artifact.id,
            artifact_type="supervisor_decision",
            status=artifact.status,
            branch_id=self.root_branch_id,
            agent_id=artifact.created_by,
            summary=summary[:180],
            stage=phase,
            extra={
                "decision_type": decision_type,
                "next_step": next_step,
                "planning_mode": planning_mode,
                "task_ids": list(task_ids or []),
                "request_ids": list(request_ids or []),
                "issue_ids": list(issue_ids or []),
                "revision_brief_ids": list(revision_brief_ids or []),
            },
        )
        return artifact

    def start_agent_run(
        self,
        *,
        role: str,
        phase: str,
        task_id: str | None = None,
        branch_id: str | None = None,
        iteration: int | None = None,
        attempt: int | None = None,
        task_kind: str = "",
        stage: str = "",
        validation_stage: str = "",
        objective_summary: str = "",
        persist: bool = True,
    ) -> AgentRunRecord:
        record = AgentRunRecord(
            id=support._new_id("agent_run"),
            role=role,
            phase=phase,
            status="running",
            agent_id=self.next_agent_id(role),
            graph_run_id=self.graph_run_id,
            node_id=self.current_node_id,
            task_id=task_id,
            branch_id=branch_id,
            task_kind=task_kind,
            stage=stage,
            validation_stage=validation_stage,
            objective_summary=objective_summary,
            attempt=int(attempt or self.graph_attempt or 1),
        )
        if persist:
            self.agent_runs.append(record)
        self._emit_agent_start(
            agent_id=record.agent_id,
            role=record.role,
            phase=phase,
            task_id=task_id,
            iteration=iteration,
            branch_id=branch_id,
            attempt=record.attempt,
            task_kind=task_kind or record.task_kind,
            stage=stage or record.stage,
            validation_stage=validation_stage or record.validation_stage,
            objective_summary=objective_summary or record.objective_summary,
        )
        return record

    def finish_agent_run(
        self,
        record: AgentRunRecord,
        *,
        status: str,
        summary: str = "",
        iteration: int | None = None,
        branch_id: str | None = None,
        stage: str | None = None,
        validation_stage: str | None = None,
    ) -> AgentRunRecord:
        record.status = status
        record.summary = summary
        record.ended_at = _now_iso()
        if stage:
            record.stage = stage
        if validation_stage:
            record.validation_stage = validation_stage
        self._emit_agent_complete(
            agent_id=record.agent_id,
            role=record.role,
            phase=record.phase,
            status=status,
            task_id=record.task_id,
            iteration=iteration,
            summary=summary,
            branch_id=branch_id or record.branch_id,
            attempt=record.attempt,
            task_kind=record.task_kind,
            stage=record.stage,
            validation_stage=record.validation_stage,
            objective_summary=record.objective_summary,
        )
        return record

    def sync_task_ledger(self, *, reason: str, created_by: str = "supervisor") -> TaskLedgerArtifact:
        ledger = self.artifact_store.task_ledger() or TaskLedgerArtifact(id=support._new_id("task_ledger"))
        research_brief = self.artifact_store.research_brief()
        revision_issues = self.artifact_store.revision_issues()
        ledger.research_brief_id = research_brief.id if research_brief else None
        ledger.entries = _build_task_ledger_entries(
            self.task_queue.all_tasks(),
            self.artifact_store.coordination_requests(),
            revision_issues,
        )
        ledger.issue_statuses = summarize_issue_statuses(revision_issues)
        ledger.created_by = created_by or ledger.created_by
        ledger.metadata["reason"] = reason
        ledger.metadata["task_count"] = len(ledger.entries)
        self.artifact_store.set_task_ledger(ledger)
        self.runtime_state["task_ledger_id"] = ledger.id
        self._emit_artifact_update(
            artifact_id=ledger.id,
            artifact_type="task_ledger",
            status=ledger.status,
            branch_id=self.root_branch_id,
            agent_id=created_by,
            summary=reason[:180],
            stage=self.current_node_id,
            extra={"entry_count": len(ledger.entries)},
        )
        return ledger

    def sync_progress_ledger(
        self,
        *,
        phase: str,
        reason: str,
        created_by: str = "supervisor",
        decision: dict[str, Any] | None = None,
        verification_summary: dict[str, Any] | None = None,
        outline_status: str | None = None,
        stop_reason: str | None = None,
    ) -> ProgressLedgerArtifact:
        ledger = self.artifact_store.progress_ledger() or ProgressLedgerArtifact(
            id=support._new_id("progress_ledger")
        )
        research_brief = self.artifact_store.research_brief()
        open_requests = self.artifact_store.coordination_requests(status="open")
        revision_issues = self.artifact_store.revision_issues()
        revision_briefs = self.artifact_store.revision_briefs()
        ledger.research_brief_id = research_brief.id if research_brief else None
        ledger.phase = phase
        ledger.current_iteration = self.current_iteration
        ledger.active_request_ids = [request.id for request in open_requests]
        ledger.blockers = _build_progress_blockers(
            open_requests,
            revision_issues,
            budget_stop_reason=self.budget_stop_reason,
        )
        ledger.issue_statuses = summarize_issue_statuses(revision_issues)
        ledger.revision_lineage = summarize_revision_lineage(
            revision_briefs=revision_briefs,
            issues=revision_issues,
        )
        if decision:
            decision_payload = copy.deepcopy(decision)
            decision_payload.setdefault("phase", phase)
            decision_payload.setdefault("recorded_at", _now_iso())
            ledger.latest_decision = decision_payload
            ledger.decisions = [*ledger.decisions, decision_payload][-20:]
        if verification_summary is not None:
            ledger.verification_summary = copy.deepcopy(verification_summary)
        if outline_status is not None:
            ledger.outline_status = outline_status
            self.runtime_state["outline_status"] = outline_status
        ledger.budget_stop_reason = self.budget_stop_reason or ""
        if stop_reason is not None:
            ledger.stop_reason = stop_reason
        ledger.created_by = created_by or ledger.created_by
        ledger.metadata["reason"] = reason
        self.artifact_store.set_progress_ledger(ledger)
        self.runtime_state["progress_ledger_id"] = ledger.id
        self._emit_artifact_update(
            artifact_id=ledger.id,
            artifact_type="progress_ledger",
            status=ledger.status,
            branch_id=self.root_branch_id,
            agent_id=created_by,
            summary=reason[:180],
            stage=phase,
            extra={
                "active_request_ids": list(ledger.active_request_ids),
                "outline_status": ledger.outline_status,
            },
        )
        return ledger


class MultiAgentDeepResearchRuntime:
    def __init__(self, state: dict[str, Any], config: dict[str, Any]):
        self._deps = _resolve_deps()
        self.state = dict(state)
        self.config = dict(config or {})
        self.cfg = self.config.get("configurable") or {}
        if not isinstance(self.cfg, dict):
            self.cfg = {}

        self.topic = str(self.state.get("input") or self.state.get("topic") or "").strip()
        self.thread_id = str(
            self.cfg.get("thread_id") or self.state.get("cancel_token_id") or ""
        ).strip()
        self.emitter = self._deps.get_emitter_sync(self.thread_id) if self.thread_id else None
        self.allow_interrupts = bool(self.cfg.get("allow_interrupts"))
        self.resumed_from_checkpoint = bool(
            self.state.get("resumed_from_checkpoint") or self.cfg.get("resumed_from_checkpoint")
        )

        resume_runtime_state = self._resume_runtime_state_snapshot()
        self.start_ts = float(resume_runtime_state.get("started_at_ts") or time.time())
        self.max_epochs = max(
            1,
            support._configurable_int(
                self.config,
                "deep_research_max_epochs",
                settings.deep_research_max_epochs,
            ),
        )
        self.query_num = max(
            1,
            support._configurable_int(
                self.config,
                "deep_research_query_num",
                settings.deep_research_query_num,
            ),
        )
        self.results_per_query = max(
            1,
            support._configurable_int(
                self.config,
                "deep_research_results_per_query",
                settings.deep_research_results_per_query,
            ),
        )
        self.parallel_workers = max(
            1,
            resolve_parallel_workers(self.config),
        )
        self.max_seconds = max(
            0.0,
            support._configurable_float(
                self.config,
                "deep_research_max_seconds",
                settings.deep_research_max_seconds,
            ),
        )
        self.max_tokens = max(
            0,
            support._configurable_int(
                self.config,
                "deep_research_max_tokens",
                settings.deep_research_max_tokens,
            ),
        )
        self.max_searches = max(
            0,
            resolve_max_searches(self.config),
        )
        self.task_retry_limit = max(
            1,
            support._configurable_int(self.config, "deep_research_task_retry_limit", 2),
        )
        self.scope_revision_limit = max(
            1,
            support._configurable_int(self.config, "deep_research_scope_revision_limit", 3),
        )
        self.max_clarify_rounds = max(
            1,
            support._configurable_int(self.config, "deep_research_clarify_round_limit", 2),
        )
        self.pause_before_merge = bool(self.cfg.get("deep_research_pause_before_merge"))

        self.provider_profile = support._resolve_provider_profile(self.state)
        self.enable_tool_agents = bool(
            self.cfg.get("deep_research_use_tool_agents", getattr(settings, "deep_research_use_tool_agents", True))
        )

        supervisor_model = support._model_for_task("planning", self.config)
        researcher_model = support._model_for_task("research", self.config)
        reporter_model = support._model_for_task("writing", self.config)
        verifier_model = support._model_for_task("gap_analysis", self.config)
        self.supervisor_model = supervisor_model
        self.researcher_model = researcher_model
        self.reporter_model = reporter_model
        self.verifier_model = verifier_model

        self.clarifier = self._deps.DeepResearchClarifyAgent(
            self._deps.create_chat_model(supervisor_model, temperature=0),
            self.config,
        )
        self.scope_agent = self._deps.DeepResearchScopeAgent(
            self._deps.create_chat_model(supervisor_model, temperature=0),
            self.config,
        )
        self.supervisor = self._deps.ResearchSupervisor(
            self._deps.create_chat_model(supervisor_model, temperature=0),
            self.config,
        )
        self.researcher = self._deps.ResearchAgent(
            self._deps.create_chat_model(researcher_model, temperature=0),
            self._search_with_tracking,
            self.config,
        )
        self.reporter = self._deps.ResearchReporter(
            self._deps.create_chat_model(reporter_model, temperature=0),
            self.config,
        )
        self.verifier = self._deps.KnowledgeGapAnalyzer(
            self._deps.create_chat_model(verifier_model, temperature=0),
            self.config,
        )
        self.claim_verifier = ClaimVerifier()

    def _resume_task_queue_snapshot(self) -> dict[str, Any]:
        snapshot = read_deep_runtime_snapshot(self.state)
        return copy.deepcopy(snapshot.get("task_queue") or {})

    def _resume_artifact_store_snapshot(self) -> dict[str, Any]:
        snapshot = read_deep_runtime_snapshot(self.state)
        return copy.deepcopy(snapshot.get("artifact_store") or {})

    def _resume_runtime_state_snapshot(self) -> dict[str, Any]:
        snapshot = read_deep_runtime_snapshot(self.state)
        return copy.deepcopy(snapshot.get("runtime_state") or {})

    def _resume_agent_runs_snapshot(self) -> list[dict[str, Any]]:
        snapshot = read_deep_runtime_snapshot(self.state)
        return copy.deepcopy(snapshot.get("agent_runs") or [])

    def _initial_shared_state(self) -> dict[str, Any]:
        return {
            "input": self.state.get("input", ""),
            "topic": self.topic,
            "route": self.state.get("route", "deep"),
            "domain": self.state.get("domain", ""),
            "domain_config": copy.deepcopy(self.state.get("domain_config", {})),
            "scraped_content": copy.deepcopy(self.state.get("scraped_content", [])),
            "summary_notes": copy.deepcopy(self.state.get("summary_notes", [])),
            "sources": copy.deepcopy(self.state.get("sources", [])),
            "errors": copy.deepcopy(self.state.get("errors", [])),
            "sub_agent_contexts": copy.deepcopy(self.state.get("sub_agent_contexts", {})),
            "cancel_token_id": self.state.get("cancel_token_id"),
            "is_cancelled": bool(self.state.get("is_cancelled")),
        }

    def _first_branch_id(self, artifact_store_snapshot: dict[str, Any]) -> str | None:
        briefs = artifact_store_snapshot.get("branch_briefs", [])
        if isinstance(briefs, list) and briefs:
            first = briefs[0]
            if isinstance(first, dict):
                return str(first.get("id") or "") or None
        return None

    def _initial_next_step(
        self,
        task_queue_snapshot: dict[str, Any],
        artifact_store_snapshot: dict[str, Any],
        runtime_state_snapshot: dict[str, Any],
    ) -> str:
        existing = str(runtime_state_snapshot.get("next_step") or "").strip()
        if existing == "completed":
            return "finalize"
        if existing:
            return existing
        if artifact_store_snapshot.get("final_report"):
            return "finalize"
        approved_scope = runtime_state_snapshot.get("approved_scope_draft")
        current_scope = runtime_state_snapshot.get("current_scope_draft")
        intake_status = str(runtime_state_snapshot.get("intake_status") or "pending").strip().lower()
        if not isinstance(approved_scope, dict) or not approved_scope:
            if isinstance(current_scope, dict) and current_scope:
                return "scope_review"
            if intake_status in {"ready_for_scope", "scope_revision_requested"}:
                return "scope"
            return "clarify"
        if not isinstance(artifact_store_snapshot.get("research_brief"), dict) or not artifact_store_snapshot.get(
            "research_brief"
        ):
            return "research_brief"
        stats = task_queue_snapshot.get("stats", {}) if isinstance(task_queue_snapshot, dict) else {}
        if int(stats.get("total", 0) or 0) == 0:
            return "supervisor_plan"
        if int(stats.get("ready", 0) or 0) > 0 or int(stats.get("in_progress", 0) or 0) > 0:
            return "dispatch"
        outline_artifact = artifact_store_snapshot.get("outline")
        if isinstance(outline_artifact, dict):
            if outline_artifact.get("is_ready"):
                return "report"
            return "outline_gate"
        if artifact_store_snapshot.get("final_report"):
            return "finalize"
        return "supervisor_decide"

    def build_initial_graph_state(self) -> MultiAgentGraphState:
        task_queue_snapshot = self._resume_task_queue_snapshot()
        artifact_store_snapshot = self._resume_artifact_store_snapshot()
        runtime_state_snapshot = self._resume_runtime_state_snapshot()
        return {
            "shared_state": self._initial_shared_state(),
            "topic": self.topic,
            "graph_run_id": str(runtime_state_snapshot.get("graph_run_id") or support._new_id("graph_run")),
            "graph_attempt": int(runtime_state_snapshot.get("graph_attempt", 0) or 0) + 1,
            "root_branch_id": str(
                runtime_state_snapshot.get("root_branch_id")
                or self._first_branch_id(artifact_store_snapshot)
                or ""
            ).strip(),
            "task_queue": task_queue_snapshot,
            "artifact_store": artifact_store_snapshot,
            "runtime_state": runtime_state_snapshot,
            "agent_runs": self._resume_agent_runs_snapshot(),
            "current_iteration": int(runtime_state_snapshot.get("current_iteration", 0) or 0),
            "planning_mode": str(runtime_state_snapshot.get("planning_mode") or "").strip() or "initial",
            "next_step": self._initial_next_step(
                task_queue_snapshot,
                artifact_store_snapshot,
                runtime_state_snapshot,
            ),
            "latest_gap_result": copy.deepcopy(runtime_state_snapshot.get("last_gap_result", {})),
            "latest_decision": copy.deepcopy(runtime_state_snapshot.get("last_decision", {})),
            "latest_verification_summary": copy.deepcopy(
                runtime_state_snapshot.get("last_verification_summary", {})
            ),
            "pending_worker_tasks": [],
            "worker_results": [],
        }

    def _view(self, graph_state: MultiAgentGraphState, node_id: str) -> _RuntimeView:
        return _RuntimeView(
            owner=self,
            shared_state=copy.deepcopy(graph_state.get("shared_state") or self._initial_shared_state()),
            task_queue=ResearchTaskQueue.from_snapshot(graph_state.get("task_queue")),
            artifact_store=ArtifactStore.from_snapshot(graph_state.get("artifact_store")),
            agent_runs=_restore_agent_runs(graph_state.get("agent_runs", [])),
            runtime_state=copy.deepcopy(graph_state.get("runtime_state") or {}),
            graph_run_id=str(graph_state.get("graph_run_id") or support._new_id("graph_run")),
            graph_attempt=int(graph_state.get("graph_attempt", 1) or 1),
            current_iteration=int(graph_state.get("current_iteration", 0) or 0),
            root_branch_id=str(graph_state.get("root_branch_id") or "").strip() or None,
            current_node_id=node_id,
        )

    def _search_with_tracking(self, payload: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(payload.get("query") or "").strip()
        max_results = int(payload.get("max_results") or self.results_per_query)
        results = support._search_query(query, max_results, config, self.provider_profile)
        if query and self.emitter:
            events.emit(
                self.emitter,
                events.ToolEventType.SEARCH,
                {
                    "query": query,
                    "provider": "multi_search",
                    "results": support._compact_sources(results, limit=min(len(results), 5)),
                    "count": len(results),
                    "engine": "multi_agent",
                },
            )
        return results

    def _bootstrap_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "bootstrap")
        view._check_cancel()

        requeued = view.task_queue.requeue_in_progress(reason="checkpoint_resume")
        for task in requeued:
            view._emit_task_update(
                task=task,
                status=task.status,
                attempt=task.attempts,
                reason="checkpoint_resume",
            )

        briefs = view.artifact_store.branch_briefs()
        root_brief = next((brief for brief in briefs if brief.id == view.root_branch_id), None)
        if root_brief is None:
            root_brief = briefs[0] if briefs else None
        if root_brief is None:
            root_brief = BranchBrief(
                id=support._new_id("brief"),
                topic=self.topic,
                summary=f"围绕主题“{self.topic}”开展多 agent Deep Research。",
            )
            view.artifact_store.put_brief(root_brief)
            view._emit_artifact_update(
                artifact_id=root_brief.id,
                artifact_type="branch_brief",
                status=root_brief.status,
                summary=root_brief.summary,
            )
        view.root_branch_id = root_brief.id
        next_step = self._initial_next_step(
            view.task_queue.snapshot(),
            view.artifact_store.snapshot(),
            view.runtime_state,
        )
        planning_mode = str(graph_state.get("planning_mode") or view.runtime_state.get("planning_mode") or "").strip()
        if next_step == "supervisor_plan" and not planning_mode:
            planning_mode = "initial"
        return view.snapshot_patch(next_step=next_step, planning_mode=planning_mode)

    def _route_after_bootstrap(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "clarify").strip().lower()
        if next_step in {
            "clarify",
            "scope",
            "scope_review",
            "research_brief",
            "supervisor_plan",
            "dispatch",
            "verify",
            "supervisor_decide",
            "outline_gate",
            "report",
            "finalize",
        }:
            return next_step
        return "supervisor_plan"

    def _clarify_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "clarify")
        record = view.start_agent_run(
            role="clarify",
            phase="intake",
            branch_id=view.root_branch_id,
            attempt=view.graph_attempt,
        )
        try:
            clarify_answers = list(view.runtime_state.get("clarify_answer_history") or [])
            clarify_transcript = _build_clarify_transcript(
                list(view.runtime_state.get("clarify_question_history") or []),
                clarify_answers,
            )
            result = self.clarifier.assess_intake(
                self.topic,
                clarify_answers=clarify_answers,
                clarify_history=clarify_transcript,
            )
            intake_summary = copy.deepcopy(result.get("intake_summary") or {})
            if intake_summary:
                view.runtime_state["intake_summary"] = intake_summary

            question = str(result.get("question") or "").strip()
            missing_information = _coerce_string_list(result.get("missing_information"))
            needs_clarification = bool(result.get("needs_clarification"))

            if (
                needs_clarification
                and question
                and self.allow_interrupts
                and len(clarify_answers) < self.max_clarify_rounds
            ):
                prompt = {
                    "checkpoint": "deep_research_clarify",
                    "message": question,
                    "instruction": "Answer the clarification question so Deep Research can draft the scope.",
                    "question": question,
                    "content": "",
                    "graph_run_id": view.graph_run_id,
                    "graph_attempt": view.graph_attempt,
                    "missing_information": missing_information,
                    "intake_summary": intake_summary,
                    "available_actions": ["answer_clarification"],
                }
                view._emit_decision(
                    decision_type="clarify_required",
                    reason=question,
                    attempt=view.graph_attempt,
                    extra={
                        "missing_information": missing_information,
                    },
                )
                view.finish_agent_run(
                    record,
                    status="completed",
                    summary=question,
                    branch_id=view.root_branch_id,
                )
                updated = interrupt(prompt)
                answer = _extract_interrupt_text(
                    updated,
                    keys=("clarify_answer", "answer", "content", "feedback"),
                )
                if not answer:
                    raise ValueError("deep_research clarify resume requires non-empty clarify_answer")
                question_history = list(view.runtime_state.get("clarify_question_history") or [])
                question_history.append(question)
                answer_history = list(view.runtime_state.get("clarify_answer_history") or [])
                answer_history.append(answer)
                view.runtime_state["clarify_question"] = question
                view.runtime_state["clarify_question_history"] = question_history
                view.runtime_state["clarify_answer_history"] = answer_history
                view.runtime_state["intake_status"] = "pending"
                return view.snapshot_patch(next_step="clarify")

            if needs_clarification and question:
                reason = (
                    f"{question} (interrupts unavailable or clarify round limit reached; continuing with best-effort scope)"
                )
            else:
                reason = "intake information is sufficient for scope drafting"
            view.runtime_state["clarify_question"] = ""
            view.runtime_state["intake_status"] = "ready_for_scope"
            view._emit_decision(
                decision_type="scope_ready",
                reason=reason,
                attempt=view.graph_attempt,
                extra={
                    "intake_summary": intake_summary,
                },
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=str(intake_summary.get("research_goal") or reason)[:240],
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step="scope")
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                branch_id=view.root_branch_id,
            )
            raise

    def _route_after_clarify(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "scope").strip().lower()
        if next_step in {"clarify", "scope"}:
            return next_step
        return "scope"

    def _scope_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "scope")
        record = view.start_agent_run(
            role="scope",
            phase="draft_scope",
            branch_id=view.root_branch_id,
            attempt=view.graph_attempt,
        )
        try:
            intake_summary = copy.deepcopy(view.runtime_state.get("intake_summary") or {})
            current_scope_payload = copy.deepcopy(view.runtime_state.get("current_scope_draft") or {})
            pending_feedback = str(view.runtime_state.get("pending_scope_feedback") or "").strip()
            clarify_transcript = _build_clarify_transcript(
                list(view.runtime_state.get("clarify_question_history") or []),
                list(view.runtime_state.get("clarify_answer_history") or []),
            )
            current_scope = _scope_draft_from_payload(current_scope_payload)
            next_version = 1
            if current_scope:
                next_version = current_scope.version + 1 if pending_feedback else current_scope.version

            scope_payload = self.scope_agent.create_scope(
                self.topic,
                intake_summary=intake_summary,
                previous_scope=current_scope_payload if pending_feedback else {},
                scope_feedback=pending_feedback,
                clarify_transcript=clarify_transcript,
            )
            scope_draft = _build_scope_draft(
                topic=self.topic,
                version=next_version,
                draft_payload=scope_payload,
                intake_summary=intake_summary,
                feedback=pending_feedback,
                agent_id=record.agent_id,
                previous=current_scope_payload if pending_feedback else None,
            )

            view.runtime_state["current_scope_draft"] = scope_draft.to_dict()
            view.runtime_state["pending_scope_feedback"] = ""
            view.runtime_state["scope_revision_count"] = max(0, scope_draft.version - 1)
            view.runtime_state["intake_status"] = "awaiting_scope_review"

            decision_type = "scope_revision_requested" if pending_feedback else "scope_ready"
            decision_reason = (
                pending_feedback
                if pending_feedback
                else "structured scope draft is ready for user review"
            )
            view._emit_decision(
                decision_type=decision_type,
                reason=decision_reason,
                attempt=view.graph_attempt,
                extra={
                    "scope_version": scope_draft.version,
                },
            )
            view._emit_artifact_update(
                artifact_id=scope_draft.id,
                artifact_type="scope_draft",
                status=scope_draft.status,
                agent_id=scope_draft.created_by,
                summary=scope_draft.research_goal[:180],
                extra={
                    "scope_version": scope_draft.version,
                    "review_state": scope_draft.status,
                    "content": _format_scope_draft_markdown(scope_draft),
                },
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=scope_draft.research_goal[:240],
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step="scope_review")
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                branch_id=view.root_branch_id,
            )
            raise

    def _scope_review_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "scope_review")
        current_scope_payload = copy.deepcopy(view.runtime_state.get("current_scope_draft") or {})
        scope_draft = _scope_draft_from_payload(current_scope_payload)
        if not scope_draft:
            return view.snapshot_patch(next_step="scope")

        if not self.allow_interrupts:
            approved_payload = scope_draft.to_dict()
            approved_payload["status"] = "approved"
            approved_payload["updated_at"] = _now_iso()
            view.runtime_state["current_scope_draft"] = copy.deepcopy(approved_payload)
            view.runtime_state["approved_scope_draft"] = copy.deepcopy(approved_payload)
            view.runtime_state["intake_status"] = "scope_approved"
            view.runtime_state["research_brief_id"] = ""
            view._emit_decision(
                decision_type="scope_approved",
                reason="interrupts disabled; auto-approving current scope draft",
                attempt=view.graph_attempt,
                extra={"scope_version": scope_draft.version},
            )
            view._emit_artifact_update(
                artifact_id=scope_draft.id,
                artifact_type="scope_draft",
                status="approved",
                agent_id=scope_draft.created_by,
                summary=scope_draft.research_goal[:180],
                extra={
                    "scope_version": scope_draft.version,
                    "review_state": "approved",
                    "content": _format_scope_draft_markdown(approved_payload),
                },
            )
            return view.snapshot_patch(next_step="research_brief")

        prompt = {
            "checkpoint": "deep_research_scope_review",
            "message": "Review the proposed Deep Research scope.",
            "instruction": (
                "Approve the current scope draft to start research, or provide natural-language feedback "
                "to request a rewrite. Direct field edits are not accepted."
            ),
            "graph_run_id": view.graph_run_id,
            "graph_attempt": view.graph_attempt,
            "scope_draft": scope_draft.to_dict(),
            "scope_version": scope_draft.version,
            "scope_revision_count": int(view.runtime_state.get("scope_revision_count", 0) or 0),
            "content": _format_scope_draft_markdown(scope_draft),
            "available_actions": ["approve_scope", "revise_scope"],
            "allow_direct_edit": False,
        }
        updated = interrupt(prompt)
        if isinstance(updated, dict) and any(
            key in updated
            for key in ("scope_draft", "current_scope_draft", "approved_scope_draft", "modifications")
        ):
            raise ValueError(
                "Scope review does not accept direct scope draft edits; submit scope_feedback instead."
            )

        action = ""
        if isinstance(updated, dict):
            action = str(updated.get("action") or updated.get("decision") or "").strip().lower()
        if not action:
            action = (
                "revise_scope"
                if _extract_interrupt_text(updated, keys=("scope_feedback", "feedback", "content"))
                else "approve_scope"
            )

        if action == "approve_scope":
            approved_payload = scope_draft.to_dict()
            approved_payload["status"] = "approved"
            approved_payload["updated_at"] = _now_iso()
            view.runtime_state["current_scope_draft"] = copy.deepcopy(approved_payload)
            view.runtime_state["approved_scope_draft"] = copy.deepcopy(approved_payload)
            view.runtime_state["intake_status"] = "scope_approved"
            view.runtime_state["research_brief_id"] = ""
            view._emit_decision(
                decision_type="scope_approved",
                reason="user approved the current scope draft",
                attempt=view.graph_attempt,
                extra={"scope_version": scope_draft.version},
            )
            view._emit_artifact_update(
                artifact_id=scope_draft.id,
                artifact_type="scope_draft",
                status="approved",
                agent_id=scope_draft.created_by,
                summary=scope_draft.research_goal[:180],
                extra={
                    "scope_version": scope_draft.version,
                    "review_state": "approved",
                    "content": _format_scope_draft_markdown(approved_payload),
                },
            )
            return view.snapshot_patch(next_step="research_brief")

        if action != "revise_scope":
            raise ValueError(f"Unsupported scope review action: {action}")

        scope_feedback = _extract_interrupt_text(
            updated,
            keys=("scope_feedback", "feedback", "content"),
        )
        if not scope_feedback:
            raise ValueError("revise_scope requires non-empty scope_feedback")
        feedback_history = list(view.runtime_state.get("scope_feedback_history") or [])
        feedback_history.append(
            {
                "scope_version": scope_draft.version,
                "feedback": scope_feedback,
                "at": _now_iso(),
            }
        )
        view.runtime_state["scope_feedback_history"] = feedback_history
        view.runtime_state["pending_scope_feedback"] = scope_feedback
        view.runtime_state["intake_status"] = "scope_revision_requested"
        view._emit_decision(
            decision_type="scope_revision_requested",
            reason=scope_feedback,
            attempt=view.graph_attempt,
            extra={"scope_version": scope_draft.version},
        )
        view._emit_artifact_update(
            artifact_id=scope_draft.id,
            artifact_type="scope_draft",
            status="revision_requested",
            agent_id=scope_draft.created_by,
            summary=scope_feedback[:180],
            extra={
                "scope_version": scope_draft.version,
                "review_state": "revision_requested",
                "content": _format_scope_draft_markdown(scope_draft),
            },
        )
        return view.snapshot_patch(next_step="scope")

    def _route_after_scope_review(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "research_brief").strip().lower()
        if next_step in {"scope", "research_brief"}:
            return next_step
        return "research_brief"

    def _research_brief_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "research_brief")
        approved_scope = copy.deepcopy(view.runtime_state.get("approved_scope_draft") or {})
        if not approved_scope:
            return view.snapshot_patch(next_step="scope_review")
        record = view.start_agent_run(
            role="scope",
            phase="research_brief_handoff",
            branch_id=view.root_branch_id,
            attempt=view.graph_attempt,
        )
        try:
            existing = view.artifact_store.research_brief()
            research_brief = _build_research_brief(
                topic=self.topic,
                approved_scope=approved_scope,
                intake_summary=copy.deepcopy(view.runtime_state.get("intake_summary") or {}),
                existing_id=existing.id if existing else None,
            )
            view.artifact_store.set_research_brief(research_brief)
            view.runtime_state["research_brief_id"] = research_brief.id
            view.runtime_state["intake_status"] = "brief_ready"
            view._emit_artifact_update(
                artifact_id=research_brief.id,
                artifact_type="research_brief",
                status=research_brief.status,
                branch_id=view.root_branch_id,
                agent_id=research_brief.created_by,
                summary=research_brief.research_goal[:180],
                stage="research_brief",
                extra={
                    "scope_id": research_brief.scope_id,
                    "scope_version": research_brief.scope_version,
                    "coverage_dimensions": list(research_brief.coverage_dimensions),
                },
            )
            view.sync_task_ledger(reason="research brief 已生成，初始化 task ledger", created_by="scope")
            view.sync_progress_ledger(
                phase="research_brief",
                reason="approved scope 已转换为权威 research brief",
                created_by="scope",
                outline_status="pending",
            )
            view._emit_decision(
                decision_type="research_brief_ready",
                reason="approved scope 已转换为结构化 research brief",
                attempt=view.graph_attempt,
                extra={
                    "research_brief_id": research_brief.id,
                    "scope_id": research_brief.scope_id,
                    "scope_version": research_brief.scope_version,
                },
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=research_brief.research_goal[:240],
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step="supervisor_plan")
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                branch_id=view.root_branch_id,
            )
            raise

    def _supervisor_plan_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "supervisor_plan")
        approved_scope = copy.deepcopy(view.runtime_state.get("approved_scope_draft") or {})
        if not approved_scope:
            return view.snapshot_patch(next_step="scope_review")
        research_brief = view.artifact_store.research_brief()
        if research_brief is None:
            return view.snapshot_patch(next_step="research_brief")
        planning_mode = str(graph_state.get("planning_mode") or view.runtime_state.get("planning_mode") or "initial")
        phase = "replan" if planning_mode == "replan" else "initial_plan"
        record = view.start_agent_run(
            role="supervisor",
            phase=phase,
            branch_id=view.root_branch_id,
            iteration=view.current_iteration or None,
            attempt=view.graph_attempt,
        )
        try:
            existing_objectives = [
                task.objective or task.title or task.goal
                for task in view.task_queue.all_tasks()
                if (task.objective or task.title or task.goal)
            ]
            task_ledger = view.artifact_store.task_ledger()
            progress_ledger = view.artifact_store.progress_ledger()
            if planning_mode == "replan":
                gap_result = _gap_result_from_payload(
                    graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
                )
                gap_labels = [gap.aspect for gap in gap_result.gaps] if gap_result else []
                plan_items = self.supervisor.refine_plan(
                    self.topic,
                    gaps=gap_labels,
                    existing_queries=existing_objectives,
                    num_queries=min(
                        self.query_num,
                        max(1, len(gap_result.suggested_queries) if gap_result else 1),
                    ),
                    approved_scope=research_brief.to_dict(),
                )
                context_id = str(research_brief.id or f"replan-{view.current_iteration or 0}")
            else:
                plan_items = self.supervisor.create_plan(
                    self.topic,
                    num_queries=self.query_num,
                    existing_knowledge=view._knowledge_summary(),
                    existing_queries=existing_objectives,
                    approved_scope=research_brief.to_dict(),
                )
                context_id = str(research_brief.id or view.root_branch_id or support._new_id("brief"))

            tasks = dispatcher.build_tasks_from_plan(
                view,
                plan_items,
                context_id=context_id,
                branch_id=view.root_branch_id,
            )
            if not tasks:
                terminal_reason = (
                    "结构化验证仍存在缺口，但重规划未生成新的 branch 研究任务，Deep Research 在当前约束下无法继续收敛"
                    if planning_mode == "replan"
                    else "research brief 已就绪，但未生成任何可执行的 branch 研究任务"
                )
                view.set_terminal_state(status="blocked", reason=terminal_reason)
                decision_type = "stop"
                view._emit_decision(
                    decision_type=decision_type,
                    reason=terminal_reason,
                    iteration=view.current_iteration or None,
                    attempt=view.graph_attempt,
                )
                decision_artifact = view.record_supervisor_decision(
                    phase=phase,
                    decision_type=decision_type,
                    summary=terminal_reason,
                    next_step="finalize",
                    planning_mode="",
                    request_ids=list(view.runtime_state.get("supervisor_request_ids") or []),
                    metadata={
                        "scope_id": approved_scope.get("id"),
                        "scope_version": approved_scope.get("version"),
                        "research_brief_id": research_brief.id,
                        "task_count": 0,
                    },
                )
                view.sync_task_ledger(
                    reason="supervisor 未生成新的 branch 任务，保留当前 ledger 供终态诊断",
                    created_by="supervisor",
                )
                view.sync_progress_ledger(
                    phase=phase,
                    reason=terminal_reason,
                    created_by="supervisor",
                    decision={
                        "id": decision_artifact.id,
                        "decision_type": decision_type,
                        "reasoning": terminal_reason,
                        "task_ids": [],
                    },
                    outline_status=str(view.runtime_state.get("outline_status") or "pending"),
                    stop_reason=terminal_reason,
                )
                view.runtime_state["supervisor_request_ids"] = []
                view.finish_agent_run(
                    record,
                    status="completed",
                    summary=terminal_reason,
                    iteration=view.current_iteration or None,
                    branch_id=view.root_branch_id,
                )
                return view.snapshot_patch(
                    next_step="finalize",
                    planning_mode="",
                    latest_decision={
                        "id": decision_artifact.id,
                        "decision_type": decision_type,
                        "reasoning": terminal_reason,
                        "next_step": "finalize",
                        "planning_mode": "",
                    },
                )
            if tasks:
                input_ids = [
                    research_brief.id,
                    *( [task_ledger.id] if task_ledger else [] ),
                    *( [progress_ledger.id] if progress_ledger else [] ),
                ]
                for task in tasks:
                    task.input_artifact_ids = _dedupe_texts(list(task.input_artifact_ids) + input_ids)
            if tasks:
                view.task_queue.enqueue(tasks)
                generated_obligations: list[CoverageObligation] = []
                for brief in dispatcher.build_briefs_from_tasks(
                    self.topic,
                    tasks,
                    parent_branch_id=view.root_branch_id,
                    context_id=context_id,
                ):
                    existing_brief = view.artifact_store.get_brief(brief.id)
                    if existing_brief:
                        brief.latest_synthesis_id = existing_brief.latest_synthesis_id
                        brief.latest_verification_id = existing_brief.latest_verification_id
                        brief.verification_status = existing_brief.verification_status
                    view.artifact_store.put_brief(brief)
                    view._emit_artifact_update(
                        artifact_id=brief.id,
                        artifact_type="branch_brief",
                        status=brief.status,
                        branch_id=brief.id,
                        task_id=brief.latest_task_id,
                        summary=brief.summary,
                        task_kind=brief.task_kind,
                        stage=brief.current_stage,
                        iteration=max(1, view.current_iteration + 1),
                        attempt=task.attempts,
                        extra={
                            "objective_summary": brief.objective,
                            "input_artifact_ids": brief.input_artifact_ids,
                        },
                    )
                for task in tasks:
                    revision_brief = None
                    if task.revision_brief_id:
                        revision_brief = next(
                            (
                                item
                                for item in view.artifact_store.revision_briefs(target_branch_id=task.branch_id)
                                if item.id == task.revision_brief_id
                            ),
                            None,
                        )
                    obligations = derive_coverage_obligations(
                        research_brief=research_brief,
                        task=task,
                        branch_id=task.branch_id,
                        revision_brief=revision_brief,
                        created_by="supervisor",
                    )
                    generated_obligations.extend(obligations)
                if generated_obligations:
                    view.artifact_store.add_coverage_obligations(generated_obligations)
                    obligations_by_task: dict[str, list[str]] = defaultdict(list)
                    for obligation in generated_obligations:
                        obligations_by_task[obligation.task_id].append(obligation.id)
                        branch_task = next((task for task in tasks if task.id == obligation.task_id), None)
                        view._emit_artifact_update(
                            artifact_id=obligation.id,
                            artifact_type="coverage_obligation",
                            status=obligation.status,
                            task_id=obligation.task_id,
                            branch_id=obligation.branch_id,
                            agent_id=obligation.created_by,
                            summary=obligation.target[:180],
                            task_kind=branch_task.task_kind if branch_task else None,
                            stage="dispatch",
                            attempt=branch_task.attempts if branch_task else view.graph_attempt,
                            extra={
                                "completion_criteria": list(obligation.completion_criteria),
                                "source": obligation.source,
                            },
                        )
                    for task in tasks:
                        if not task.branch_id:
                            continue
                        brief = view.artifact_store.get_brief(task.branch_id)
                        if brief is None:
                            continue
                        brief.obligation_ids = obligations_by_task.get(task.id, [])
                        view.artifact_store.put_brief(brief)
                for task in tasks:
                    view._emit_task_update(
                        task=task,
                        status=task.status,
                        iteration=max(1, view.current_iteration + 1),
                        attempt=task.attempts,
                    )
                view._emit_deep_research_topology_update()
            plan_snapshot = {
                "id": support._new_id("supervisor_plan"),
                "phase": phase,
                "approved_scope_id": str(approved_scope.get("id") or ""),
                "research_brief_id": research_brief.id,
                "task_ids": [task.id for task in tasks],
                "request_ids": list(view.runtime_state.get("supervisor_request_ids") or []),
                "created_at": _now_iso(),
            }
            view.runtime_state["supervisor_phase"] = phase
            view.runtime_state["supervisor_plan"] = plan_snapshot
            decision_type = "supervisor_replan" if planning_mode == "replan" else "supervisor_plan"
            decision_summary = f"生成 {len(tasks)} 个 branch 研究任务"
            view._emit_decision(
                decision_type=decision_type,
                reason=decision_summary,
                iteration=view.current_iteration or None,
                attempt=view.graph_attempt,
                extra={
                    "task_ids": [task.id for task in tasks],
                    "scope_id": approved_scope.get("id"),
                    "scope_version": approved_scope.get("version"),
                    "research_brief_id": research_brief.id,
                },
            )
            decision_artifact = view.record_supervisor_decision(
                phase=phase,
                decision_type=decision_type,
                summary=decision_summary,
                next_step="dispatch",
                planning_mode="",
                task_ids=[task.id for task in tasks],
                request_ids=list(view.runtime_state.get("supervisor_request_ids") or []),
                metadata={
                    "scope_id": approved_scope.get("id"),
                    "scope_version": approved_scope.get("version"),
                    "research_brief_id": research_brief.id,
                    "task_count": len(tasks),
                },
            )
            view.sync_task_ledger(
                reason="supervisor 已根据 research brief 生成/更新 branch 任务",
                created_by="supervisor",
            )
            view.sync_progress_ledger(
                phase=phase,
                reason=decision_summary,
                created_by="supervisor",
                decision={
                    "id": decision_artifact.id,
                    "decision_type": decision_type,
                    "reasoning": decision_summary,
                    "task_ids": [task.id for task in tasks],
                },
            )
            view.runtime_state["supervisor_request_ids"] = []
            view.finish_agent_run(
                record,
                status="completed",
                summary=decision_summary,
                iteration=view.current_iteration or None,
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(
                next_step="dispatch",
                planning_mode="",
                latest_decision={
                    "id": decision_artifact.id,
                    "decision_type": decision_type,
                    "reasoning": decision_summary,
                },
            )
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration or None,
                branch_id=view.root_branch_id,
            )
            raise

    def _dispatch_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "dispatch")
        view.current_iteration += 1
        gap_result = _gap_result_from_payload(
            graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
        )
        view._emit_decision(
            decision_type="research",
            reason="执行当前可调度的研究任务",
            iteration=view.current_iteration,
            coverage=gap_result.overall_coverage if gap_result else None,
            gap_count=len(gap_result.gaps) if gap_result else None,
            attempt=view.graph_attempt,
        )
        pending = dispatcher.claim_ready_task_payloads(view, view.current_iteration)
        if view.budget_stop_reason:
            view._emit_decision(
                decision_type="budget_stop",
                reason=view.budget_stop_reason,
                iteration=view.current_iteration,
                coverage=gap_result.overall_coverage if gap_result else None,
                gap_count=len(gap_result.gaps) if gap_result else None,
                attempt=view.graph_attempt,
            )
        view.sync_task_ledger(reason="进入 dispatch，刷新当前 branch 调度状态", created_by="supervisor")
        view.sync_progress_ledger(
            phase="dispatch",
            reason="supervisor 开始派发当前 ready branch",
            created_by="supervisor",
            decision={
                "decision_type": "dispatch",
                "reasoning": "执行当前可调度的研究任务",
                "pending_worker_count": len(pending),
            },
        )
        return view.snapshot_patch(
            next_step="verify",
            pending_worker_tasks=pending,
            worker_results=[{"__reset__": True}],
        )

    def _route_after_dispatch(self, graph_state: MultiAgentGraphState) -> list[Send] | str:
        payloads = graph_state.get("pending_worker_tasks") or []
        if not payloads:
            return "verify"
        return [Send("researcher", {"worker_task": payload}) for payload in payloads]

    def _route_after_supervisor_plan(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "dispatch").strip().lower()
        if next_step in {"scope_review", "research_brief", "dispatch", "finalize"}:
            return next_step
        return "dispatch"

    def _try_researcher_tool_agent(
        self,
        *,
        view: _RuntimeView,
        task: ResearchTask,
        record: AgentRunRecord,
        worker_context: ResearchWorkerContext,
        objective_summary: str,
        current_stage: str,
        branch_brief: BranchBrief | None,
        iteration: int,
        attempt: int,
    ) -> WorkerExecutionResult | None:
        if not self.enable_tool_agents:
            return None
        session = DeepResearchToolAgentSession(
            runtime=view,
            role="researcher",
            topic=self.topic,
            graph_run_id=view.graph_run_id,
            branch_id=task.branch_id,
            task=task,
            iteration=iteration,
            attempt=attempt,
            allowed_capabilities=set(task.allowed_tools or []),
            approved_scope=copy.deepcopy(view.runtime_state.get("approved_scope_draft") or {}),
            related_artifacts=view.artifact_store.get_related_artifacts(task.id, branch_id=task.branch_id),
        )
        system_prompt = (
            "You are the Deep Research branch researcher.\n"
            "You must stay inside the active branch scope and only use the provided tools.\n"
            "Always inspect task context first, including fabric_get_verification_contracts when revision context exists.\n"
            "Gather evidence with search/read/extract as needed, then call fabric_submit_research_bundle.\n"
            "If blocked, call fabric_request_follow_up instead of inventing facts.\n"
            "When this is a revision task, pass resolved_issue_ids when you have materially addressed them.\n"
            "Finish with a compact JSON object containing summary and result_status."
        )
        user_prompt = (
            f"Topic: {self.topic}\n"
            f"Branch objective: {objective_summary}\n"
            f"Branch summary: {(branch_brief.summary if branch_brief else '')}\n"
            f"Primary query: {task.query}\n"
            f"Query hints: {', '.join(_derive_branch_queries(task))}\n"
            f"Acceptance criteria: {task.acceptance_criteria}\n"
            f"Allowed capabilities: {task.allowed_tools}\n"
            f"Revision kind: {task.revision_kind or 'initial'}\n"
            f"Revision brief id: {task.revision_brief_id or 'n/a'}\n"
            f"Target issue ids: {task.target_issue_ids}\n"
        )
        try:
            run_bounded_tool_agent(
                session,
                model=self.researcher_model,
                allowed_tools=task.allowed_tools,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                config=self.config,
            )
        except Exception:
            return None
        if not session.submissions or session.branch_synthesis is None:
            return None
        claim_units = derive_claim_units(
            claim_verifier=self.claim_verifier,
            task=task,
            synthesis=session.branch_synthesis,
            created_by=record.agent_id,
        )
        session.branch_synthesis.claim_ids = [item.id for item in claim_units]
        session.branch_synthesis.revision_brief_id = task.revision_brief_id
        session.branch_synthesis.metadata.setdefault("addressed_issue_ids", list(task.target_issue_ids))

        worker_context.summary_notes.append(session.branch_synthesis.summary)
        worker_context.scraped_content.append(
            {
                "query": task.query,
                "queries": _derive_branch_queries(task),
                "objective": objective_summary,
                "task_kind": task.task_kind,
                "stage": "submit",
                "results": list(session.search_results),
                "timestamp": _now_iso(),
                "task_id": task.id,
                "agent_id": record.agent_id,
                "attempt": attempt,
                "branch_id": task.branch_id,
                "tool_agent": True,
            }
        )
        worker_context.sources.extend(support._compact_sources(session.search_results, limit=10))
        worker_context.artifacts_created.extend(
            [item.to_dict() for item in session.source_candidates]
            + [item.to_dict() for item in session.fetched_documents]
            + [item.to_dict() for item in session.evidence_passages]
            + [item.to_dict() for item in session.evidence_cards]
            + ([session.branch_synthesis.to_dict()] if session.branch_synthesis else [])
            + ([session.section_draft.to_dict()] if session.section_draft else [])
            + [item.to_dict() for item in session.coordination_requests]
            + [item.to_dict() for item in session.submissions]
        )
        worker_context.is_complete = True
        task.stage = "submit"
        view.finish_agent_run(
            record,
            status="completed",
            summary=session.branch_synthesis.summary[:240],
            iteration=iteration,
            branch_id=task.branch_id,
            stage="submit",
        )
        return WorkerExecutionResult(
            task=task,
            context=worker_context,
            source_candidates=session.source_candidates,
            fetched_documents=session.fetched_documents,
            evidence_passages=session.evidence_passages,
            branch_synthesis=session.branch_synthesis,
            evidence_cards=session.evidence_cards,
            section_draft=session.section_draft,
            coordination_requests=session.coordination_requests,
            submission=session.submissions[-1],
            raw_results=list(session.search_results),
            tokens_used=max(session.tokens_used, support._estimate_tokens_from_text(session.branch_synthesis.summary)),
            searches_used=session.searches_used,
            branch_id=task.branch_id,
            task_stage="submit",
            result_status=session.submissions[-1].result_status,
            agent_run=record,
            claim_units=claim_units,
            resolved_issue_ids=list(session.submissions[-1].resolved_issue_ids),
        )

    def _try_verifier_tool_agent(
        self,
        *,
        view: _RuntimeView,
        task: ResearchTask,
        synthesis: BranchSynthesis,
        validation_stage: str,
        claim_result: VerificationResult | None = None,
        gap_result: GapAnalysisResult | None = None,
        verified_knowledge: str = "",
        claim_units: list[ClaimUnit] | None = None,
        obligations: list[CoverageObligation] | None = None,
    ) -> DeepResearchToolAgentSession | None:
        if not self.enable_tool_agents:
            return None
        related_artifacts = view.artifact_store.get_related_artifacts(task.id, branch_id=synthesis.branch_id)
        if claim_units is not None:
            related_artifacts["claim_units"] = [item.to_dict() for item in claim_units]
        if obligations is not None:
            related_artifacts["coverage_obligations"] = [item.to_dict() for item in obligations]
        session_task = copy.deepcopy(task)
        if validation_stage in {"claim_check", "coverage_check"}:
            session_task.stage = validation_stage
        session = DeepResearchToolAgentSession(
            runtime=view,
            role="verifier",
            topic=self.topic,
            graph_run_id=view.graph_run_id,
            branch_id=synthesis.branch_id,
            task=session_task,
            iteration=view.current_iteration,
            attempt=max(1, int(task.attempts or 1)),
            allowed_capabilities={"search", "read", "extract"},
            approved_scope=copy.deepcopy(view.runtime_state.get("approved_scope_draft") or {}),
            related_artifacts=related_artifacts,
        )
        session.branch_synthesis = copy.deepcopy(synthesis)
        session.claim_units = [copy.deepcopy(item) for item in (claim_units or [])]
        session.source_candidates = [
            SourceCandidate(**item)
            for item in related_artifacts.get("source_candidates", [])
            if isinstance(item, dict)
        ]
        session.fetched_documents = [
            FetchedDocument(**item)
            for item in related_artifacts.get("fetched_documents", [])
            if isinstance(item, dict)
        ]
        session.evidence_passages = [
            EvidencePassage(**item)
            for item in related_artifacts.get("evidence_passages", [])
            if isinstance(item, dict)
        ]
        session.evidence_cards = [
            EvidenceCard(**item)
            for item in related_artifacts.get("evidence_cards", [])
            if isinstance(item, dict)
        ]

        system_prompt = (
            "You are the Deep Research verifier.\n"
            "Work only inside the active branch and only use the provided tools.\n"
            "Inspect the current task and related artifacts first.\n"
            "Use fabric_get_verification_contracts to inspect structured claims, obligations and issues first.\n"
            "Use fabric_challenge_summary for claim checks, fabric_compare_coverage for coverage checks, "
            "and search/read/extract only when you need extra evidence.\n"
            "If you need to request follow-up work, only use registered request types: "
            "retry_branch, need_counterevidence, contradiction_found, blocked_by_tooling.\n"
            "Always finish by calling fabric_submit_verification_bundle.\n"
            "Claim checks MUST submit claim_ids.\n"
            "Coverage checks MUST submit obligation_ids.\n"
            "Consistency checks MUST submit consistency_result_ids.\n"
            "If you reference an existing issue, include issue_ids.\n"
            "Do not submit blanket passed verdicts that are not bound to concrete contracts.\n"
            "Return a compact JSON object with validation_stage, outcome, summary and recommended_action."
        )
        user_prompt = (
            f"Topic: {self.topic}\n"
            f"Validation stage: {validation_stage}\n"
            f"Branch objective: {task.objective or task.title or task.goal}\n"
            f"Acceptance criteria: {task.acceptance_criteria}\n"
            f"Branch summary: {synthesis.summary}\n"
            f"Citation URLs: {synthesis.citation_urls}\n"
            f"Claim ids: {synthesis.claim_ids}\n"
            f"Revision brief id: {task.revision_brief_id or 'n/a'}\n"
            f"Target issue ids: {task.target_issue_ids}\n"
            f"Prior claim outcome: {(claim_result.outcome if claim_result else 'n/a')}\n"
            f"Coverage analysis: {(gap_result.analysis if gap_result else '')}\n"
            f"Suggested follow-up queries: {(gap_result.suggested_queries if gap_result else [])}\n"
            f"Verified knowledge so far: {verified_knowledge[:1200]}\n"
        )
        try:
            run_bounded_tool_agent(
                session,
                model=self.verifier_model,
                allowed_tools=None,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                config=self.config,
            )
        except Exception:
            return None
        if not session.verification_results or not session.submissions:
            return None
        result = session.verification_results[-1]
        if result.validation_stage != validation_stage:
            return None
        if validation_stage == "coverage_check" and gap_result and "gap_analysis" not in result.metadata:
            result.metadata["gap_analysis"] = gap_result.analysis
        return session

    def _persist_verifier_tool_agent_session(
        self,
        *,
        view: _RuntimeView,
        task_map: dict[str, ResearchTask],
        validation_stage: str,
        source_candidates: list[SourceCandidate],
        fetched_documents: list[FetchedDocument],
        evidence_passages: list[EvidencePassage],
        evidence_cards: list[EvidenceCard],
        verification_results: list[VerificationResult],
        coordination_requests: list[CoordinationRequest],
        submissions: list[ResearchSubmission],
    ) -> None:
        existing_source_ids = {item.id for item in view.artifact_store.source_candidates()}
        existing_document_ids = {item.id for item in view.artifact_store.fetched_documents()}
        existing_passage_ids = {item.id for item in view.artifact_store.evidence_passages()}
        existing_card_ids = {item.id for item in view.artifact_store.evidence_cards()}
        source_candidates = [item for item in source_candidates if item.id not in existing_source_ids]
        fetched_documents = [item for item in fetched_documents if item.id not in existing_document_ids]
        evidence_passages = [item for item in evidence_passages if item.id not in existing_passage_ids]
        evidence_cards = [item for item in evidence_cards if item.id not in existing_card_ids]
        if source_candidates:
            view.artifact_store.add_source_candidates(source_candidates)
            for candidate in source_candidates:
                branch_task = task_map.get(candidate.task_id)
                artifact_attempt = branch_task.attempts if branch_task else view.graph_attempt
                view._emit_artifact_update(
                    artifact_id=candidate.id,
                    artifact_type="source_candidate",
                    status=candidate.status,
                    task_id=candidate.task_id,
                    branch_id=candidate.branch_id,
                    agent_id=candidate.created_by,
                    summary=candidate.summary[:180],
                    source_url=candidate.url,
                    task_kind=branch_task.task_kind if branch_task else None,
                    stage="search",
                    validation_stage=validation_stage,
                    attempt=artifact_attempt,
                )
        if fetched_documents:
            view.artifact_store.add_fetched_documents(fetched_documents)
            for document in fetched_documents:
                branch_task = task_map.get(document.task_id)
                artifact_attempt = branch_task.attempts if branch_task else view.graph_attempt
                view._emit_artifact_update(
                    artifact_id=document.id,
                    artifact_type="fetched_document",
                    status=document.status,
                    task_id=document.task_id,
                    branch_id=document.branch_id,
                    agent_id=document.created_by,
                    summary=document.title[:180] or document.excerpt[:180],
                    source_url=document.url,
                    task_kind=branch_task.task_kind if branch_task else None,
                    stage="read",
                    validation_stage=validation_stage,
                    attempt=artifact_attempt,
                )
        if evidence_passages:
            view.artifact_store.add_evidence_passages(evidence_passages)
            for passage in evidence_passages:
                branch_task = task_map.get(passage.task_id)
                artifact_attempt = branch_task.attempts if branch_task else view.graph_attempt
                view._emit_artifact_update(
                    artifact_id=passage.id,
                    artifact_type="evidence_passage",
                    status=passage.status,
                    task_id=passage.task_id,
                    branch_id=passage.branch_id,
                    agent_id=passage.created_by,
                    summary=passage.quote[:180] or passage.text[:180],
                    source_url=passage.url,
                    task_kind=branch_task.task_kind if branch_task else None,
                    stage="extract",
                    validation_stage=validation_stage,
                    attempt=artifact_attempt,
                )
        if evidence_cards:
            view.artifact_store.add_evidence(evidence_cards)
            for card in evidence_cards:
                branch_task = task_map.get(card.task_id)
                artifact_attempt = branch_task.attempts if branch_task else view.graph_attempt
                view._emit_artifact_update(
                    artifact_id=card.id,
                    artifact_type="evidence_card",
                    status=card.status,
                    task_id=card.task_id,
                    branch_id=card.branch_id,
                    agent_id=card.created_by,
                    summary=card.summary[:180],
                    source_url=card.source_url,
                    task_kind=branch_task.task_kind if branch_task else None,
                    stage="extract",
                    validation_stage=validation_stage,
                    attempt=artifact_attempt,
                )
        if verification_results:
            view.artifact_store.add_verification_results(verification_results)
            for result in verification_results:
                branch_task = task_map.get(result.task_id)
                artifact_attempt = branch_task.attempts if branch_task else view.graph_attempt
                view._emit_artifact_update(
                    artifact_id=result.id,
                    artifact_type="verification_result",
                    status=result.status,
                    task_id=result.task_id,
                    branch_id=result.branch_id,
                    agent_id=result.created_by,
                    summary=result.summary,
                    task_kind=branch_task.task_kind if branch_task else None,
                    stage=validation_stage,
                    validation_stage=result.validation_stage,
                    attempt=artifact_attempt,
                    extra={
                        "outcome": result.outcome,
                        "recommended_action": result.recommended_action,
                        "gap_ids": list(result.gap_ids),
                        "claim_ids": list(result.metadata.get("claim_ids", [])),
                        "obligation_ids": list(result.metadata.get("obligation_ids", [])),
                        "consistency_result_ids": list(result.metadata.get("consistency_result_ids", [])),
                        "issue_ids": list(result.metadata.get("issue_ids", [])),
                    },
                )
                if result.branch_id:
                    brief = view.artifact_store.get_brief(result.branch_id)
                    if brief:
                        brief.latest_verification_id = result.id
                        brief.current_stage = validation_stage
                        brief.verification_status = result.outcome
                        view.artifact_store.put_brief(brief)
        if coordination_requests:
            view.artifact_store.add_coordination_requests(coordination_requests)
            for request in coordination_requests:
                branch_task = task_map.get(request.task_id or "")
                artifact_attempt = branch_task.attempts if branch_task else view.graph_attempt
                view._emit_artifact_update(
                    artifact_id=request.id,
                    artifact_type="coordination_request",
                    status=request.status,
                    task_id=request.task_id,
                    branch_id=request.branch_id,
                    agent_id=request.requested_by,
                    summary=request.summary[:180],
                    task_kind=branch_task.task_kind if branch_task else None,
                    stage=validation_stage,
                    validation_stage=validation_stage,
                    attempt=artifact_attempt,
                    extra={
                        "request_type": request.request_type,
                        "artifact_ids": list(request.artifact_ids),
                        "suggested_queries": list(request.suggested_queries),
                    },
                )
        if submissions:
            view.artifact_store.add_submissions(submissions)
            for submission in submissions:
                branch_task = task_map.get(submission.task_id or "")
                artifact_attempt = branch_task.attempts if branch_task else view.graph_attempt
                view._emit_artifact_update(
                    artifact_id=submission.id,
                    artifact_type="verification_submission",
                    status=submission.status,
                    task_id=submission.task_id,
                    branch_id=submission.branch_id,
                    agent_id=submission.created_by,
                    summary=submission.summary[:180],
                    task_kind=branch_task.task_kind if branch_task else None,
                    stage=submission.stage or validation_stage,
                    validation_stage=submission.validation_stage or validation_stage,
                    attempt=artifact_attempt,
                    extra={
                        "submission_kind": submission.submission_kind,
                        "result_status": submission.result_status,
                        "artifact_ids": list(submission.artifact_ids),
                        "request_ids": list(submission.request_ids),
                        "claim_ids": list(submission.claim_ids),
                        "obligation_ids": list(submission.obligation_ids),
                        "consistency_result_ids": list(submission.consistency_result_ids),
                        "issue_ids": list(submission.issue_ids),
                    },
                )

    def _try_reporter_tool_agent(
        self,
        *,
        view: _RuntimeView,
        verified_syntheses: list[BranchSynthesis],
        citation_urls: list[str],
        outline_artifact: OutlineArtifact,
    ) -> DeepResearchToolAgentSession | None:
        if not self.enable_tool_agents:
            return None
        session = DeepResearchToolAgentSession(
            runtime=view,
            role="reporter",
            topic=self.topic,
            graph_run_id=view.graph_run_id,
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
            allowed_capabilities=set(),
            approved_scope=copy.deepcopy(view.runtime_state.get("approved_scope_draft") or {}),
            related_artifacts={
                "outline": outline_artifact.to_dict(),
                "branch_syntheses": [item.to_dict() for item in verified_syntheses],
                "verification_results": [
                    item.to_dict()
                    for item in view.artifact_store.verification_results()
                ],
                "coverage_matrix": (
                    view.artifact_store.coverage_matrix().to_dict()
                    if view.artifact_store.coverage_matrix()
                    else {}
                ),
                "contradiction_registry": (
                    view.artifact_store.contradiction_registry().to_dict()
                    if view.artifact_store.contradiction_registry()
                    else {}
                ),
                "missing_evidence_list": (
                    view.artifact_store.missing_evidence_list().to_dict()
                    if view.artifact_store.missing_evidence_list()
                    else {}
                ),
                "research_brief": (
                    view.artifact_store.research_brief().to_dict()
                    if view.artifact_store.research_brief()
                    else {}
                ),
            },
        )
        outline_lines = "\n".join(
            f"- {section.get('title')}: {section.get('summary', '')[:180]}"
            for section in outline_artifact.sections[:8]
        )
        synthesis_lines = "\n".join(
            f"- {item.objective or item.branch_id or 'branch'}: {item.summary[:280]}"
            for item in verified_syntheses[:8]
        )
        citation_lines = "\n".join(
            f"[{index}] {url}"
            for index, url in enumerate(citation_urls[:20], 1)
        ) or "无来源"
        system_prompt = (
            "You are the Deep Research reporter.\n"
            "Only use the outline artifact and verified branch artifacts from the blackboard.\n"
            "Read the outline first, then expand it into the final report.\n"
            "Use fabric_get_verified_branch_summaries to inspect the final evidence base.\n"
            "Use fabric_get_outline_artifact to inspect the report structure gate.\n"
            "Use fabric_format_report_section when helpful, then call fabric_submit_report_bundle.\n"
            "Do not introduce facts that are not supported by verified artifacts.\n"
            "Write a long-form report with inline [n] citations and a closing Sources section.\n"
            "Return a compact JSON object with report_markdown, executive_summary and citation_urls."
        )
        user_prompt = (
            f"Topic: {self.topic}\n"
            f"Outline sections:\n{outline_lines}\n"
            f"Verified branch count: {len(verified_syntheses)}\n"
            f"Verified synthesis previews:\n{synthesis_lines}\n"
            f"Citation map:\n{citation_lines}\n"
        )
        try:
            run_bounded_tool_agent(
                session,
                model=self.reporter_model,
                allowed_tools=None,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                config=self.config,
            )
        except Exception:
            return None
        if session.final_report is None or not session.submissions:
            return None
        return session

    def _researcher_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "researcher")
        payload = graph_state.get("worker_task") or {}
        task_payload = payload.get("task") if isinstance(payload, dict) else None
        task = ResearchTask(**task_payload) if isinstance(task_payload, dict) else ResearchTask(**payload)
        branch_id = task.branch_id or payload.get("branch_id") or view.root_branch_id
        iteration = int(payload.get("iteration") or view.current_iteration or 0)
        attempt = int(payload.get("attempt") or task.attempts or 1)
        objective_summary = task.objective or task.title or task.goal
        record = view.start_agent_run(
            role="researcher",
            phase="branch_research",
            task_id=task.id,
            branch_id=branch_id,
            iteration=iteration,
            attempt=attempt,
            task_kind=task.task_kind,
            stage="search",
            objective_summary=objective_summary,
            persist=False,
        )

        worker_parent_state = copy.deepcopy(view.shared_state)
        branch_brief = view.artifact_store.get_brief(branch_id or "") if branch_id else None
        worker_context = build_research_worker_context(
            worker_parent_state,
            task_id=task.id,
            agent_id=record.agent_id,
            query=task.query,
            topic=self.topic,
            brief={
                "topic": self.topic,
                "goal": task.goal,
                "objective": objective_summary,
                "aspect": task.aspect,
                "task_kind": task.task_kind,
                "acceptance_criteria": list(task.acceptance_criteria),
                "allowed_tools": list(task.allowed_tools),
                "iteration": iteration,
                "stage": "planned",
                "branch_summary": branch_brief.summary if branch_brief else "",
            },
            related_artifacts=view.artifact_store.get_related_artifacts(task.id, branch_id=branch_id),
            scope_id=f"worker-{task.id}-attempt-{attempt}",
            parent_scope_id=branch_id,
        )

        current_stage = "search"

        def _emit_stage(stage: str, *, reason: str = "") -> None:
            nonlocal current_stage
            current_stage = stage
            task.stage = stage
            worker_context.brief["stage"] = stage
            view._emit_task_update(
                task=task,
                status="in_progress",
                iteration=iteration,
                attempt=attempt,
                reason=reason or "",
            )

        try:
            view._check_cancel()
            tool_result = self._try_researcher_tool_agent(
                view=view,
                task=task,
                record=record,
                worker_context=worker_context,
                objective_summary=objective_summary,
                current_stage=current_stage,
                branch_brief=branch_brief,
                iteration=iteration,
                attempt=attempt,
            )
            if tool_result is not None:
                return {"worker_results": [tool_result.to_dict()]}
            _emit_stage("search")
            queries = _derive_branch_queries(task)
            if not queries:
                raise RuntimeError("branch task has no executable query hints")

            results: list[dict[str, Any]] = []
            searches_used = 0
            for query in queries:
                view._check_cancel()
                query_results = self.researcher.execute_queries(
                    [query],
                    max_results_per_query=self.results_per_query,
                )
                if query:
                    searches_used += 1
                for item in query_results:
                    if not isinstance(item, dict):
                        continue
                    results.append({**item, "query": query})

            if not results:
                raise RuntimeError("branch agent returned no evidence")

            _emit_stage("read")
            source_candidates: list[SourceCandidate] = []
            fetched_documents: list[FetchedDocument] = []
            evidence_passages: list[EvidencePassage] = []
            evidence_cards: list[EvidenceCard] = []
            for index, item in enumerate(results[: min(len(results), max(3, self.results_per_query))], 1):
                source_candidate_id = support._new_id("source")
                document_id = support._new_id("document")
                passage_id = support._new_id("passage")
                content = str(
                    item.get("raw_excerpt")
                    or item.get("content")
                    or item.get("summary")
                    or item.get("snippet")
                    or ""
                ).strip()
                summary_text = str(item.get("summary") or item.get("snippet") or content[:280]).strip()
                source_title = str(item.get("title") or item.get("url") or "Untitled")
                source_url = str(item.get("url") or "")
                source_candidates.append(
                    SourceCandidate(
                        id=source_candidate_id,
                        task_id=task.id,
                        branch_id=branch_id,
                        title=source_title,
                        url=source_url,
                        summary=summary_text[:400],
                        rank=index,
                        source_provider=str(item.get("provider") or ""),
                        published_date=item.get("published_date"),
                        created_by=record.agent_id,
                        metadata={
                            "query": str(item.get("query") or task.query or objective_summary),
                            "attempt": attempt,
                            "graph_run_id": view.graph_run_id,
                        },
                    )
                )
                fetched_documents.append(
                    FetchedDocument(
                        id=document_id,
                        task_id=task.id,
                        branch_id=branch_id,
                        source_candidate_id=source_candidate_id,
                        url=source_url,
                        title=source_title,
                        content=content[:2400],
                        excerpt=content[:700],
                        created_by=record.agent_id,
                        metadata={
                            "query": str(item.get("query") or task.query or objective_summary),
                            "attempt": attempt,
                        },
                    )
                )
                evidence_passages.append(
                    EvidencePassage(
                        id=passage_id,
                        task_id=task.id,
                        branch_id=branch_id,
                        document_id=document_id,
                        url=source_url,
                        text=content[:900],
                        quote=content[:240],
                        source_title=source_title,
                        snippet_hash=f"{task.id}-{index}-{attempt}",
                        created_by=record.agent_id,
                        metadata={
                            "query": str(item.get("query") or task.query or objective_summary),
                            "attempt": attempt,
                        },
                    )
                )
                evidence_cards.append(
                    EvidenceCard(
                        id=support._new_id("evidence"),
                        task_id=task.id,
                        branch_id=branch_id,
                        source_title=source_title,
                        source_url=source_url,
                        summary=summary_text[:280],
                        excerpt=content[:700],
                        source_provider=str(item.get("provider") or ""),
                        published_date=item.get("published_date"),
                        created_by=record.agent_id,
                        metadata={
                            "query": str(item.get("query") or task.query or objective_summary),
                            "attempt": attempt,
                            "graph_run_id": view.graph_run_id,
                            "passage_id": passage_id,
                        },
                    )
                )

            _emit_stage("extract")
            summary = self.researcher.summarize_findings(
                self.topic,
                results,
                existing_summary=view._knowledge_summary(),
            )
            findings = _split_findings(summary)

            _emit_stage("synthesize")
            branch_synthesis = BranchSynthesis(
                id=support._new_id("synthesis"),
                task_id=task.id,
                branch_id=branch_id,
                objective=objective_summary,
                summary=summary or f"未能为“{objective_summary}”形成充分结论。",
                findings=findings,
                acceptance_criteria=list(task.acceptance_criteria),
                evidence_passage_ids=[passage.id for passage in evidence_passages],
                source_document_ids=[document.id for document in fetched_documents],
                citation_urls=[candidate.url for candidate in source_candidates if candidate.url],
                revision_brief_id=task.revision_brief_id,
                created_by=record.agent_id,
                metadata={
                    "query_hints": list(queries),
                    "attempt": attempt,
                    "task_kind": task.task_kind,
                    "graph_run_id": view.graph_run_id,
                    "addressed_issue_ids": list(task.target_issue_ids),
                },
            )
            claim_units = derive_claim_units(
                claim_verifier=self.claim_verifier,
                task=task,
                synthesis=branch_synthesis,
                created_by=record.agent_id,
            )
            branch_synthesis.claim_ids = [item.id for item in claim_units]

            section_draft = ReportSectionDraft(
                id=support._new_id("section"),
                task_id=task.id,
                branch_id=branch_id,
                title=task.title or objective_summary,
                summary=branch_synthesis.summary,
                evidence_ids=[card.id for card in evidence_cards],
                created_by=record.agent_id,
            )

            worker_context.summary_notes.append(branch_synthesis.summary)
            worker_context.scraped_content.append(
                {
                    "query": task.query,
                    "queries": queries,
                    "objective": objective_summary,
                    "task_kind": task.task_kind,
                    "stage": current_stage,
                    "results": results,
                    "timestamp": _now_iso(),
                    "task_id": task.id,
                    "agent_id": record.agent_id,
                    "attempt": attempt,
                    "branch_id": branch_id,
                }
            )
            worker_context.sources.extend(support._compact_sources(results, limit=10))
            worker_context.artifacts_created.extend(
                [candidate.to_dict() for candidate in source_candidates]
                + [document.to_dict() for document in fetched_documents]
                + [passage.to_dict() for passage in evidence_passages]
                + [card.to_dict() for card in evidence_cards]
                + [branch_synthesis.to_dict(), section_draft.to_dict()]
            )
            worker_context.is_complete = True
            submission = ResearchSubmission(
                id=support._new_id("submission"),
                submission_kind="research_bundle",
                summary=branch_synthesis.summary[:240],
                task_id=task.id,
                branch_id=branch_id,
                created_by=record.agent_id,
                result_status="completed",
                stage="submit",
                artifact_ids=[
                    *[candidate.id for candidate in source_candidates],
                    *[document.id for document in fetched_documents],
                    *[passage.id for passage in evidence_passages],
                    *[card.id for card in evidence_cards],
                    branch_synthesis.id,
                    section_draft.id,
                ],
                metadata={
                    "allowed_tools": list(task.allowed_tools),
                    "queries": list(queries),
                    "task_kind": task.task_kind,
                    "addressed_issue_ids": list(task.target_issue_ids),
                    "claim_ids": [item.id for item in claim_units],
                },
            )

            view.finish_agent_run(
                record,
                status="completed",
                summary=branch_synthesis.summary[:240],
                iteration=iteration,
                branch_id=branch_id,
                stage=current_stage,
            )

            result = WorkerExecutionResult(
                task=task,
                context=worker_context,
                source_candidates=source_candidates,
                fetched_documents=fetched_documents,
                evidence_passages=evidence_passages,
                branch_synthesis=branch_synthesis,
                evidence_cards=evidence_cards,
                section_draft=section_draft,
                coordination_requests=[],
                submission=submission,
                raw_results=results,
                tokens_used=support._estimate_tokens_from_results(results)
                + support._estimate_tokens_from_text(summary),
                searches_used=searches_used,
                branch_id=branch_id,
                task_stage=current_stage,
                result_status="completed",
                agent_run=record,
                claim_units=claim_units,
            )
        except Exception as exc:
            worker_context.errors.append(str(exc))
            worker_context.is_complete = True
            retry_request = CoordinationRequest(
                id=support._new_id("request"),
                request_type="retry_branch" if attempt < self.task_retry_limit else "blocked_by_tooling",
                summary=str(exc),
                branch_id=branch_id,
                task_id=task.id,
                requested_by=record.agent_id,
                artifact_ids=[],
                suggested_queries=_derive_branch_queries(task),
                impact_scope=str(branch_id or task.id),
                reason=str(exc),
                blocking_level="blocking",
                suggested_next_action="retry_branch" if attempt < self.task_retry_limit else "supervisor_review",
                metadata={
                    "stage": current_stage,
                    "allowed_tools": list(task.allowed_tools),
                    "task_kind": task.task_kind,
                },
            )
            submission = ResearchSubmission(
                id=support._new_id("submission"),
                submission_kind="research_bundle",
                summary=str(exc),
                task_id=task.id,
                branch_id=branch_id,
                created_by=record.agent_id,
                result_status="failed",
                stage=current_stage,
                request_ids=[retry_request.id],
                metadata={
                    "allowed_tools": list(task.allowed_tools),
                    "task_kind": task.task_kind,
                },
            )
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=iteration,
                branch_id=branch_id,
                stage=current_stage,
            )
            result = WorkerExecutionResult(
                task=task,
                context=worker_context,
                source_candidates=[],
                fetched_documents=[],
                evidence_passages=[],
                branch_synthesis=None,
                evidence_cards=[],
                section_draft=None,
                coordination_requests=[retry_request],
                submission=submission,
                raw_results=[],
                tokens_used=0,
                searches_used=0,
                branch_id=branch_id,
                task_stage=current_stage,
                result_status="failed",
                agent_run=record,
                error=str(exc),
                claim_units=[],
            )

        return {"worker_results": [result.to_dict()]}

    def _merge_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "merge")
        payloads = dispatcher.sort_worker_payloads(graph_state.get("worker_results") or [])
        if self.pause_before_merge and payloads:
            interrupt(
                {
                    "checkpoint": "deep_research_merge",
                    "graph_run_id": view.graph_run_id,
                    "iteration": view.current_iteration,
                    "pending_workers": len(payloads),
                }
            )
        for payload in payloads:
            result = _restore_worker_result(payload)
            updates = merge_research_worker_context(view.shared_state, result.context)
            view.shared_state.update(updates)
            view.searches_used += max(0, result.searches_used)
            view.tokens_used += max(0, result.tokens_used)

            if result.agent_run:
                view.agent_runs.append(result.agent_run)

            if result.coordination_requests:
                view.artifact_store.add_coordination_requests(result.coordination_requests)
                for request in result.coordination_requests:
                    view._emit_artifact_update(
                        artifact_id=request.id,
                        artifact_type="coordination_request",
                        status=request.status,
                        task_id=request.task_id,
                        branch_id=request.branch_id,
                        agent_id=request.requested_by,
                        summary=request.summary[:180],
                        task_kind=result.task.task_kind,
                        stage=result.task_stage or result.task.stage,
                        attempt=result.task.attempts,
                        extra={
                            "request_type": request.request_type,
                            "artifact_ids": list(request.artifact_ids),
                            "suggested_queries": list(request.suggested_queries),
                        },
                    )

            if result.submission:
                view.artifact_store.add_submissions([result.submission])
                view._emit_artifact_update(
                    artifact_id=result.submission.id,
                    artifact_type="research_submission",
                    status=result.submission.status,
                    task_id=result.submission.task_id,
                    branch_id=result.submission.branch_id,
                    agent_id=result.submission.created_by,
                    summary=result.submission.summary[:180],
                    task_kind=result.task.task_kind,
                    stage=result.submission.stage or result.task_stage or result.task.stage,
                    validation_stage=result.submission.validation_stage or None,
                    attempt=result.task.attempts,
                    extra={
                        "submission_kind": result.submission.submission_kind,
                        "result_status": result.submission.result_status,
                        "artifact_ids": list(result.submission.artifact_ids),
                        "request_ids": list(result.submission.request_ids),
                    },
                )

            if result.source_candidates:
                view.artifact_store.add_source_candidates(result.source_candidates)
                for candidate in result.source_candidates:
                    view._emit_artifact_update(
                        artifact_id=candidate.id,
                        artifact_type="source_candidate",
                        status=candidate.status,
                        task_id=candidate.task_id,
                        branch_id=candidate.branch_id,
                        agent_id=candidate.created_by,
                        summary=candidate.summary[:180],
                        source_url=candidate.url,
                        task_kind=result.task.task_kind,
                        stage="search",
                        attempt=result.task.attempts,
                    )

            if result.fetched_documents:
                view.artifact_store.add_fetched_documents(result.fetched_documents)
                for document in result.fetched_documents:
                    view._emit_artifact_update(
                        artifact_id=document.id,
                        artifact_type="fetched_document",
                        status=document.status,
                        task_id=document.task_id,
                        branch_id=document.branch_id,
                        agent_id=document.created_by,
                        summary=document.title[:180] or document.excerpt[:180],
                        source_url=document.url,
                        task_kind=result.task.task_kind,
                        stage="read",
                        attempt=result.task.attempts,
                    )

            if result.evidence_passages:
                view.artifact_store.add_evidence_passages(result.evidence_passages)
                for passage in result.evidence_passages:
                    view._emit_artifact_update(
                        artifact_id=passage.id,
                        artifact_type="evidence_passage",
                        status=passage.status,
                        task_id=passage.task_id,
                        branch_id=passage.branch_id,
                        agent_id=passage.created_by,
                        summary=passage.quote[:180] or passage.text[:180],
                        source_url=passage.url,
                        task_kind=result.task.task_kind,
                        stage="extract",
                        attempt=result.task.attempts,
                    )

            if result.evidence_cards:
                view.artifact_store.add_evidence(result.evidence_cards)
                for card in result.evidence_cards:
                    view._emit_artifact_update(
                        artifact_id=card.id,
                        artifact_type="evidence_card",
                        status=card.status,
                        task_id=card.task_id,
                        branch_id=card.branch_id,
                        agent_id=card.created_by,
                        summary=card.summary[:180],
                        source_url=card.source_url,
                        task_kind=result.task.task_kind,
                        stage="extract",
                        attempt=result.task.attempts,
                    )

            if result.claim_units:
                view.artifact_store.add_claim_units(result.claim_units)
                for claim_unit in result.claim_units:
                    view._emit_artifact_update(
                        artifact_id=claim_unit.id,
                        artifact_type="claim_unit",
                        status=claim_unit.status,
                        task_id=claim_unit.task_id,
                        branch_id=claim_unit.branch_id,
                        agent_id=claim_unit.created_by,
                        summary=claim_unit.claim[:180],
                        task_kind=result.task.task_kind,
                        stage="synthesize",
                        attempt=result.task.attempts,
                        extra={
                            "claim_provenance": copy.deepcopy(claim_unit.claim_provenance),
                            "evidence_passage_ids": list(claim_unit.evidence_passage_ids),
                        },
                    )

            if result.branch_synthesis:
                view.artifact_store.add_branch_synthesis(result.branch_synthesis)
                view._emit_artifact_update(
                    artifact_id=result.branch_synthesis.id,
                    artifact_type="branch_synthesis",
                    status=result.branch_synthesis.status,
                    task_id=result.branch_synthesis.task_id,
                    branch_id=result.branch_synthesis.branch_id,
                    agent_id=result.branch_synthesis.created_by,
                    summary=result.branch_synthesis.summary[:180],
                    task_kind=result.task.task_kind,
                    stage="synthesize",
                    attempt=result.task.attempts,
                    extra={
                        "objective_summary": result.branch_synthesis.objective,
                        "citation_urls": result.branch_synthesis.citation_urls,
                    },
                )

            if result.section_draft:
                view.artifact_store.add_section_draft(result.section_draft)
                view._emit_artifact_update(
                    artifact_id=result.section_draft.id,
                    artifact_type="report_section_draft",
                    status=result.section_draft.status,
                    task_id=result.section_draft.task_id,
                    branch_id=result.section_draft.branch_id,
                    agent_id=result.section_draft.created_by,
                    summary=result.section_draft.summary[:180],
                    task_kind=result.task.task_kind,
                    stage="synthesize",
                    attempt=result.task.attempts,
                )

            if result.branch_id:
                branch_brief = view.artifact_store.get_brief(result.branch_id)
                if branch_brief:
                    branch_brief.latest_task_id = result.task.id
                    branch_brief.current_stage = result.task_stage or result.task.stage or branch_brief.current_stage
                    branch_brief.summary = result.task.title or result.task.objective or branch_brief.summary
                    branch_brief.objective = result.task.objective or branch_brief.objective
                    branch_brief.task_kind = result.task.task_kind or branch_brief.task_kind
                    branch_brief.allowed_tools = list(result.task.allowed_tools or branch_brief.allowed_tools)
                    branch_brief.acceptance_criteria = list(
                        result.task.acceptance_criteria or branch_brief.acceptance_criteria
                    )
                    branch_brief.claim_ids = [item.id for item in result.claim_units]
                    branch_brief.latest_revision_brief_id = (
                        result.task.revision_brief_id or branch_brief.latest_revision_brief_id
                    )
                    branch_brief.open_issue_ids = list(
                        dict.fromkeys(result.task.target_issue_ids + branch_brief.open_issue_ids)
                    )
                    if result.branch_synthesis:
                        branch_brief.latest_synthesis_id = result.branch_synthesis.id
                    branch_brief.verification_status = "pending"
                    view.artifact_store.put_brief(branch_brief)

            if result.raw_results and result.branch_synthesis:
                updated_task = view.task_queue.update_stage(
                    result.task.id,
                    "reported",
                    status="completed",
                )
                if updated_task:
                    view._emit_task_update(
                        task=updated_task,
                        status=updated_task.status,
                        attempt=updated_task.attempts,
                    )
                continue

            reason = result.error or "researcher returned no results"
            if result.task.attempts < self.task_retry_limit and not view.budget_stop_reason:
                failed_task = view.task_queue.update_stage(
                    result.task.id,
                    result.task_stage or result.task.stage or "search",
                    status="failed",
                    reason=reason,
                )
                if failed_task:
                    view._emit_task_update(
                        task=failed_task,
                        status=failed_task.status,
                        attempt=failed_task.attempts,
                        reason=reason,
                    )
                retry_task = view.task_queue.update_stage(
                    result.task.id,
                    "dispatch",
                    status="ready",
                    reason=reason,
                )
                if retry_task:
                    view._emit_task_update(
                        task=retry_task,
                        status=retry_task.status,
                        iteration=view.current_iteration + 1,
                        attempt=retry_task.attempts,
                        reason=reason,
                    )
            else:
                failed_task = view.task_queue.update_stage(
                    result.task.id,
                    result.task_stage or result.task.stage or "search",
                    status="failed",
                    reason=reason,
                )
                if failed_task:
                    view._emit_task_update(
                        task=failed_task,
                        status=failed_task.status,
                        attempt=failed_task.attempts,
                        reason=reason,
                    )

        view.sync_task_ledger(reason="merge 完成，已同步 branch 执行结果到 task ledger", created_by="supervisor")
        view.sync_progress_ledger(
            phase="merge",
            reason="graph merge 已合并本轮 researcher 结果",
            created_by="supervisor",
        )
        view._emit_deep_research_topology_update()
        return view.snapshot_patch(
            next_step="verify",
            pending_worker_tasks=[],
            worker_results=[{"__reset__": True}],
        )

    def _verify_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "verify")
        task_map = {task.id: task for task in view.task_queue.all_tasks()}
        syntheses = latest_branch_syntheses(
            view.artifact_store.branch_syntheses(),
            view.artifact_store.branch_briefs(),
        )
        research_brief = view.artifact_store.research_brief()

        def _emit_contract_artifact(
            *,
            artifact_id: str,
            artifact_type: str,
            status: str,
            task_id: str | None,
            branch_id: str | None,
            summary: str,
            stage: str,
            extra: dict[str, Any] | None = None,
        ) -> None:
            branch_task = task_map.get(task_id or "")
            view._emit_artifact_update(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                status=status,
                task_id=task_id,
                branch_id=branch_id,
                summary=summary[:180],
                task_kind=branch_task.task_kind if branch_task else None,
                stage=stage,
                validation_stage="coverage_check" if stage != "grounding_check" else "claim_check",
                attempt=branch_task.attempts if branch_task else view.graph_attempt,
                extra=extra or {},
            )

        def _emit_issue_status(issue: RevisionIssue) -> None:
            _emit_contract_artifact(
                artifact_id=issue.id,
                artifact_type="revision_issue",
                status=issue.status,
                task_id=issue.task_id,
                branch_id=issue.branch_id,
                summary=issue.summary,
                stage="issue_aggregation",
                extra={
                    "issue_type": issue.issue_type,
                    "severity": issue.severity,
                    "blocking": issue.blocking,
                    "recommended_action": issue.recommended_action,
                    "claim_ids": list(issue.claim_ids),
                    "obligation_ids": list(issue.obligation_ids),
                    "consistency_result_ids": list(issue.consistency_result_ids),
                },
            )

        current_scope_task_ids = {synthesis.task_id for synthesis in syntheses}
        current_scope_branch_ids = {
            str(synthesis.branch_id or "").strip()
            for synthesis in syntheses
            if str(synthesis.branch_id or "").strip()
        }

        def _resolve_stale_issues(current_issues: list[RevisionIssue]) -> None:
            current_keys = {
                str(issue.metadata.get("issue_key") or issue.id): issue.id
                for issue in current_issues
            }
            for existing_issue in view.artifact_store.revision_issues():
                if existing_issue.status not in {"open", "accepted"}:
                    continue
                if (
                    existing_issue.task_id not in current_scope_task_ids
                    and str(existing_issue.branch_id or "").strip() not in current_scope_branch_ids
                ):
                    continue
                key = str(existing_issue.metadata.get("issue_key") or existing_issue.id)
                if key in current_keys:
                    if current_keys[key] == existing_issue.id:
                        continue
                    updated = view.artifact_store.update_revision_issue_status(
                        existing_issue.id,
                        "superseded",
                        resolution={"superseded_by": current_keys[key]},
                        metadata={"reverified_at": _now_iso()},
                    )
                else:
                    updated = view.artifact_store.update_revision_issue_status(
                        existing_issue.id,
                        "resolved",
                        resolution={"resolved_by": "verify"},
                        metadata={"reverified_at": _now_iso()},
                    )
                if updated:
                    _emit_issue_status(updated)

        def _resolve_stale_requests() -> None:
            for request in view.artifact_store.coordination_requests(status="open"):
                if (
                    request.task_id not in current_scope_task_ids
                    and str(request.branch_id or "").strip() not in current_scope_branch_ids
                ):
                    continue
                updated = view.artifact_store.update_coordination_request_status(
                    request.id,
                    "resolved",
                    metadata={"resolved_by": "verify", "next_step": "supervisor_decide"},
                )
                if updated:
                    view._emit_artifact_update(
                        artifact_id=updated.id,
                        artifact_type="coordination_request",
                        status=updated.status,
                        task_id=updated.task_id,
                        branch_id=updated.branch_id,
                        agent_id="verifier",
                        summary=updated.summary[:180],
                        stage="issue_aggregation",
                        extra={
                            "request_type": updated.request_type,
                            "issue_ids": list(updated.issue_ids),
                        },
                    )

        def _build_requests_from_issues(issues: list[RevisionIssue]) -> list[CoordinationRequest]:
            grouped: dict[str, list[RevisionIssue]] = defaultdict(list)
            for issue in issues:
                if not issue.blocking or issue.status not in {"open", "accepted"}:
                    continue
                grouped[str(issue.branch_id or "root")].append(issue)
            requests: list[CoordinationRequest] = []
            for branch_key, branch_issues in grouped.items():
                branch_id = branch_key if branch_key != "root" else view.root_branch_id
                task = task_map.get(branch_issues[0].task_id or "")
                actions = {issue.recommended_action for issue in branch_issues if issue.recommended_action}
                if "spawn_counterevidence_branch" in actions:
                    request_type = "need_counterevidence"
                elif any(action in {"spawn_follow_up_branch", "patch_branch"} for action in actions):
                    request_type = "retry_branch"
                else:
                    request_type = "retry_branch"
                suggested_queries = _dedupe_texts(
                    [
                        *[query for issue in branch_issues for query in issue.suggested_queries],
                        *(_derive_branch_queries(task) if task else []),
                    ]
                )
                requests.append(
                    CoordinationRequest(
                        id=support._new_id("request"),
                        request_type=request_type,
                        summary=f"{len(branch_issues)} unresolved verification issues require supervisor routing",
                        branch_id=branch_id,
                        task_id=task.id if task else None,
                        requested_by="verifier",
                        artifact_ids=_dedupe_texts(
                            [artifact_id for issue in branch_issues for artifact_id in [issue.id, *issue.artifact_ids]]
                        ),
                        issue_ids=[issue.id for issue in branch_issues],
                        suggested_queries=suggested_queries,
                        impact_scope=str(branch_id or task.id if task else "research"),
                        reason="verification issues remain unresolved after structured verification",
                        blocking_level="blocking",
                        suggested_next_action="supervisor_review",
                        metadata={
                            "issue_types": list(dict.fromkeys(issue.issue_type for issue in branch_issues)),
                            "recommended_actions": list(actions),
                        },
                    )
                )
            return requests

        claim_record = view.start_agent_run(
            role="verifier",
            phase="grounding_check",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
            stage="grounding_check",
            validation_stage="claim_check",
        )
        claim_units_to_persist: list[ClaimUnit] = []
        grounding_artifacts: list[ClaimGroundingResult] = []
        claim_results: list[VerificationResult] = []
        claim_submissions: list[ResearchSubmission] = []
        claim_outcomes_by_task: dict[str, VerificationResult] = {}
        try:
            for synthesis in syntheses:
                task = task_map.get(synthesis.task_id)
                if task is None:
                    continue
                task.stage = "grounding_check"
                view._emit_task_update(
                    task=task,
                    status=task.status,
                    attempt=task.attempts,
                )
                existing_claim_units = view.artifact_store.claim_units(task_id=task.id)
                claim_units = derive_claim_units(
                    claim_verifier=self.claim_verifier,
                    task=task,
                    synthesis=synthesis,
                    created_by=claim_record.agent_id,
                    existing_claim_units=existing_claim_units,
                )
                claim_units_to_persist.extend(
                    [item for item in claim_units if item.id not in {existing.id for existing in existing_claim_units}]
                )
                synthesis.claim_ids = [item.id for item in claim_units]
                synthesis.revision_brief_id = synthesis.revision_brief_id or task.revision_brief_id
                view.artifact_store.add_branch_synthesis(synthesis)
                claim_tool_session: DeepResearchToolAgentSession | None = None
                if self.enable_tool_agents:
                    try:
                        claim_tool_session = self._try_verifier_tool_agent(
                            view=view,
                            task=task,
                            synthesis=synthesis,
                            validation_stage="claim_check",
                            claim_units=claim_units,
                        )
                    except Exception:
                        claim_tool_session = None
                if claim_tool_session is not None:
                    self._persist_verifier_tool_agent_session(
                        view=view,
                        task_map=task_map,
                        validation_stage="claim_check",
                        source_candidates=claim_tool_session.source_candidates,
                        fetched_documents=claim_tool_session.fetched_documents,
                        evidence_passages=claim_tool_session.evidence_passages,
                        evidence_cards=claim_tool_session.evidence_cards,
                        verification_results=claim_tool_session.verification_results,
                        coordination_requests=claim_tool_session.coordination_requests,
                        submissions=claim_tool_session.submissions,
                    )
                related_passages = [
                    passage
                    for passage in view.artifact_store.evidence_passages(branch_id=synthesis.branch_id)
                    if not synthesis.evidence_passage_ids or passage.id in synthesis.evidence_passage_ids
                ]
                for claim_unit in claim_units:
                    _emit_contract_artifact(
                        artifact_id=claim_unit.id,
                        artifact_type="claim_unit",
                        status=claim_unit.status,
                        task_id=claim_unit.task_id,
                        branch_id=claim_unit.branch_id,
                        summary=claim_unit.claim,
                        stage="grounding_check",
                        extra={
                            "claim_provenance": copy.deepcopy(claim_unit.claim_provenance),
                            "evidence_passage_ids": list(claim_unit.evidence_passage_ids),
                        },
                    )
                claim_groundings = ground_claim_units(
                    claim_verifier=self.claim_verifier,
                    claim_units=claim_units,
                    passages=[
                        {
                            "id": passage.id,
                            "passage_id": passage.id,
                            "url": passage.url,
                            "text": passage.text,
                            "quote": passage.quote,
                            "snippet_hash": passage.snippet_hash,
                            "heading_path": passage.heading_path,
                        }
                        for passage in related_passages
                    ],
                    created_by=claim_record.agent_id,
                )
                tool_claim_result = (
                    next(
                        (
                            item
                            for item in reversed(claim_tool_session.verification_results)
                            if item.validation_stage == "claim_check"
                        ),
                        None,
                    )
                    if claim_tool_session is not None
                    else None
                )
                tool_claim_submission = (
                    next(
                        (
                            item
                            for item in reversed(claim_tool_session.submissions)
                            if item.validation_stage == "claim_check"
                        ),
                        None,
                    )
                    if claim_tool_session is not None
                    else None
                )
                claim_groundings = _merge_tool_claim_groundings(
                    claim_units=claim_units,
                    claim_groundings=claim_groundings,
                    tool_result=tool_claim_result,
                    tool_submission=tool_claim_submission,
                    fallback_urls=list(synthesis.citation_urls),
                    fallback_passage_ids=(
                        [
                            item.id
                            for item in (claim_tool_session.evidence_passages if claim_tool_session else [])
                        ]
                        or list(synthesis.evidence_passage_ids)
                    ),
                )
                grounding_artifacts.extend(claim_groundings)
                for grounding in claim_groundings:
                    _emit_contract_artifact(
                        artifact_id=grounding.id,
                        artifact_type="claim_grounding_result",
                        status=grounding.status,
                        task_id=grounding.task_id,
                        branch_id=grounding.branch_id,
                        summary=grounding.summary or str(grounding.metadata.get("claim") or ""),
                        stage="grounding_check",
                        extra={
                            "claim_id": grounding.claim_id,
                            "severity": grounding.severity,
                            "evidence_urls": list(grounding.evidence_urls),
                            "evidence_passage_ids": list(grounding.evidence_passage_ids),
                        },
                    )
                statuses = [result.status for result in claim_groundings]
                if any(status == "contradicted" for status in statuses):
                    outcome = "failed"
                    recommended_action = (
                        tool_claim_result.recommended_action
                        if tool_claim_result is not None and tool_claim_result.outcome == "failed"
                        else "contradiction_found"
                    )
                    summary = (
                        tool_claim_result.summary
                        if tool_claim_result is not None and tool_claim_result.outcome == "failed"
                        else "claim grounding 发现矛盾证据"
                    )
                elif any(status in {"unsupported", "unresolved"} for status in statuses):
                    outcome = "needs_follow_up"
                    recommended_action = (
                        tool_claim_result.recommended_action
                        if tool_claim_result is not None and tool_claim_result.outcome == "needs_follow_up"
                        else "need_counterevidence"
                    )
                    summary = (
                        tool_claim_result.summary
                        if tool_claim_result is not None and tool_claim_result.outcome == "needs_follow_up"
                        else "claim grounding 发现证据不足"
                    )
                else:
                    outcome = "passed"
                    recommended_action = (
                        tool_claim_result.recommended_action
                        if tool_claim_result is not None and tool_claim_result.outcome == "passed"
                        else "report"
                    )
                    summary = (
                        tool_claim_result.summary
                        if tool_claim_result is not None and tool_claim_result.outcome == "passed"
                        else "claim grounding 检查通过"
                    )
                verification_result = VerificationResult(
                    id=support._new_id("verification"),
                    task_id=task.id,
                    branch_id=synthesis.branch_id,
                    synthesis_id=synthesis.id,
                    validation_stage="claim_check",
                    outcome=outcome,
                    summary=summary,
                    recommended_action=recommended_action,
                    evidence_urls=_dedupe_texts(
                        [url for result in claim_groundings for url in result.evidence_urls]
                    ),
                    evidence_passage_ids=_dedupe_texts(
                        [passage_id for result in claim_groundings for passage_id in result.evidence_passage_ids]
                    ),
                    metadata={
                        "claim_ids": [item.id for item in claim_units],
                        "grounding_result_ids": [item.id for item in claim_groundings],
                        "claims": [
                            {
                                "claim_id": claim_unit.id,
                                "claim": claim_unit.claim,
                                "status": result.status,
                                "evidence_urls": list(result.evidence_urls),
                                "evidence_passage_ids": list(result.evidence_passage_ids),
                                "notes": result.summary,
                            }
                            for claim_unit, result in zip(claim_units, claim_groundings, strict=False)
                        ],
                        "branch_summary": synthesis.summary[:240],
                    },
                )
                claim_results.append(verification_result)
                claim_outcomes_by_task[task.id] = verification_result
                claim_submissions.append(
                    ResearchSubmission(
                        id=support._new_id("submission"),
                        submission_kind="verification_bundle",
                        summary=summary,
                        task_id=task.id,
                        branch_id=synthesis.branch_id,
                        created_by=claim_record.agent_id,
                        result_status=outcome,
                        stage="verify",
                        validation_stage="claim_check",
                        artifact_ids=[verification_result.id, *[item.id for item in claim_groundings]],
                        claim_ids=[item.id for item in claim_units],
                        metadata={
                            "recommended_action": recommended_action,
                            "grounding_result_ids": [item.id for item in claim_groundings],
                        },
                    )
                )
            if claim_units_to_persist:
                view.artifact_store.add_claim_units(claim_units_to_persist)
            if grounding_artifacts:
                view.artifact_store.add_claim_grounding_results(grounding_artifacts)
            if claim_results:
                view.artifact_store.add_verification_results(claim_results)
                for result in claim_results:
                    _emit_contract_artifact(
                        artifact_id=result.id,
                        artifact_type="verification_result",
                        status=result.status,
                        task_id=result.task_id,
                        branch_id=result.branch_id,
                        summary=result.summary,
                        stage="grounding_check",
                        extra={
                            "validation_stage": result.validation_stage,
                            "outcome": result.outcome,
                            "recommended_action": result.recommended_action,
                            "claim_ids": list(result.metadata.get("claim_ids", [])),
                        },
                    )
            if claim_submissions:
                view.artifact_store.add_submissions(claim_submissions)
                for submission in claim_submissions:
                    _emit_contract_artifact(
                        artifact_id=submission.id,
                        artifact_type="verification_submission",
                        status=submission.status,
                        task_id=submission.task_id,
                        branch_id=submission.branch_id,
                        summary=submission.summary,
                        stage="grounding_check",
                        extra={
                            "submission_kind": submission.submission_kind,
                            "result_status": submission.result_status,
                            "claim_ids": list(submission.claim_ids),
                            "artifact_ids": list(submission.artifact_ids),
                        },
                    )

            view.finish_agent_run(
                claim_record,
                status="completed",
                summary=f"claim_checks={len(claim_results)}",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
                stage="grounding_check",
                validation_stage="claim_check",
            )
        except Exception as exc:
            view.finish_agent_run(
                claim_record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
                stage="grounding_check",
                validation_stage="claim_check",
            )
            raise

        coverage_record = view.start_agent_run(
            role="verifier",
            phase="coverage_check",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
            stage="coverage_evaluation",
            validation_stage="coverage_check",
        )
        try:
            executed_objectives = [
                task.objective or task.query or task.title or task.goal
                for task in view.task_queue.all_tasks()
                if task.status == "completed"
            ]
            verified_knowledge = "\n\n".join(
                synthesis.summary
                for synthesis in syntheses
                if claim_outcomes_by_task.get(synthesis.task_id)
                and claim_outcomes_by_task[synthesis.task_id].outcome == "passed"
            )
            fallback_gap_result = self.verifier.analyze(
                self.topic,
                executed_queries=executed_objectives,
                collected_knowledge=verified_knowledge or view._knowledge_summary(),
            )
            obligations_to_persist: list[CoverageObligation] = []
            coverage_evaluations: list[CoverageEvaluationResult] = []
            consistency_artifacts: list[ConsistencyResult] = []
            revision_issues: list[RevisionIssue] = []
            coverage_results: list[VerificationResult] = []
            verification_submissions: list[ResearchSubmission] = []
            verified_task_ids: list[str] = []
            retry_task_ids: list[str] = []

            for synthesis in syntheses:
                task = task_map.get(synthesis.task_id)
                if task is None:
                    continue
                task.stage = "coverage_evaluation"
                view._emit_task_update(
                    task=task,
                    status=task.status,
                    attempt=task.attempts,
                )
                branch_brief = view.artifact_store.get_brief(task.branch_id or "")
                branch_revision_briefs = view.artifact_store.revision_briefs(target_branch_id=task.branch_id)
                revision_brief = None
                if branch_brief and branch_brief.latest_revision_brief_id:
                    revision_brief = next(
                        (
                            item
                            for item in branch_revision_briefs
                            if item.id == branch_brief.latest_revision_brief_id
                        ),
                        None,
                    )
                if revision_brief is None and branch_revision_briefs:
                    revision_brief = sorted(branch_revision_briefs, key=lambda item: (item.created_at, item.id))[-1]
                existing_obligations = view.artifact_store.coverage_obligations(task_id=task.id)
                obligations = derive_coverage_obligations(
                    research_brief=research_brief,
                    task=task,
                    branch_id=task.branch_id,
                    revision_brief=revision_brief,
                    created_by="supervisor",
                    existing_obligations=existing_obligations,
                )
                obligations_to_persist.extend(
                    [item for item in obligations if item.id not in {existing.id for existing in existing_obligations}]
                )
                for obligation in obligations:
                    _emit_contract_artifact(
                        artifact_id=obligation.id,
                        artifact_type="coverage_obligation",
                        status=obligation.status,
                        task_id=obligation.task_id,
                        branch_id=obligation.branch_id,
                        summary=obligation.target,
                        stage="coverage_evaluation",
                        extra={
                            "completion_criteria": list(obligation.completion_criteria),
                            "source": obligation.source,
                        },
                    )
                branch_claim_units = view.artifact_store.claim_units(task_id=task.id)
                branch_groundings = view.artifact_store.claim_grounding_results(task_id=task.id)
                claim_result = claim_outcomes_by_task.get(task.id)
                coverage_tool_session: DeepResearchToolAgentSession | None = None
                if self.enable_tool_agents:
                    try:
                        coverage_tool_session = self._try_verifier_tool_agent(
                            view=view,
                            task=task,
                            synthesis=synthesis,
                            validation_stage="coverage_check",
                            claim_result=claim_result,
                            gap_result=fallback_gap_result,
                            verified_knowledge=verified_knowledge,
                            obligations=obligations,
                        )
                    except Exception:
                        coverage_tool_session = None
                if coverage_tool_session is not None:
                    self._persist_verifier_tool_agent_session(
                        view=view,
                        task_map=task_map,
                        validation_stage="coverage_check",
                        source_candidates=coverage_tool_session.source_candidates,
                        fetched_documents=coverage_tool_session.fetched_documents,
                        evidence_passages=coverage_tool_session.evidence_passages,
                        evidence_cards=coverage_tool_session.evidence_cards,
                        verification_results=coverage_tool_session.verification_results,
                        coordination_requests=coverage_tool_session.coordination_requests,
                        submissions=coverage_tool_session.submissions,
                    )
                branch_coverage_results = evaluate_obligations(
                    task=task,
                    synthesis=synthesis,
                    obligations=obligations,
                    claim_units=branch_claim_units,
                    grounding_results=branch_groundings,
                    created_by=coverage_record.agent_id,
                )
                tool_coverage_result = (
                    next(
                        (
                            item
                            for item in reversed(coverage_tool_session.verification_results)
                            if item.validation_stage == "coverage_check"
                        ),
                        None,
                    )
                    if coverage_tool_session is not None
                    else None
                )
                tool_coverage_submission = (
                    next(
                        (
                            item
                            for item in reversed(coverage_tool_session.submissions)
                            if item.validation_stage == "coverage_check"
                        ),
                        None,
                    )
                    if coverage_tool_session is not None
                    else None
                )
                branch_coverage_results = _merge_tool_coverage_results(
                    obligations=obligations,
                    coverage_results=branch_coverage_results,
                    tool_result=tool_coverage_result,
                    tool_submission=tool_coverage_submission,
                    fallback_urls=list(synthesis.citation_urls),
                    fallback_passage_ids=(
                        [
                            item.id
                            for item in (coverage_tool_session.evidence_passages if coverage_tool_session else [])
                        ]
                        or list(synthesis.evidence_passage_ids)
                    ),
                )
                coverage_evaluations.extend(branch_coverage_results)
                for item in branch_coverage_results:
                    _emit_contract_artifact(
                        artifact_id=item.id,
                        artifact_type="coverage_evaluation_result",
                        status=item.status,
                        task_id=item.task_id,
                        branch_id=item.branch_id,
                        summary=item.summary,
                        stage="coverage_evaluation",
                        extra={
                            "obligation_id": item.obligation_id,
                            "evidence_urls": list(item.evidence_urls),
                            "evidence_passage_ids": list(item.evidence_passage_ids),
                        },
                    )
                missing_targets = [
                    str(item.metadata.get("target") or "").strip()
                    for item in branch_coverage_results
                    if item.status != "satisfied"
                ]
                if claim_result and claim_result.outcome == "failed":
                    outcome = "failed"
                    recommended_action = "contradiction_found"
                    summary = "coverage evaluation 被 claim contradiction 阻断"
                elif claim_result and claim_result.outcome == "needs_follow_up":
                    outcome = "needs_follow_up"
                    recommended_action = "need_counterevidence"
                    summary = "coverage evaluation 发现 claim grounding 仍未闭合"
                elif any(item.status in {"unsatisfied", "unresolved"} for item in branch_coverage_results):
                    outcome = "needs_follow_up"
                    recommended_action = "retry_branch"
                    summary = f"coverage evaluation 发现仍有 {len(missing_targets)} 项 obligation 未满足"
                elif any(item.status == "partially_satisfied" for item in branch_coverage_results):
                    outcome = "passed"
                    recommended_action = "report"
                    summary = "coverage evaluation 通过，保留 non-blocking follow-up obligations"
                    verified_task_ids.append(task.id)
                else:
                    outcome = "passed"
                    recommended_action = "report"
                    summary = "coverage evaluation 通过"
                    verified_task_ids.append(task.id)
                result = VerificationResult(
                    id=support._new_id("verification"),
                    task_id=task.id,
                    branch_id=synthesis.branch_id,
                    synthesis_id=synthesis.id,
                    validation_stage="coverage_check",
                    outcome=outcome,
                    summary=summary,
                    recommended_action=recommended_action,
                    evidence_urls=_dedupe_texts(
                        [url for item in branch_coverage_results for url in item.evidence_urls]
                    ),
                    evidence_passage_ids=_dedupe_texts(
                        [passage_id for item in branch_coverage_results for passage_id in item.evidence_passage_ids]
                    ),
                    metadata={
                        "obligation_ids": [item.id for item in obligations],
                        "coverage_result_ids": [item.id for item in branch_coverage_results],
                        "missing_acceptance_criteria": missing_targets,
                    },
                )
                coverage_results.append(result)
                verification_submissions.append(
                    ResearchSubmission(
                        id=support._new_id("submission"),
                        submission_kind="verification_bundle",
                        summary=summary,
                        task_id=task.id,
                        branch_id=synthesis.branch_id,
                        created_by=coverage_record.agent_id,
                        result_status=outcome,
                        stage="verify",
                        validation_stage="coverage_check",
                        artifact_ids=[result.id, *[item.id for item in branch_coverage_results]],
                        obligation_ids=[item.id for item in obligations],
                        metadata={
                            "recommended_action": recommended_action,
                            "coverage_result_ids": [item.id for item in branch_coverage_results],
                        },
                    )
                )

            if obligations_to_persist:
                view.artifact_store.add_coverage_obligations(obligations_to_persist)
            if coverage_evaluations:
                view.artifact_store.add_coverage_evaluation_results(coverage_evaluations)

            current_claim_units = [
                item
                for synthesis in syntheses
                for item in view.artifact_store.claim_units(task_id=synthesis.task_id)
            ]
            current_groundings = [
                item
                for synthesis in syntheses
                for item in view.artifact_store.claim_grounding_results(task_id=synthesis.task_id)
            ]
            for synthesis in syntheses:
                task = task_map.get(synthesis.task_id)
                if task is None:
                    continue
                branch_consistency = evaluate_consistency(
                    claim_verifier=self.claim_verifier,
                    claim_units=view.artifact_store.claim_units(task_id=task.id),
                    grounding_results=view.artifact_store.claim_grounding_results(task_id=task.id),
                    all_claim_units=current_claim_units,
                    all_grounding_results=current_groundings,
                    created_by=coverage_record.agent_id,
                )
                consistency_artifacts.extend(branch_consistency)

            if consistency_artifacts:
                view.artifact_store.add_consistency_results(consistency_artifacts)
                for item in consistency_artifacts:
                    _emit_contract_artifact(
                        artifact_id=item.id,
                        artifact_type="consistency_result",
                        status=item.status,
                        task_id=item.task_id,
                        branch_id=item.branch_id,
                        summary=item.summary,
                        stage="consistency_check",
                        extra={
                            "claim_ids": list(item.claim_ids),
                            "related_branch_ids": list(item.related_branch_ids),
                        },
                    )

            all_obligations = [
                item
                for synthesis in syntheses
                for item in view.artifact_store.coverage_obligations(task_id=synthesis.task_id)
            ]
            issues_by_task: dict[str, list[RevisionIssue]] = defaultdict(list)
            for synthesis in syntheses:
                task = task_map.get(synthesis.task_id)
                if task is None:
                    continue
                branch_issues = aggregate_revision_issues(
                    task=task,
                    claim_units=view.artifact_store.claim_units(task_id=task.id),
                    obligations=view.artifact_store.coverage_obligations(task_id=task.id),
                    grounding_results=view.artifact_store.claim_grounding_results(task_id=task.id),
                    coverage_results=view.artifact_store.coverage_evaluation_results(task_id=task.id),
                    consistency_results=[
                        item
                        for item in consistency_artifacts
                        if item.task_id == task.id or item.branch_id == task.branch_id
                    ],
                    created_by=coverage_record.agent_id,
                )
                revision_issues.extend(branch_issues)
                issues_by_task[task.id].extend(branch_issues)

            _resolve_stale_issues(revision_issues)
            if revision_issues:
                view.artifact_store.add_revision_issues(revision_issues)
                for issue in revision_issues:
                    _emit_issue_status(issue)

            retry_task_ids = list(
                dict.fromkeys(
                    issue.task_id
                    for issue in revision_issues
                    if issue.blocking and issue.status in {"open", "accepted"} and issue.task_id
                )
            )

            gap_result = build_gap_result(
                obligations=all_obligations,
                coverage_results=coverage_evaluations,
                fallback_result=fallback_gap_result,
                fallback_analysis=fallback_gap_result.analysis,
                fallback_queries=fallback_gap_result.suggested_queries,
            )
            gap_artifacts = [
                KnowledgeGap(
                    id=support._new_id("gap"),
                    aspect=gap.aspect,
                    importance=gap.importance,
                    reason=gap.reason,
                    branch_id=view.root_branch_id,
                    suggested_queries=list(gap_result.suggested_queries),
                    advisory=getattr(gap, "advisory", True),
                )
                for gap in fallback_gap_result.gaps
            ]
            view.artifact_store.replace_gaps(gap_artifacts)
            for gap in gap_artifacts:
                view._emit_artifact_update(
                    artifact_id=gap.id,
                    artifact_type="knowledge_gap",
                    status=gap.status,
                    branch_id=view.root_branch_id,
                    summary=f"{gap.aspect}: {gap.reason}",
                    stage="coverage_check",
                    validation_stage="coverage_check",
                )

            _resolve_stale_requests()
            verification_requests = _build_requests_from_issues(revision_issues)
            if verification_requests:
                view.artifact_store.add_coordination_requests(verification_requests)
                for request in verification_requests:
                    view._emit_artifact_update(
                        artifact_id=request.id,
                        artifact_type="coordination_request",
                        status=request.status,
                        task_id=request.task_id,
                        branch_id=request.branch_id,
                        agent_id=request.requested_by,
                        summary=request.summary[:180],
                        stage="issue_aggregation",
                        validation_stage="coverage_check",
                        extra={
                            "request_type": request.request_type,
                            "artifact_ids": list(request.artifact_ids),
                            "issue_ids": list(request.issue_ids),
                            "suggested_queries": list(request.suggested_queries),
                        },
                    )

            if coverage_results:
                view.artifact_store.add_verification_results(coverage_results)
                for result in coverage_results:
                    _emit_contract_artifact(
                        artifact_id=result.id,
                        artifact_type="verification_result",
                        status=result.status,
                        task_id=result.task_id,
                        branch_id=result.branch_id,
                        summary=result.summary,
                        stage="coverage_evaluation",
                        extra={
                            "validation_stage": result.validation_stage,
                            "outcome": result.outcome,
                            "recommended_action": result.recommended_action,
                            "obligation_ids": list(result.metadata.get("obligation_ids", [])),
                        },
                    )
            if verification_submissions:
                view.artifact_store.add_submissions(verification_submissions)
                for submission in verification_submissions:
                    _emit_contract_artifact(
                        artifact_id=submission.id,
                        artifact_type="verification_submission",
                        status=submission.status,
                        task_id=submission.task_id,
                        branch_id=submission.branch_id,
                        summary=submission.summary,
                        stage="coverage_evaluation",
                        extra={
                            "submission_kind": submission.submission_kind,
                            "result_status": submission.result_status,
                            "obligation_ids": list(submission.obligation_ids),
                            "artifact_ids": list(submission.artifact_ids),
                        },
                    )

            coverage_matrix_artifact = _build_coverage_matrix_artifact(
                view=view,
                research_brief=research_brief,
                obligations=all_obligations,
                coverage_results=coverage_evaluations,
                revision_issues=revision_issues,
                syntheses=syntheses,
            )
            contradiction_registry_artifact = _build_contradiction_registry_artifact(
                view=view,
                research_brief=research_brief,
                grounding_results=current_groundings,
                consistency_results=consistency_artifacts,
            )
            missing_evidence_artifact = _build_missing_evidence_list_artifact(
                view=view,
                research_brief=research_brief,
                revision_issues=revision_issues,
                gap_artifacts=gap_artifacts,
            )
            view.artifact_store.set_coverage_matrix(coverage_matrix_artifact)
            view.artifact_store.set_contradiction_registry(contradiction_registry_artifact)
            view.artifact_store.set_missing_evidence_list(missing_evidence_artifact)
            view._emit_artifact_update(
                artifact_id=coverage_matrix_artifact.id,
                artifact_type="coverage_matrix",
                status=coverage_matrix_artifact.status,
                branch_id=view.root_branch_id,
                agent_id=coverage_matrix_artifact.created_by,
                summary=f"coverage rows={len(coverage_matrix_artifact.rows)}",
                stage="coverage_check",
                validation_stage="coverage_check",
                extra={"overall_coverage": coverage_matrix_artifact.overall_coverage},
            )
            view._emit_artifact_update(
                artifact_id=contradiction_registry_artifact.id,
                artifact_type="contradiction_registry",
                status=contradiction_registry_artifact.status,
                branch_id=view.root_branch_id,
                agent_id=contradiction_registry_artifact.created_by,
                summary=f"contradictions={len(contradiction_registry_artifact.entries)}",
                stage="coverage_check",
                validation_stage="coverage_check",
            )
            view._emit_artifact_update(
                artifact_id=missing_evidence_artifact.id,
                artifact_type="missing_evidence_list",
                status=missing_evidence_artifact.status,
                branch_id=view.root_branch_id,
                agent_id=missing_evidence_artifact.created_by,
                summary=f"missing_evidence={len(missing_evidence_artifact.items)}",
                stage="coverage_check",
                validation_stage="coverage_check",
            )

            quality_summary = view._quality_summary(gap_result)
            view._emit(events.ToolEventType.QUALITY_UPDATE, quality_summary)

            follow_up_branch_count = len(
                {
                    issue.branch_id
                    for issue in revision_issues
                    if issue.recommended_action == "spawn_follow_up_branch" and issue.branch_id
                }
            )
            counterevidence_branch_count = len(
                {
                    issue.branch_id
                    for issue in revision_issues
                    if issue.recommended_action == "spawn_counterevidence_branch" and issue.branch_id
                }
            )
            blocking_issue_ids = [
                issue.id
                for issue in revision_issues
                if issue.blocking and issue.status in {"open", "accepted"}
            ]
            non_blocking_issue_ids = [
                issue.id
                for issue in revision_issues
                if not issue.blocking and issue.status in {"open", "accepted"}
            ]
            verification_summary = {
                "verified_branches": len(
                    {
                        task_map[task_id].branch_id
                        for task_id in verified_task_ids
                        if task_id in task_map and task_map[task_id].branch_id
                    }
                ),
                "verified_task_ids": verified_task_ids,
                "retry_branches": len(
                    {
                        task_map[task_id].branch_id
                        for task_id in retry_task_ids
                        if task_id in task_map and task_map[task_id].branch_id
                    }
                ),
                "retry_task_ids": list(dict.fromkeys(retry_task_ids)),
                "failed_branches": len(
                    {
                        issue.branch_id
                        for issue in revision_issues
                        if issue.issue_type == "claim_grounding"
                        and issue.status in {"open", "accepted"}
                        and issue.branch_id
                    }
                ),
                "follow_up_branches": follow_up_branch_count,
                "counterevidence_branches": counterevidence_branch_count,
                "coverage_gap_count": len(gap_artifacts),
                "advisory_gap_count": len(gap_artifacts),
                "coverage_matrix_id": coverage_matrix_artifact.id,
                "contradiction_registry_id": contradiction_registry_artifact.id,
                "missing_evidence_list_id": missing_evidence_artifact.id,
                "contradiction_count": len(contradiction_registry_artifact.entries),
                "missing_evidence_count": len(missing_evidence_artifact.items),
                "blocking_verification_debt_count": len(blocking_issue_ids),
                "replan_hints": list(gap_result.suggested_queries),
                "advisory_replan_hints": list(gap_result.suggested_queries),
                "request_ids": [request.id for request in verification_requests],
                "open_issue_ids": [issue.id for issue in revision_issues if issue.status in {"open", "accepted"}],
                "blocking_issue_ids": blocking_issue_ids,
                "non_blocking_issue_ids": non_blocking_issue_ids,
                "issue_statuses": summarize_issue_statuses(view.artifact_store.revision_issues()),
                "revision_lineage": summarize_revision_lineage(
                    revision_briefs=view.artifact_store.revision_briefs(),
                    issues=view.artifact_store.revision_issues(),
                ),
                "revision_issue_count": len(revision_issues),
            }
            for synthesis in syntheses:
                task = task_map.get(synthesis.task_id)
                if task is None or not synthesis.branch_id:
                    continue
                branch_brief = view.artifact_store.get_brief(synthesis.branch_id)
                if branch_brief is None:
                    continue
                branch_issues = view.artifact_store.revision_issues(branch_id=synthesis.branch_id)
                branch_brief.claim_ids = [item.id for item in view.artifact_store.claim_units(task_id=task.id)]
                branch_brief.obligation_ids = [
                    item.id for item in view.artifact_store.coverage_obligations(task_id=task.id)
                ]
                branch_brief.open_issue_ids = [
                    issue.id
                    for issue in branch_issues
                    if issue.status in {"open", "accepted"}
                ]
                branch_brief.resolved_issue_ids = [
                    issue.id
                    for issue in branch_issues
                    if issue.status == "resolved"
                ]
                branch_brief.verification_status = (
                    "passed"
                    if not any(issue.blocking and issue.status in {"open", "accepted"} for issue in branch_issues)
                    else "needs_follow_up"
                )
                branch_brief.current_stage = "consistency_check" if consistency_artifacts else "coverage_evaluation"
                branch_brief.latest_verification_id = next(
                    (
                        result.id
                        for result in reversed(coverage_results)
                        if result.branch_id == synthesis.branch_id
                    ),
                    branch_brief.latest_verification_id,
                )
                view.artifact_store.put_brief(branch_brief)
            view.runtime_state["supervisor_request_ids"] = [
                request.id
                for request in view.artifact_store.coordination_requests(status="open")
            ]
            view.sync_progress_ledger(
                phase="issue_aggregation",
                reason="结构化验证 artifacts 已更新",
                created_by="verifier",
                verification_summary=verification_summary,
                outline_status="pending",
            )
            if verification_summary["blocking_issue_ids"]:
                view._emit_decision(
                    decision_type="verification_retry_requested",
                    reason="branch 验证产生了 blocking revision issues",
                    iteration=view.current_iteration,
                    gap_count=len(gap_artifacts),
                    attempt=view.graph_attempt,
                    validation_stage="coverage_check",
                    extra={
                        "retry_task_ids": verification_summary["retry_task_ids"],
                        "blocking_issue_ids": verification_summary["blocking_issue_ids"],
                    },
                )
            elif verification_summary["contradiction_count"] or verification_summary["missing_evidence_count"]:
                view._emit_decision(
                    decision_type="coverage_gap_detected",
                    reason="结构化验证 artifacts 指出仍存在 coverage / contradiction / evidence 缺口",
                    iteration=view.current_iteration,
                    gap_count=verification_summary["blocking_verification_debt_count"],
                    attempt=view.graph_attempt,
                    validation_stage="coverage_check",
                    extra={
                        "suggested_queries": gap_result.suggested_queries,
                        "contradiction_count": verification_summary["contradiction_count"],
                        "missing_evidence_count": verification_summary["missing_evidence_count"],
                        "advisory_gap_count": len(gap_artifacts),
                    },
                )
            else:
                view._emit_decision(
                    decision_type="verification_passed",
                    reason="branch 验证通过，可进入 outline gate",
                    iteration=view.current_iteration,
                    coverage=gap_result.overall_coverage,
                    gap_count=len(gap_artifacts),
                    attempt=view.graph_attempt,
                    validation_stage="coverage_check",
                    extra={
                        "advisory_gap_count": len(gap_artifacts),
                        "suggested_queries": gap_result.suggested_queries,
                    },
                )

            view.finish_agent_run(
                coverage_record,
                status="completed",
                summary=f"coverage={gap_result.overall_coverage:.2f}, issues={len(blocking_issue_ids)}",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
                stage="issue_aggregation",
                validation_stage="coverage_check",
            )
            return view.snapshot_patch(
                next_step="supervisor_decide",
                latest_gap_result=gap_result.to_dict(),
                latest_verification_summary=verification_summary,
            )
        except Exception as exc:
            view.finish_agent_run(
                coverage_record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
                stage="coverage_check",
                validation_stage="coverage_check",
            )
            raise

    def _supervisor_decide_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "supervisor_decide")
        gap_result = _gap_result_from_payload(
            graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
        )
        verification_summary = copy.deepcopy(
            graph_state.get("latest_verification_summary")
            or view.runtime_state.get("last_verification_summary")
            or {}
        )
        open_requests = view.artifact_store.coordination_requests(status="open")
        research_brief = view.artifact_store.research_brief()
        task_ledger = view.artifact_store.task_ledger()
        progress_ledger = view.artifact_store.progress_ledger()
        coverage_matrix = view.artifact_store.coverage_matrix()
        contradiction_registry = view.artifact_store.contradiction_registry()
        missing_evidence_list = view.artifact_store.missing_evidence_list()
        outline_artifact = view.artifact_store.outline()
        revision_issues = view.artifact_store.revision_issues()
        record = view.start_agent_run(
            role="supervisor",
            phase="loop_decision",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
        )
        try:
            retry_task_ids = [
                task_id
                for task_id in verification_summary.get("retry_task_ids", [])
                if isinstance(task_id, str) and task_id.strip()
            ]
            evidence_count = len(view.artifact_store.evidence_passages()) or len(view.artifact_store.evidence_cards())
            section_count = len(view.artifact_store.branch_syntheses())
            unique_urls = {
                passage.url
                for passage in view.artifact_store.evidence_passages()
                if passage.url
            }
            if not unique_urls:
                unique_urls = {
                    card.source_url
                    for card in view.artifact_store.evidence_cards()
                    if card.source_url
                }
            citation_accuracy = min(1.0, len(unique_urls) / max(1, evidence_count)) if evidence_count else 0.0
            if view.current_iteration >= self.max_epochs and not view.budget_stop_reason:
                decision = self._deps.SupervisorDecision(
                    action=SupervisorAction.REPORT,
                    reasoning="已达到最大研究轮次，停止继续派发研究任务",
                    request_ids=[request.id for request in open_requests],
                )
            else:
                decision = self.supervisor.decide_next_action(
                    topic=self.topic,
                    num_queries=view.task_queue.completed_count(),
                    num_sources=len(unique_urls),
                    num_summaries=section_count,
                    current_epoch=view.current_iteration,
                    max_epochs=self.max_epochs,
                    ready_task_count=view.task_queue.ready_count(),
                    retry_task_ids=retry_task_ids,
                    request_ids=[request.id for request in open_requests],
                    budget_stop_reason=view.budget_stop_reason or "",
                    knowledge_summary=view._knowledge_summary(),
                    quality_score=gap_result.overall_coverage if gap_result else 0.0,
                    quality_gap_count=len(gap_result.gaps) if gap_result else 0,
                    citation_accuracy=citation_accuracy,
                    verification_summary=verification_summary,
                    revision_issues=[issue.to_dict() for issue in revision_issues],
                    research_brief=research_brief.to_dict() if research_brief else {},
                    task_ledger=task_ledger.to_dict() if task_ledger else {},
                    progress_ledger=progress_ledger.to_dict() if progress_ledger else {},
                    coverage_matrix=coverage_matrix.to_dict() if coverage_matrix else {},
                    contradiction_registry=contradiction_registry.to_dict() if contradiction_registry else {},
                    missing_evidence_list=missing_evidence_list.to_dict() if missing_evidence_list else {},
                    outline_artifact=outline_artifact.to_dict() if outline_artifact else {},
                )
            latest_decision = {
                "action": decision.action.value,
                "reasoning": decision.reasoning,
                "iteration": view.current_iteration,
                "request_ids": list(decision.request_ids),
                "issue_ids": list(decision.issue_ids),
            }
            view._emit_decision(
                decision_type=decision.action.value,
                reason=decision.reasoning,
                iteration=view.current_iteration,
                coverage=gap_result.overall_coverage if gap_result else None,
                gap_count=len(gap_result.gaps) if gap_result else None,
                attempt=view.graph_attempt,
            )

            next_step = (
                    "report"
                    if outline_artifact and outline_artifact.is_ready and not outline_artifact.blocking_gaps
                    else "outline_gate"
            )
            terminal_reason: str | None = None
            planning_mode = ""
            metadata: dict[str, Any] = {}
            created_revision_briefs: list[BranchRevisionBrief] = []
            created_tasks: list[ResearchTask] = []
            created_branch_ids: list[str] = []

            def _latest_branch_synthesis(branch_id: str | None) -> BranchSynthesis | None:
                if not branch_id:
                    return None
                branch_brief = view.artifact_store.get_brief(branch_id)
                branch_syntheses = view.artifact_store.branch_syntheses(branch_id=branch_id)
                if branch_brief and branch_brief.latest_synthesis_id:
                    return next(
                        (item for item in branch_syntheses if item.id == branch_brief.latest_synthesis_id),
                        None,
                    )
                if not branch_syntheses:
                    return None
                return sorted(branch_syntheses, key=lambda item: (item.created_at, item.id))[-1]

            def _emit_revision_brief(brief: BranchRevisionBrief) -> None:
                view._emit_artifact_update(
                    artifact_id=brief.id,
                    artifact_type="branch_revision_brief",
                    status=brief.status,
                    task_id=brief.target_task_id,
                    branch_id=brief.target_branch_id,
                    agent_id=brief.created_by,
                    summary=brief.summary[:180],
                    stage="loop_decision",
                    extra={
                        "revision_kind": brief.revision_kind,
                        "issue_ids": list(brief.issue_ids),
                        "source_branch_id": brief.source_branch_id,
                        "source_task_id": brief.source_task_id,
                    },
                )

            def _create_revision_work(
                *,
                decision_action: SupervisorAction,
                issue_ids: list[str],
                target_branch_ids: list[str],
            ) -> tuple[list[ResearchTask], list[BranchRevisionBrief], list[str]]:
                blocking_issues = [
                    issue
                    for issue in revision_issues
                    if issue.status in {"open", "accepted"}
                    and issue.blocking
                    and (not issue_ids or issue.id in issue_ids)
                    and (not target_branch_ids or str(issue.branch_id or "").strip() in set(target_branch_ids))
                ]
                grouped: dict[str, list[RevisionIssue]] = defaultdict(list)
                for issue in blocking_issues:
                    grouped[str(issue.branch_id or "root")].append(issue)
                tasks: list[ResearchTask] = []
                briefs: list[BranchRevisionBrief] = []
                branch_ids: list[str] = []
                revision_kind = {
                    SupervisorAction.PATCH_BRANCH: "patch_branch",
                    SupervisorAction.SPAWN_FOLLOW_UP_BRANCH: "spawn_follow_up_branch",
                    SupervisorAction.SPAWN_COUNTEREVIDENCE_BRANCH: "spawn_counterevidence_branch",
                }.get(decision_action, "patch_branch")
                for source_branch_key, branch_issues in grouped.items():
                    source_branch_id = source_branch_key if source_branch_key != "root" else view.root_branch_id
                    source_brief = view.artifact_store.get_brief(source_branch_id or "")
                    source_task = None
                    if source_brief and source_brief.latest_task_id:
                        source_task = view.task_queue.get(source_brief.latest_task_id)
                    if source_task is None and branch_issues[0].task_id:
                        source_task = view.task_queue.get(branch_issues[0].task_id)
                    source_synthesis = _latest_branch_synthesis(source_branch_id)
                    target_branch_id = (
                        source_branch_id
                        if revision_kind == "patch_branch"
                        else support._new_id("branch")
                    )
                    suggested_queries = _dedupe_texts(
                        [
                            query
                            for issue in branch_issues
                            for query in issue.suggested_queries
                        ]
                        + (_derive_branch_queries(source_task) if source_task else [])
                    )
                    objective_seed = (
                        source_brief.objective
                        if source_brief and source_brief.objective
                        else (
                            source_task.objective
                            if source_task and source_task.objective
                            else branch_issues[0].summary
                        )
                    )
                    task_title = (
                        f"修订 {objective_seed}"
                        if revision_kind == "patch_branch"
                        else (
                            f"补充分支 {objective_seed}"
                            if revision_kind == "spawn_follow_up_branch"
                            else f"反证分支 {objective_seed}"
                        )
                    )
                    completion_criteria = _dedupe_texts(
                        [
                            *[issue.summary for issue in branch_issues],
                            *(source_task.acceptance_criteria if source_task else []),
                        ]
                    )[:6]
                    revision_brief = BranchRevisionBrief(
                        id=support._new_id("revision_brief"),
                        revision_kind=revision_kind,
                        target_branch_id=target_branch_id,
                        target_task_id=None,
                        issue_ids=[issue.id for issue in branch_issues],
                        summary=task_title,
                        source_branch_id=source_branch_id,
                        source_task_id=source_task.id if source_task else None,
                        reusable_artifact_ids=_dedupe_texts(
                            [
                                *(source_brief.input_artifact_ids if source_brief else []),
                                source_synthesis.id if source_synthesis else "",
                                *[
                                    artifact_id
                                    for issue in branch_issues
                                    for artifact_id in [issue.id, *issue.artifact_ids]
                                ],
                            ]
                        ),
                        suggested_queries=suggested_queries,
                        completion_criteria=completion_criteria,
                        metadata={
                            "source_branch_id": source_branch_id,
                            "source_task_id": source_task.id if source_task else None,
                            "issue_ids": [issue.id for issue in branch_issues],
                        },
                    )
                    query = (
                        suggested_queries[0]
                        if suggested_queries
                        else (
                            source_task.query
                            if source_task and source_task.query
                            else task_title
                        )
                    )
                    task = ResearchTask(
                        id=support._new_id("task"),
                        goal=task_title,
                        query=query,
                        priority=source_task.priority if source_task else 1,
                        objective=task_title,
                        task_kind=(
                            "branch_revision"
                            if revision_kind == "patch_branch"
                            else (
                                "follow_up_branch"
                                if revision_kind == "spawn_follow_up_branch"
                                else "counterevidence_branch"
                            )
                        ),
                        acceptance_criteria=completion_criteria,
                        allowed_tools=list(
                            source_task.allowed_tools
                            if source_task and source_task.allowed_tools
                            else (
                                source_brief.allowed_tools
                                if source_brief and source_brief.allowed_tools
                                else ["search", "read", "extract", "synthesize"]
                            )
                        ),
                        input_artifact_ids=_dedupe_texts(
                            [
                                research_brief.id if research_brief else "",
                                *(source_brief.input_artifact_ids if source_brief else []),
                                source_synthesis.id if source_synthesis else "",
                                *revision_brief.reusable_artifact_ids,
                            ]
                        ),
                        output_artifact_types=list(
                            source_task.output_artifact_types
                            if source_task and source_task.output_artifact_types
                            else ["source_candidate", "fetched_document", "evidence_passage", "branch_synthesis"]
                        ),
                        query_hints=suggested_queries or [query],
                        stage="planned",
                        title=task_title,
                        aspect=source_task.aspect if source_task else "",
                        branch_id=target_branch_id,
                        parent_task_id=source_task.id if source_task else None,
                        parent_context_id=str(research_brief.id if research_brief else view.root_branch_id or ""),
                        revision_kind=revision_kind,
                        revision_of_task_id=source_task.id if source_task else None,
                        revision_brief_id=revision_brief.id,
                        target_issue_ids=[issue.id for issue in branch_issues],
                    )
                    revision_brief.target_task_id = task.id
                    tasks.append(task)
                    briefs.append(revision_brief)
                    branch_ids.append(target_branch_id or "")
                return tasks, briefs, [branch_id for branch_id in branch_ids if branch_id]

            if decision.action == SupervisorAction.RETRY_BRANCH:
                ready_for_retry = []
                for task_id in decision.retry_task_ids:
                    existing_task = view.task_queue.get(task_id)
                    if not existing_task or existing_task.attempts >= self.task_retry_limit:
                        continue
                    retried_task = view.task_queue.update_stage(
                        task_id,
                        "dispatch",
                        status="ready",
                        reason="verification_follow_up",
                    )
                    if retried_task:
                        ready_for_retry.append(retried_task)
                        view._emit_task_update(
                            task=retried_task,
                            status=retried_task.status,
                            iteration=view.current_iteration + 1,
                            attempt=retried_task.attempts,
                            reason="verification_follow_up",
                        )
                if ready_for_retry:
                    next_step = "dispatch"
                elif gap_result and gap_result.gaps and not view.budget_stop_reason:
                    next_step = "supervisor_plan"
                    planning_mode = "replan"
                    metadata["retry_fallback"] = "replan"
                else:
                    next_step = "finalize"
                    terminal_reason = (
                        "branch 验证要求补证据，但所有候选任务都已达到重试上限，且当前没有可继续执行的研究分支"
                    )
                latest_decision["retry_task_ids"] = [task.id for task in ready_for_retry]
                metadata["retry_task_ids"] = latest_decision["retry_task_ids"]
            elif decision.action in {
                SupervisorAction.PATCH_BRANCH,
                SupervisorAction.SPAWN_FOLLOW_UP_BRANCH,
                SupervisorAction.SPAWN_COUNTEREVIDENCE_BRANCH,
            }:
                created_tasks, created_revision_briefs, created_branch_ids = _create_revision_work(
                    decision_action=decision.action,
                    issue_ids=decision.issue_ids,
                    target_branch_ids=decision.target_branch_ids,
                )
                if created_tasks and created_revision_briefs:
                    view.task_queue.enqueue(created_tasks)
                    view.artifact_store.add_revision_briefs(created_revision_briefs)
                    generated_obligations: list[CoverageObligation] = []
                    for task, revision_brief in zip(created_tasks, created_revision_briefs, strict=False):
                        source_brief = view.artifact_store.get_brief(revision_brief.source_branch_id or "")
                        if decision.action == SupervisorAction.PATCH_BRANCH and source_brief:
                            source_brief.latest_task_id = task.id
                            source_brief.latest_revision_brief_id = revision_brief.id
                            source_brief.summary = task.title or task.objective or source_brief.summary
                            source_brief.objective = task.objective or source_brief.objective
                            source_brief.current_stage = "planned"
                            source_brief.task_kind = task.task_kind
                            source_brief.acceptance_criteria = list(task.acceptance_criteria)
                            source_brief.allowed_tools = list(task.allowed_tools)
                            source_brief.open_issue_ids = list(
                                dict.fromkeys(task.target_issue_ids + source_brief.open_issue_ids)
                            )
                            source_brief.revision_count += 1
                            source_brief.lineage = {
                                **source_brief.lineage,
                                "revision_kind": task.revision_kind,
                                "revision_of_task_id": task.revision_of_task_id,
                                "source_branch_id": revision_brief.source_branch_id,
                            }
                            view.artifact_store.put_brief(source_brief)
                            branch_brief = source_brief
                        else:
                            branch_brief = BranchBrief(
                                id=task.branch_id or support._new_id("branch"),
                                topic=self.topic,
                                summary=task.title or task.objective or task.goal,
                                objective=task.objective or task.goal,
                                task_kind=task.task_kind,
                                acceptance_criteria=list(task.acceptance_criteria),
                                allowed_tools=list(task.allowed_tools),
                                input_artifact_ids=list(task.input_artifact_ids),
                                context_id=task.parent_context_id,
                                parent_branch_id=revision_brief.source_branch_id,
                                parent_task_id=task.parent_task_id,
                                latest_task_id=task.id,
                                latest_revision_brief_id=revision_brief.id,
                                current_stage="planned",
                                verification_status="pending",
                                open_issue_ids=list(task.target_issue_ids),
                                revision_count=1,
                                lineage={
                                    "revision_kind": task.revision_kind,
                                    "revision_of_task_id": task.revision_of_task_id,
                                    "source_branch_id": revision_brief.source_branch_id,
                                },
                            )
                            view.artifact_store.put_brief(branch_brief)
                        obligations = derive_coverage_obligations(
                            research_brief=research_brief,
                            task=task,
                            branch_id=task.branch_id,
                            revision_brief=revision_brief,
                            created_by="supervisor",
                        )
                        generated_obligations.extend(obligations)
                        branch_brief.obligation_ids = [item.id for item in obligations]
                        view.artifact_store.put_brief(branch_brief)
                        _emit_revision_brief(revision_brief)
                        view._emit_artifact_update(
                            artifact_id=branch_brief.id,
                            artifact_type="branch_brief",
                            status=branch_brief.status,
                            branch_id=branch_brief.id,
                            task_id=branch_brief.latest_task_id,
                            summary=branch_brief.summary[:180],
                            task_kind=branch_brief.task_kind,
                            stage="planned",
                            extra={
                                "objective_summary": branch_brief.objective,
                                "latest_revision_brief_id": branch_brief.latest_revision_brief_id,
                                "open_issue_ids": list(branch_brief.open_issue_ids),
                                "lineage": copy.deepcopy(branch_brief.lineage),
                            },
                        )
                        view._emit_task_update(
                            task=task,
                            status=task.status,
                            iteration=max(1, view.current_iteration + 1),
                            attempt=task.attempts,
                        )
                    if generated_obligations:
                        view.artifact_store.add_coverage_obligations(generated_obligations)
                        for obligation in generated_obligations:
                            view._emit_artifact_update(
                                artifact_id=obligation.id,
                                artifact_type="coverage_obligation",
                                status=obligation.status,
                                task_id=obligation.task_id,
                                branch_id=obligation.branch_id,
                                agent_id=obligation.created_by,
                                summary=obligation.target[:180],
                                stage="planned",
                                extra={
                                    "completion_criteria": list(obligation.completion_criteria),
                                    "source": obligation.source,
                                },
                            )
                    for revision_brief in created_revision_briefs:
                        for issue_id in revision_brief.issue_ids:
                            updated_issue = view.artifact_store.update_revision_issue_status(
                                issue_id,
                                "accepted",
                                resolution={
                                    "assigned_revision_brief_id": revision_brief.id,
                                    "assigned_task_id": revision_brief.target_task_id,
                                    "assigned_branch_id": revision_brief.target_branch_id,
                                },
                            )
                            if updated_issue:
                                view._emit_artifact_update(
                                    artifact_id=updated_issue.id,
                                    artifact_type="revision_issue",
                                    status=updated_issue.status,
                                    task_id=updated_issue.task_id,
                                    branch_id=updated_issue.branch_id,
                                    agent_id="supervisor",
                                    summary=updated_issue.summary[:180],
                                    stage="loop_decision",
                                    extra={
                                        "issue_type": updated_issue.issue_type,
                                        "recommended_action": updated_issue.recommended_action,
                                        "resolution": copy.deepcopy(updated_issue.resolution),
                                    },
                                )
                    next_step = "dispatch"
                    latest_decision["task_ids"] = [task.id for task in created_tasks]
                    latest_decision["revision_brief_ids"] = [brief.id for brief in created_revision_briefs]
                    metadata["task_ids"] = latest_decision["task_ids"]
                    metadata["revision_brief_ids"] = latest_decision["revision_brief_ids"]
                else:
                    next_step = "finalize"
                    terminal_reason = "存在 blocking revision issues，但当前无法为其创建有效的 revision task"
            elif decision.action == SupervisorAction.PLAN:
                next_step = "supervisor_plan"
                planning_mode = "initial"
            elif decision.action == SupervisorAction.REPLAN:
                next_step = "supervisor_plan"
                planning_mode = "replan"
            elif decision.action == SupervisorAction.DISPATCH:
                if view.task_queue.ready_count() > 0:
                    next_step = "dispatch"
                elif gap_result and gap_result.gaps:
                    next_step = "supervisor_plan"
                    planning_mode = "replan"
                else:
                    next_step = (
                        "report"
                        if outline_artifact and outline_artifact.is_ready and not outline_artifact.blocking_gaps
                        else "outline_gate"
                    )
            elif decision.action == SupervisorAction.STOP:
                next_step = (
                    "report"
                    if outline_artifact and outline_artifact.is_ready and not outline_artifact.blocking_gaps
                    else "outline_gate"
                )
            elif decision.action == SupervisorAction.BOUNDED_STOP:
                next_step = "finalize"
                terminal_reason = decision.reasoning

            outline_ready = bool(
                outline_artifact and outline_artifact.is_ready and not outline_artifact.blocking_gaps
            )
            outline_blocked = bool(outline_artifact and not outline_ready)
            if decision.action in {SupervisorAction.REPORT, SupervisorAction.STOP} and outline_blocked:
                next_step = "finalize"
                terminal_reason = (
                    f"{decision.reasoning}；outline 仍存在阻塞性缺口，无法生成最终报告"
                )

            for request in open_requests:
                resolved_status = (
                    "accepted"
                    if (
                        request.id in decision.request_ids
                        or any(issue_id in request.issue_ids for issue_id in decision.issue_ids)
                        or (request.branch_id in created_branch_ids if created_branch_ids else False)
                    )
                    else request.status
                )
                updated = view.artifact_store.update_coordination_request_status(
                    request.id,
                    resolved_status,
                    metadata={"resolved_by": "supervisor", "next_step": next_step},
                )
                if updated and updated.status != request.status:
                    view._emit_artifact_update(
                        artifact_id=updated.id,
                        artifact_type="coordination_request",
                        status=updated.status,
                        task_id=updated.task_id,
                        branch_id=updated.branch_id,
                        agent_id="supervisor",
                        summary=updated.summary[:180],
                        stage="loop_decision",
                        extra={"request_type": updated.request_type},
                    )

            if terminal_reason:
                metadata["terminal_reason"] = terminal_reason
                view.set_terminal_state(status="blocked", reason=terminal_reason)

            decision_artifact = view.record_supervisor_decision(
                phase="loop_decision",
                decision_type=decision.action.value,
                summary=decision.reasoning,
                next_step=next_step,
                planning_mode=planning_mode,
                task_ids=list(
                    latest_decision.get("retry_task_ids", [])
                    or latest_decision.get("task_ids", [])
                ),
                request_ids=list(decision.request_ids),
                issue_ids=list(decision.issue_ids),
                revision_brief_ids=list(latest_decision.get("revision_brief_ids", [])),
                metadata={
                    **metadata,
                    "research_brief_id": research_brief.id if research_brief else "",
                    "task_ledger_id": task_ledger.id if task_ledger else "",
                    "progress_ledger_id": progress_ledger.id if progress_ledger else "",
                    "coverage_matrix_id": coverage_matrix.id if coverage_matrix else "",
                    "outline_id": outline_artifact.id if outline_artifact else "",
                },
            )
            view.sync_progress_ledger(
                phase="loop_decision",
                reason=decision.reasoning,
                created_by="supervisor",
                decision={
                    "id": decision_artifact.id,
                    "decision_type": decision.action.value,
                    "reasoning": decision.reasoning,
                    "next_step": next_step,
                    "issue_ids": list(decision.issue_ids),
                },
                verification_summary=verification_summary,
                outline_status=(
                    "blocked"
                    if terminal_reason or outline_blocked
                    else ("ready" if outline_ready else "pending")
                ),
                stop_reason=terminal_reason
                or (decision.reasoning if decision.action == SupervisorAction.STOP else None),
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=f"{decision.action.value}: {decision.reasoning}",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(
                next_step=next_step,
                planning_mode=planning_mode,
                latest_decision={
                    **latest_decision,
                    "id": decision_artifact.id,
                    "next_step": next_step,
                    "planning_mode": planning_mode,
                },
            )
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            raise

    def _route_after_supervisor_decide(self, graph_state: MultiAgentGraphState) -> str:
        next_step = str(graph_state.get("next_step") or "report").strip().lower()
        if next_step in {"supervisor_plan", "dispatch", "outline_gate", "report", "finalize"}:
            return next_step
        return "outline_gate"

    def _outline_gate_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "outline_gate")
        record = view.start_agent_run(
            role="reporter",
            phase="outline_gate",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
        )
        try:
            claim_results = {
                result.task_id: result
                for result in view.artifact_store.verification_results(validation_stage="claim_check")
            }
            coverage_results = {
                result.task_id: result
                for result in view.artifact_store.verification_results(validation_stage="coverage_check")
            }
            latest_syntheses = latest_branch_syntheses(
                view.artifact_store.branch_syntheses(),
                view.artifact_store.branch_briefs(),
            )
            blocking_issue_branch_ids = {
                issue.branch_id
                for issue in view.artifact_store.revision_issues()
                if issue.blocking and issue.status in {"open", "accepted"} and issue.branch_id
            }
            verified_syntheses = [
                synthesis
                for synthesis in latest_syntheses
                if claim_results.get(synthesis.task_id)
                and coverage_results.get(synthesis.task_id)
                and claim_results[synthesis.task_id].outcome == "passed"
                and coverage_results[synthesis.task_id].outcome == "passed"
                and synthesis.branch_id not in blocking_issue_branch_ids
            ]
            research_brief = view.artifact_store.research_brief()
            coverage_matrix = view.artifact_store.coverage_matrix()
            contradiction_registry = view.artifact_store.contradiction_registry()
            missing_evidence_list = view.artifact_store.missing_evidence_list()
            revision_issues = view.artifact_store.revision_issues()
            outline_artifact = _build_outline_artifact(
                view=view,
                research_brief=research_brief,
                verified_syntheses=verified_syntheses,
                coverage_matrix=coverage_matrix,
                contradiction_registry=contradiction_registry,
                missing_evidence_list=missing_evidence_list,
                revision_issues=revision_issues,
            )
            view.artifact_store.set_outline(outline_artifact)
            view.runtime_state["outline_id"] = outline_artifact.id
            view.runtime_state["outline_status"] = "ready" if outline_artifact.is_ready else "blocked"
            view._emit_artifact_update(
                artifact_id=outline_artifact.id,
                artifact_type="outline",
                status=outline_artifact.status,
                branch_id=view.root_branch_id,
                agent_id=outline_artifact.created_by,
                summary=(
                    f"outline ready with {len(outline_artifact.sections)} sections"
                    if outline_artifact.is_ready
                    else f"outline blocked by {len(outline_artifact.blocking_gaps)} gaps"
                )[:180],
                stage="outline_gate",
                extra={
                    "section_count": len(outline_artifact.sections),
                    "blocking_gap_count": len(outline_artifact.blocking_gaps),
                    "is_ready": outline_artifact.is_ready,
                },
            )

            next_step = "report"
            if outline_artifact.blocking_gaps:
                existing_outline_gaps = [
                    request
                    for request in view.artifact_store.coordination_requests(status="open")
                    if request.request_type == "outline_gap"
                ]
                if not existing_outline_gaps:
                    request = CoordinationRequest(
                        id=support._new_id("request"),
                        request_type="outline_gap",
                        summary="outline 仍存在阻塞性结构缺口，需要 supervisor 回到研究回路",
                        branch_id=view.root_branch_id,
                        requested_by=record.agent_id,
                        artifact_ids=[
                            outline_artifact.id,
                            *[
                                artifact_id
                                for gap in outline_artifact.blocking_gaps
                                for artifact_id in gap.get("artifact_ids", [])
                                if artifact_id
                            ],
                        ],
                        impact_scope=str(view.root_branch_id or "outline"),
                        reason="最终报告大纲仍无法稳定支撑目标输出结构",
                        blocking_level="blocking",
                        suggested_next_action="supervisor_review",
                    )
                    view.artifact_store.add_coordination_requests([request])
                    view._emit_artifact_update(
                        artifact_id=request.id,
                        artifact_type="coordination_request",
                        status=request.status,
                        branch_id=request.branch_id,
                        agent_id=request.requested_by,
                        summary=request.summary[:180],
                        stage="outline_gate",
                        extra={
                            "request_type": request.request_type,
                            "artifact_ids": list(request.artifact_ids),
                        },
                    )
                view.runtime_state["supervisor_request_ids"] = [
                    request.id for request in view.artifact_store.coordination_requests(status="open")
                ]
                view.sync_progress_ledger(
                    phase="outline_gate",
                    reason="outline gate 发现结构缺口，控制权回到 supervisor",
                    created_by="reporter",
                    outline_status="blocked",
                )
                view._emit_decision(
                    decision_type="outline_gap_detected",
                    reason="outline 发现结构缺口，需要回到研究闭环",
                    iteration=view.current_iteration,
                    attempt=view.graph_attempt,
                    extra={"blocking_gap_count": len(outline_artifact.blocking_gaps)},
                )
                next_step = "supervisor_decide"
            else:
                for request in view.artifact_store.coordination_requests(status="open"):
                    if request.request_type != "outline_gap":
                        continue
                    view.artifact_store.update_coordination_request_status(
                        request.id,
                        "resolved",
                        metadata={"resolved_by": "outline_gate"},
                    )
                view.sync_progress_ledger(
                    phase="outline_gate",
                    reason="outline 已就绪，可进入最终报告生成",
                    created_by="reporter",
                    outline_status="ready",
                )
                view._emit_decision(
                    decision_type="outline_ready",
                    reason="outline 已就绪，允许 reporter 进入最终成文",
                    iteration=view.current_iteration,
                    attempt=view.graph_attempt,
                )

            view.finish_agent_run(
                record,
                status="completed",
                summary=(
                    f"outline sections={len(outline_artifact.sections)}, blocked={len(outline_artifact.blocking_gaps)}"
                ),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step=next_step)
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            raise

    def _report_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "report")
        outline_artifact = view.artifact_store.outline()
        if outline_artifact is None or not outline_artifact.is_ready or outline_artifact.blocking_gaps:
            return view.snapshot_patch(next_step="outline_gate")
        record = view.start_agent_run(
            role="reporter",
            phase="final_report",
            branch_id=view.root_branch_id,
            iteration=view.current_iteration,
            attempt=view.graph_attempt,
        )
        try:
            coverage_results = {
                result.task_id: result
                for result in view.artifact_store.verification_results(validation_stage="coverage_check")
            }
            claim_results = {
                result.task_id: result
                for result in view.artifact_store.verification_results(validation_stage="claim_check")
            }
            latest_syntheses = latest_branch_syntheses(
                view.artifact_store.branch_syntheses(),
                view.artifact_store.branch_briefs(),
            )
            blocking_issue_branch_ids = {
                issue.branch_id
                for issue in view.artifact_store.revision_issues()
                if issue.blocking and issue.status in {"open", "accepted"} and issue.branch_id
            }
            verified_syntheses = [
                synthesis
                for synthesis in latest_syntheses
                if claim_results.get(synthesis.task_id)
                and coverage_results.get(synthesis.task_id)
                and claim_results[synthesis.task_id].outcome == "passed"
                and coverage_results[synthesis.task_id].outcome == "passed"
                and synthesis.branch_id not in blocking_issue_branch_ids
            ]
            source_catalog = _build_report_source_catalog(view)
            report_context = _build_report_context(
                topic=self.topic,
                outline_artifact=outline_artifact,
                verified_syntheses=verified_syntheses,
                source_catalog=source_catalog,
            )
            citation_urls = [source.url for source in report_context.sources]

            tool_session = self._try_reporter_tool_agent(
                view=view,
                verified_syntheses=verified_syntheses,
                citation_urls=citation_urls,
                outline_artifact=outline_artifact,
            )
            report_submissions: list[ResearchSubmission] = []
            if tool_session is not None and tool_session.final_report is not None:
                final_artifact = tool_session.final_report
                report_submissions = list(tool_session.submissions)
            else:
                final_report = self.reporter.generate_report(
                    report_context,
                )
                final_artifact = FinalReportArtifact(
                    id=support._new_id("final_report"),
                    report_markdown=final_report,
                    executive_summary="",
                    citation_urls=citation_urls,
                    created_by=record.agent_id,
                )
                report_submissions = [
                    ResearchSubmission(
                        id=support._new_id("submission"),
                        submission_kind="report_bundle",
                        summary=final_report[:240],
                        branch_id=view.root_branch_id,
                        created_by=record.agent_id,
                        result_status="completed",
                        stage="submit",
                        artifact_ids=[final_artifact.id],
                    )
                ]

            normalized_sources = _resolve_report_sources(
                list(final_artifact.citation_urls) + [source.url for source in report_context.sources],
                source_catalog=source_catalog,
            )
            final_artifact.report_markdown, final_artifact.citation_urls = self.reporter.normalize_report(
                final_artifact.report_markdown,
                normalized_sources,
                title=self.topic,
            )
            executive_summary = final_artifact.executive_summary or self.reporter.generate_executive_summary(
                final_artifact.report_markdown,
                self.topic,
            )
            final_artifact.executive_summary = executive_summary
            for submission in report_submissions:
                if submission.submission_kind == "report_bundle":
                    submission.summary = executive_summary[:240] or final_artifact.report_markdown[:240]
            view.artifact_store.set_final_report(final_artifact)
            if report_submissions:
                view.artifact_store.add_submissions(report_submissions)
                for submission in report_submissions:
                    view._emit_artifact_update(
                        artifact_id=submission.id,
                        artifact_type="report_submission",
                        status=submission.status,
                        branch_id=submission.branch_id,
                        agent_id=submission.created_by,
                        summary=submission.summary[:180],
                        stage=submission.stage or "submit",
                        extra={
                            "submission_kind": submission.submission_kind,
                            "result_status": submission.result_status,
                            "artifact_ids": list(submission.artifact_ids),
                        },
                    )
            view._emit_artifact_update(
                artifact_id=final_artifact.id,
                artifact_type="final_report",
                status=final_artifact.status,
                agent_id=final_artifact.created_by,
                summary=executive_summary[:180],
            )
            view.sync_progress_ledger(
                phase="final_report",
                reason="最终报告已生成",
                created_by="reporter",
                outline_status="ready",
            )
            view.finish_agent_run(
                record,
                status="completed",
                summary=executive_summary[:240] or "完成最终报告生成",
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            return view.snapshot_patch(next_step="finalize")
        except Exception as exc:
            view.finish_agent_run(
                record,
                status="failed",
                summary=str(exc),
                iteration=view.current_iteration,
                branch_id=view.root_branch_id,
            )
            raise

    def _finalize_node(self, graph_state: MultiAgentGraphState) -> dict[str, Any]:
        view = self._view(graph_state, "finalize")
        gap_result = _gap_result_from_payload(
            graph_state.get("latest_gap_result") or view.runtime_state.get("last_gap_result")
        )
        final_artifact = view.artifact_store.final_report()
        report_text = final_artifact.report_markdown if final_artifact else ""
        executive_summary = final_artifact.executive_summary if final_artifact else ""
        terminal_status = view.terminal_status
        terminal_reason = view.terminal_reason
        if not report_text and terminal_reason:
            report_text = f"Deep Research 未能完成：{terminal_reason}"
        if not executive_summary and terminal_status == "blocked":
            executive_summary = "Deep Research 已停止"
        evidence_cards = view.artifact_store.evidence_cards()
        quality_summary = view._quality_summary(gap_result)
        sources = support._compact_sources(
            [card.to_dict() for card in evidence_cards],
            limit=max(5, min(20, len(evidence_cards))),
        )
        elapsed = max(0.0, time.time() - self.start_ts)

        deep_research_artifacts = build_public_deep_research_artifacts(
            task_queue=view.task_queue.snapshot(),
            artifact_store=view.artifact_store.snapshot(),
            research_topology=view._research_topology_snapshot(),
            quality_summary=quality_summary,
            runtime_state=view.runtime_state_snapshot(),
            mode="multi_agent",
            engine="multi_agent",
        )

        view._emit(
            events.ToolEventType.RESEARCH_NODE_COMPLETE,
            {
                "node_id": "deep_research_multi_agent",
                "summary": executive_summary or report_text[:1200],
                "sources": sources,
                "quality": quality_summary,
                "engine": "multi_agent",
                "iteration": view.current_iteration,
                "graph_run_id": view.graph_run_id,
                "graph_attempt": view.graph_attempt,
                "branch_id": view.root_branch_id,
            },
        )

        messages = [AIMessage(content=report_text)]
        if executive_summary:
            messages.append(AIMessage(content=f"执行摘要: {executive_summary}"))
        if view.budget_stop_reason:
            messages.append(AIMessage(content=f"(预算限制提示: {view.budget_stop_reason})"))

        view.runtime_state["next_step"] = "completed"
        deep_runtime_snapshot = build_deep_runtime_snapshot(
            engine="multi_agent",
            task_queue=view.task_queue.snapshot(),
            artifact_store=view.artifact_store.snapshot(),
            runtime_state=view.runtime_state_snapshot(),
            agent_runs=[run.to_dict() for run in view.agent_runs],
        )
        result = {
            "deep_runtime": deep_runtime_snapshot,
            "research_plan": [task.query for task in view.task_queue.all_tasks()],
            "scraped_content": view.shared_state.get("scraped_content", []),
            "draft_report": report_text,
            "final_report": report_text,
            "quality_summary": quality_summary,
            "sources": sources,
            "deep_research_artifacts": deep_research_artifacts,
            "research_topology": view._research_topology_snapshot(),
            "messages": messages,
            "is_complete": True,
            "budget_stop_reason": view.budget_stop_reason,
            "terminal_status": terminal_status,
            "terminal_reason": terminal_reason,
            "errors": view.shared_state.get("errors", []),
            "sub_agent_contexts": view.shared_state.get("sub_agent_contexts", {}),
        }
        return view.snapshot_patch(final_result=result, next_step="completed")

    def build_graph(self, *, checkpointer: Any = None, interrupt_before: Any = None):
        workflow = StateGraph(MultiAgentGraphState)
        workflow.add_node("bootstrap", self._bootstrap_node)
        workflow.add_node("clarify", self._clarify_node)
        workflow.add_node("scope", self._scope_node)
        workflow.add_node("scope_review", self._scope_review_node)
        workflow.add_node("research_brief", self._research_brief_node)
        workflow.add_node("supervisor_plan", self._supervisor_plan_node)
        workflow.add_node("dispatch", self._dispatch_node)
        workflow.add_node("researcher", self._researcher_node)
        workflow.add_node("merge", self._merge_node)
        workflow.add_node("verify", self._verify_node)
        workflow.add_node("supervisor_decide", self._supervisor_decide_node)
        workflow.add_node("outline_gate", self._outline_gate_node)
        workflow.add_node("report", self._report_node)
        workflow.add_node("finalize", self._finalize_node)

        workflow.set_entry_point("bootstrap")
        workflow.add_conditional_edges(
            "bootstrap",
            self._route_after_bootstrap,
            [
                "clarify",
                "scope",
                "scope_review",
                "research_brief",
                "supervisor_plan",
                "dispatch",
                "verify",
                "supervisor_decide",
                "outline_gate",
                "report",
                "finalize",
            ],
        )
        workflow.add_conditional_edges(
            "clarify",
            self._route_after_clarify,
            ["clarify", "scope"],
        )
        workflow.add_edge("scope", "scope_review")
        workflow.add_conditional_edges(
            "scope_review",
            self._route_after_scope_review,
            ["scope", "research_brief"],
        )
        workflow.add_edge("research_brief", "supervisor_plan")
        workflow.add_conditional_edges(
            "supervisor_plan",
            self._route_after_supervisor_plan,
            ["scope_review", "research_brief", "dispatch", "finalize"],
        )
        workflow.add_conditional_edges(
            "dispatch",
            self._route_after_dispatch,
            ["researcher", "verify"],
        )
        workflow.add_edge("researcher", "merge")
        workflow.add_edge("merge", "verify")
        workflow.add_edge("verify", "supervisor_decide")
        workflow.add_conditional_edges(
            "supervisor_decide",
            self._route_after_supervisor_decide,
            ["supervisor_plan", "dispatch", "outline_gate", "report", "finalize"],
        )
        workflow.add_conditional_edges(
            "outline_gate",
            lambda graph_state: str(graph_state.get("next_step") or "report").strip().lower()
            if str(graph_state.get("next_step") or "report").strip().lower()
            in {"supervisor_decide", "report", "finalize"}
            else "report",
            ["supervisor_decide", "report", "finalize"],
        )
        workflow.add_edge("report", "finalize")
        workflow.add_edge("finalize", END)
        return workflow.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)

    def run(self) -> dict[str, Any]:
        try:
            graph = self.build_graph()
            output = graph.invoke(self.build_initial_graph_state(), self.config)
            if isinstance(output, dict) and isinstance(output.get("final_result"), dict):
                return output["final_result"]
            return output if isinstance(output, dict) else {}
        except asyncio.CancelledError:
            return {
                "is_cancelled": True,
                "is_complete": True,
                "errors": ["Deep Research was cancelled"],
                "final_report": "任务已被取消",
            }


def create_multi_agent_deep_research_graph(
    state: dict[str, Any],
    config: dict[str, Any],
    *,
    checkpointer: Any = None,
    interrupt_before: Any = None,
):
    runtime = MultiAgentDeepResearchRuntime(state, config)
    return runtime.build_graph(checkpointer=checkpointer, interrupt_before=interrupt_before)


def run_multi_agent_deep_research(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    runtime = MultiAgentDeepResearchRuntime(state, config)
    return runtime.run()


__all__ = [
    "GapAnalysisResult",
    "MultiAgentDeepResearchRuntime",
    "create_multi_agent_deep_research_graph",
    "run_multi_agent_deep_research",
]
