"""Final reporting and completion helpers for the Deep Research engine."""

from __future__ import annotations

import copy
from typing import Any

from langchain_core.messages import AIMessage

from agent.deep_research.agents.reporter import ReportContext, ReportSectionContext, ReportSource
from agent.deep_research.artifacts.public_artifacts import build_public_deep_research_artifacts
from agent.deep_research.engine.artifact_store import LightweightArtifactStore
from agent.deep_research.schema import FinalReportArtifact
from agent.deep_research.store import ResearchTaskQueue
from agent.foundation.source_urls import canonicalize_source_url
from agent.foundation.state import build_deep_runtime_snapshot


def build_final_report_artifact(
    *,
    topic: str,
    report_sections: list[ReportSectionContext],
    artifact_store: LightweightArtifactStore,
    reporter: Any,
    created_by: str,
    final_report_id: str,
) -> dict[str, Any]:
    report_context = ReportContext(
        topic=topic,
        sections=report_sections,
        sources=_report_sources(report_sections, artifact_store),
    )
    report_markdown = reporter.generate_report(report_context)
    normalized_report, citation_urls = reporter.normalize_report(
        report_markdown,
        report_context.sources,
        title=topic,
    )
    executive_summary = reporter.generate_executive_summary(
        normalized_report,
        topic,
        report_context=report_context,
    )
    return FinalReportArtifact(
        id=final_report_id,
        report_markdown=normalized_report,
        executive_summary=executive_summary,
        citation_urls=citation_urls,
        created_by=created_by,
    ).to_dict()


def run_final_claim_gate(
    *,
    report: str,
    scraped_content: list[dict[str, Any]],
    passages: list[dict[str, Any]],
) -> dict[str, Any]:
    from agent.contracts.claim_verifier import ClaimStatus, ClaimVerifier

    verifier = ClaimVerifier()
    checks = verifier.verify_report(
        report,
        scraped_content,
        passages=passages,
    )
    contradicted = [item for item in checks if item.status == ClaimStatus.CONTRADICTED]
    unsupported = [item for item in checks if item.status == ClaimStatus.UNSUPPORTED]
    verified = [item for item in checks if item.status == ClaimStatus.VERIFIED]
    return {
        "claim_verifier_total": len(checks),
        "claim_verifier_verified": len(verified),
        "claim_verifier_unsupported": len(unsupported),
        "claim_verifier_contradicted": len(contradicted),
        "passed": len(contradicted) == 0,
        "review_needed": bool(contradicted or unsupported),
    }


def build_finalize_outputs(
    *,
    root_branch_id: str,
    current_iteration: int,
    task_queue: ResearchTaskQueue,
    artifact_store: LightweightArtifactStore,
    runtime_state: dict[str, Any],
    agent_runs: list[dict[str, Any]],
    shared_state: dict[str, Any],
    quality_summary: dict[str, Any],
    research_topology: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    final_artifact = artifact_store.final_report()
    final_report = str(final_artifact.get("report_markdown") or "")
    if not final_report and runtime_state.get("terminal_reason"):
        final_report = f"Deep Research 未能完成：{runtime_state['terminal_reason']}"

    task_queue_snapshot = task_queue.snapshot()
    artifact_store_snapshot = artifact_store.snapshot()
    deep_research_artifacts = build_public_deep_research_artifacts(
        task_queue=task_queue_snapshot,
        artifact_store=artifact_store_snapshot,
        research_topology=research_topology,
        quality_summary=quality_summary,
        runtime_state=runtime_state,
        mode="multi_agent",
        engine="multi_agent",
    )
    node_complete_payload = {
        "node_id": "deep_research_multi_agent",
        "summary": str(final_artifact.get("executive_summary") or final_report[:1200]),
        "sources": deep_research_artifacts.get("sources", []),
        "quality": quality_summary,
        "branch_id": root_branch_id,
        "iteration": current_iteration,
    }
    result = {
        "deep_runtime": build_deep_runtime_snapshot(
            engine="multi_agent",
            task_queue=task_queue_snapshot,
            artifact_store=artifact_store_snapshot,
            runtime_state=runtime_state,
            agent_runs=agent_runs,
        ),
        "research_plan": [task.query for task in task_queue.all_tasks()],
        "scraped_content": copy.deepcopy(shared_state.get("scraped_content") or []),
        "draft_report": final_report,
        "final_report": final_report,
        "quality_summary": quality_summary,
        "sources": copy.deepcopy(deep_research_artifacts.get("sources") or []),
        "deep_research_artifacts": deep_research_artifacts,
        "research_topology": research_topology,
        "messages": [AIMessage(content=final_report)] if final_report else [],
        "is_complete": True,
        "budget_stop_reason": runtime_state.get("budget_stop_reason", ""),
        "terminal_status": runtime_state.get("terminal_status", ""),
        "terminal_reason": runtime_state.get("terminal_reason", ""),
        "errors": list(shared_state.get("errors") or []),
        "sub_agent_contexts": copy.deepcopy(shared_state.get("sub_agent_contexts") or {}),
    }
    return node_complete_payload, result


def _report_sources(
    report_sections: list[ReportSectionContext],
    artifact_store: LightweightArtifactStore,
) -> list[ReportSource]:
    all_sources = [
        ReportSource(
            url=str(item.get("url") or ""),
            title=str(item.get("title") or item.get("url") or ""),
            provider=str(item.get("provider") or ""),
            published_date=item.get("published_date"),
        )
        for item in artifact_store.all_sources()
        if str(item.get("url") or "").strip()
    ]
    referenced_urls: list[str] = []
    seen_referenced_urls: set[str] = set()
    for section in report_sections:
        for raw_url in section.citation_urls:
            normalized_url = canonicalize_source_url(raw_url)
            if not normalized_url or normalized_url in seen_referenced_urls:
                continue
            seen_referenced_urls.add(normalized_url)
            referenced_urls.append(normalized_url)

    if not referenced_urls:
        return all_sources

    source_by_url = {
        canonicalize_source_url(source.url): source
        for source in all_sources
        if canonicalize_source_url(source.url)
    }
    return [
        source_by_url.get(url) or ReportSource(url=url, title=url)
        for url in referenced_urls
    ]
