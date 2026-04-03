"""
Public Deep Research artifact adapters derived from the multi-agent runtime.
"""

from __future__ import annotations

from typing import Any

from agent.runtime.deep.state import read_deep_runtime_snapshot, resolve_deep_runtime_mode
from agent.research.source_url_utils import canonicalize_source_url, compact_unique_sources


def _sorted_tasks(task_queue: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = task_queue.get("tasks", []) if isinstance(task_queue, dict) else []
    if not isinstance(tasks, list):
        return []
    return sorted(
        (task for task in tasks if isinstance(task, dict)),
        key=lambda item: (
            int(item.get("priority", 0) or 0),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )


def _build_queries(task_queue: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for task in _sorted_tasks(task_queue):
        text = str(task.get("query") or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        queries.append(text)
    return queries


def _normalize_fetched_pages(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    items = artifact_store.get("fetched_documents", []) if isinstance(artifact_store, dict) else []
    pages: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = canonicalize_source_url(item.get("url"))
        if not url:
            continue
        pages.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "branch_id": item.get("branch_id"),
                "url": url,
                "title": str(item.get("title") or "").strip(),
                "excerpt": str(item.get("excerpt") or "").strip(),
                "content": str(item.get("content") or ""),
                "source_candidate_id": item.get("source_candidate_id"),
            }
        )
    return pages


def _normalize_passages(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    items = artifact_store.get("evidence_passages", []) if isinstance(artifact_store, dict) else []
    passages: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = canonicalize_source_url(item.get("url"))
        if not url:
            continue
        passage = {
            "id": item.get("id"),
            "task_id": item.get("task_id"),
            "branch_id": item.get("branch_id"),
            "document_id": item.get("document_id"),
            "url": url,
            "text": str(item.get("text") or ""),
            "quote": str(item.get("quote") or "").strip(),
            "source_title": str(item.get("source_title") or "").strip(),
            "snippet_hash": str(item.get("snippet_hash") or "").strip(),
            "heading_path": list(item.get("heading_path") or []),
        }
        passages.append(passage)
    return passages


def _normalize_sources(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    evidence_cards = artifact_store.get("evidence_cards", []) if isinstance(artifact_store, dict) else []
    for item in evidence_cards if isinstance(evidence_cards, list) else []:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "title": item.get("source_title", ""),
                "url": item.get("source_url", ""),
                "provider": item.get("source_provider", ""),
                "published_date": item.get("published_date"),
            }
        )

    fetched_documents = artifact_store.get("fetched_documents", []) if isinstance(artifact_store, dict) else []
    for item in fetched_documents if isinstance(fetched_documents, list) else []:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
            }
        )

    source_candidates = artifact_store.get("source_candidates", []) if isinstance(artifact_store, dict) else []
    for item in source_candidates if isinstance(source_candidates, list) else []:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "provider": item.get("source_provider", ""),
                "published_date": item.get("published_date"),
                "score": item.get("rank", 0),
            }
        )

    final_report = artifact_store.get("final_report", {}) if isinstance(artifact_store, dict) else {}
    citation_urls = final_report.get("citation_urls", []) if isinstance(final_report, dict) else []
    for url in citation_urls if isinstance(citation_urls, list) else []:
        candidates.append({"title": str(url or ""), "url": url})

    return compact_unique_sources(candidates, limit=max(5, len(candidates) or 5))


def _normalize_claims(
    artifact_store: dict[str, Any],
    passages_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    claim_units = artifact_store.get("claim_units", []) if isinstance(artifact_store, dict) else []
    grounding_results = (
        artifact_store.get("claim_grounding_results", []) if isinstance(artifact_store, dict) else []
    )
    revision_issues = artifact_store.get("revision_issues", []) if isinstance(artifact_store, dict) else []
    if isinstance(claim_units, list) and claim_units:
        grounding_by_claim: dict[str, dict[str, Any]] = {}
        for item in grounding_results if isinstance(grounding_results, list) else []:
            if not isinstance(item, dict):
                continue
            claim_id = str(item.get("claim_id") or "").strip()
            if claim_id:
                grounding_by_claim[claim_id] = item
        issue_ids_by_claim: dict[str, list[str]] = {}
        for issue in revision_issues if isinstance(revision_issues, list) else []:
            if not isinstance(issue, dict):
                continue
            issue_id = str(issue.get("id") or "").strip()
            if not issue_id:
                continue
            for claim_id in issue.get("claim_ids", []) or []:
                normalized = str(claim_id or "").strip()
                if not normalized:
                    continue
                issue_ids_by_claim.setdefault(normalized, []).append(issue_id)

        claims: list[dict[str, Any]] = []
        for unit in claim_units:
            if not isinstance(unit, dict):
                continue
            claim_id = str(unit.get("id") or "").strip()
            claim_text = str(unit.get("claim") or "").strip()
            if not claim_id or not claim_text:
                continue
            grounding = grounding_by_claim.get(claim_id, {})
            grounding_status = str(grounding.get("status") or "").strip().lower()
            status = (
                "verified"
                if grounding_status == "grounded"
                else ("contradicted" if grounding_status == "contradicted" else grounding_status or "unsupported")
            )
            evidence_passage_ids = list(grounding.get("evidence_passage_ids") or unit.get("evidence_passage_ids") or [])
            evidence_passages = [
                passages_by_id.get(str(passage_id))
                for passage_id in evidence_passage_ids
                if passages_by_id.get(str(passage_id))
            ]
            evidence_urls = [
                canonicalize_source_url(url)
                for url in grounding.get("evidence_urls", []) or unit.get("citation_urls", [])
                if canonicalize_source_url(url)
            ]
            claims.append(
                {
                    "claim_id": claim_id,
                    "claim": claim_text,
                    "status": status,
                    "branch_id": unit.get("branch_id"),
                    "task_id": unit.get("task_id"),
                    "issue_ids": list(dict.fromkeys(issue_ids_by_claim.get(claim_id, []))),
                    "evidence_urls": evidence_urls,
                    "evidence_passages": evidence_passages,
                    "score": grounding.get("metadata", {}).get("score", 0.0)
                    if isinstance(grounding.get("metadata"), dict)
                    else 0.0,
                    "notes": str(grounding.get("summary") or "").strip(),
                    "provenance": dict(unit.get("claim_provenance") or {}),
                }
            )
        return claims

    verification_results = (
        artifact_store.get("verification_results", []) if isinstance(artifact_store, dict) else []
    )
    claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in verification_results if isinstance(verification_results, list) else []:
        if not isinstance(result, dict) or result.get("validation_stage") != "claim_check":
            continue

        metadata = result.get("metadata", {})
        raw_claims = metadata.get("claims", []) if isinstance(metadata, dict) else []
        for item in raw_claims if isinstance(raw_claims, list) else []:
            if not isinstance(item, dict):
                continue
            claim_text = str(item.get("claim") or "").strip()
            status = str(item.get("status") or "").strip().lower()
            key = (claim_text.lower(), status)
            if not claim_text or not status or key in seen:
                continue
            seen.add(key)

            evidence_urls = [
                canonicalize_source_url(url)
                for url in item.get("evidence_urls", [])
                if canonicalize_source_url(url)
            ]
            evidence_passages: list[dict[str, Any]] = []
            raw_passages = item.get("evidence_passages", [])
            if isinstance(raw_passages, list) and raw_passages:
                for passage in raw_passages:
                    if not isinstance(passage, dict):
                        continue
                    url = canonicalize_source_url(passage.get("url"))
                    payload = {
                        "url": url,
                        "snippet_hash": str(passage.get("snippet_hash") or "").strip(),
                        "quote": str(passage.get("quote") or "").strip(),
                        "heading_path": list(passage.get("heading_path") or []),
                    }
                    if url:
                        evidence_passages.append(payload)
            else:
                for passage_id in result.get("evidence_passage_ids", []) or []:
                    passage = passages_by_id.get(str(passage_id))
                    if passage:
                        evidence_passages.append(passage)

            if not evidence_urls and evidence_passages:
                evidence_urls = [
                    url
                    for url in dict.fromkeys(
                        passage.get("url")
                        for passage in evidence_passages
                        if isinstance(passage.get("url"), str) and passage.get("url")
                    )
                ]

            claims.append(
                {
                    "claim": claim_text,
                    "status": status,
                    "evidence_urls": evidence_urls,
                    "evidence_passages": evidence_passages,
                    "score": item.get("score", 0.0),
                    "notes": str(item.get("notes") or "").strip(),
                }
            )
    return claims


def _normalize_obligations(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    obligations = artifact_store.get("coverage_obligations", []) if isinstance(artifact_store, dict) else []
    evaluations = (
        artifact_store.get("coverage_evaluation_results", []) if isinstance(artifact_store, dict) else []
    )
    evaluation_items = evaluations if isinstance(evaluations, list) else []
    evaluation_by_obligation = {
        str(item.get("obligation_id")): item
        for item in evaluation_items
        if isinstance(item, dict) and str(item.get("obligation_id") or "").strip()
    }
    items: list[dict[str, Any]] = []
    for obligation in obligations if isinstance(obligations, list) else []:
        if not isinstance(obligation, dict):
            continue
        obligation_id = str(obligation.get("id") or "").strip()
        evaluation = evaluation_by_obligation.get(obligation_id, {})
        items.append(
            {
                "id": obligation_id,
                "branch_id": obligation.get("branch_id"),
                "task_id": obligation.get("task_id"),
                "source": str(obligation.get("source") or "").strip(),
                "target": str(obligation.get("target") or "").strip(),
                "completion_criteria": list(obligation.get("completion_criteria") or []),
                "status": str(evaluation.get("status") or "pending").strip(),
                "summary": str(evaluation.get("summary") or "").strip(),
            }
        )
    return items


def _normalize_consistency_results(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    results = artifact_store.get("consistency_results", []) if isinstance(artifact_store, dict) else []
    items: list[dict[str, Any]] = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "id": item.get("id"),
                "branch_id": item.get("branch_id"),
                "task_id": item.get("task_id"),
                "claim_ids": list(item.get("claim_ids") or []),
                "related_branch_ids": list(item.get("related_branch_ids") or []),
                "status": str(item.get("status") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
            }
        )
    return items


def _normalize_revision_issues(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    issues = artifact_store.get("revision_issues", []) if isinstance(artifact_store, dict) else []
    items: list[dict[str, Any]] = []
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict):
            continue
        items.append(
            {
                "id": issue.get("id"),
                "branch_id": issue.get("branch_id"),
                "task_id": issue.get("task_id"),
                "issue_type": str(issue.get("issue_type") or "").strip(),
                "summary": str(issue.get("summary") or "").strip(),
                "status": str(issue.get("status") or "").strip(),
                "severity": str(issue.get("severity") or "").strip(),
                "blocking": bool(issue.get("blocking")),
                "recommended_action": str(issue.get("recommended_action") or "").strip(),
                "claim_ids": list(issue.get("claim_ids") or []),
                "obligation_ids": list(issue.get("obligation_ids") or []),
                "consistency_result_ids": list(issue.get("consistency_result_ids") or []),
            }
        )
    return items


def _normalize_revision_briefs(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    briefs = artifact_store.get("revision_briefs", []) if isinstance(artifact_store, dict) else []
    items: list[dict[str, Any]] = []
    for brief in briefs if isinstance(briefs, list) else []:
        if not isinstance(brief, dict):
            continue
        items.append(
            {
                "id": brief.get("id"),
                "revision_kind": str(brief.get("revision_kind") or "").strip(),
                "target_branch_id": brief.get("target_branch_id"),
                "target_task_id": brief.get("target_task_id"),
                "source_branch_id": brief.get("source_branch_id"),
                "source_task_id": brief.get("source_task_id"),
                "issue_ids": list(brief.get("issue_ids") or []),
                "summary": str(brief.get("summary") or "").strip(),
            }
        )
    return items


def _merge_quality_summary(
    quality_summary: dict[str, Any] | None,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = dict(quality_summary or {})
    if claims:
        verified = sum(1 for claim in claims if claim.get("status") == "verified")
        unsupported = sum(1 for claim in claims if claim.get("status") == "unsupported")
        contradicted = sum(1 for claim in claims if claim.get("status") == "contradicted")
        summary.setdefault("claim_verifier_total", len(claims))
        summary.setdefault("claim_verifier_verified", verified)
        summary.setdefault("claim_verifier_unsupported", unsupported)
        summary.setdefault("claim_verifier_contradicted", contradicted)
    return summary


def build_public_deep_research_artifacts(
    *,
    task_queue: dict[str, Any] | None,
    artifact_store: dict[str, Any] | None,
    research_topology: dict[str, Any] | None = None,
    quality_summary: dict[str, Any] | None = None,
    runtime_state: dict[str, Any] | None = None,
    mode: str = "multi_agent",
    engine: str = "multi_agent",
) -> dict[str, Any]:
    queue_snapshot = task_queue if isinstance(task_queue, dict) else {}
    store_snapshot = artifact_store if isinstance(artifact_store, dict) else {}
    public_passages = _normalize_passages(store_snapshot)
    passages_by_id = {
        str(item.get("id")): item
        for item in public_passages
        if isinstance(item.get("id"), str) and item.get("id")
    }
    claims = _normalize_claims(store_snapshot, passages_by_id)
    obligations = _normalize_obligations(store_snapshot)
    consistency_results = _normalize_consistency_results(store_snapshot)
    revision_issues = _normalize_revision_issues(store_snapshot)
    revision_briefs = _normalize_revision_briefs(store_snapshot)
    merged_quality = _merge_quality_summary(quality_summary, claims)
    query_coverage_score = merged_quality.get("query_coverage_score")
    final_report = store_snapshot.get("final_report") if isinstance(store_snapshot, dict) else {}
    if not isinstance(final_report, dict):
        final_report = {}
    freshness_summary = merged_quality.get("freshness_summary")
    if not isinstance(freshness_summary, dict):
        freshness_summary = {}

    return {
        "mode": mode,
        "engine": engine,
        "queries": _build_queries(queue_snapshot),
        "research_topology": research_topology if isinstance(research_topology, dict) else {},
        "quality_summary": merged_quality,
        "query_coverage": (
            {"score": float(query_coverage_score)}
            if isinstance(query_coverage_score, (int, float))
            else {}
        ),
        "freshness_summary": freshness_summary,
        "fetched_pages": _normalize_fetched_pages(store_snapshot),
        "passages": public_passages,
        "sources": _normalize_sources(store_snapshot),
        "claims": claims,
        "coverage_obligations": obligations,
        "consistency_results": consistency_results,
        "revision_issues": revision_issues,
        "revision_briefs": revision_briefs,
        "research_brief": (
            dict(store_snapshot.get("research_brief"))
            if isinstance(store_snapshot.get("research_brief"), dict)
            else {}
        ),
        "task_ledger": (
            dict(store_snapshot.get("task_ledger"))
            if isinstance(store_snapshot.get("task_ledger"), dict)
            else {}
        ),
        "progress_ledger": (
            dict(store_snapshot.get("progress_ledger"))
            if isinstance(store_snapshot.get("progress_ledger"), dict)
            else {}
        ),
        "coverage_matrix": (
            dict(store_snapshot.get("coverage_matrix"))
            if isinstance(store_snapshot.get("coverage_matrix"), dict)
            else {}
        ),
        "contradiction_registry": (
            dict(store_snapshot.get("contradiction_registry"))
            if isinstance(store_snapshot.get("contradiction_registry"), dict)
            else {}
        ),
        "missing_evidence_list": (
            dict(store_snapshot.get("missing_evidence_list"))
            if isinstance(store_snapshot.get("missing_evidence_list"), dict)
            else {}
        ),
        "outline": (
            dict(store_snapshot.get("outline"))
            if isinstance(store_snapshot.get("outline"), dict)
            else {}
        ),
        "coordination_requests": list(store_snapshot.get("coordination_requests") or []),
        "final_report": str(final_report.get("report_markdown") or ""),
        "executive_summary": str(final_report.get("executive_summary") or ""),
        "runtime_state": runtime_state if isinstance(runtime_state, dict) else {},
    }


def build_public_deep_research_artifacts_from_state(state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}

    deep_runtime = read_deep_runtime_snapshot(state, default_engine="")
    task_queue = deep_runtime.get("task_queue")
    artifact_store = deep_runtime.get("artifact_store")
    has_runtime_snapshot = (
        isinstance(task_queue, dict)
        and isinstance(artifact_store, dict)
        and (bool(task_queue) or bool(artifact_store))
    )
    if has_runtime_snapshot:
        mode = resolve_deep_runtime_mode(state, default_mode="multi_agent")
        return build_public_deep_research_artifacts(
            task_queue=task_queue,
            artifact_store=artifact_store,
            research_topology=state.get("research_topology"),
            quality_summary=state.get("quality_summary"),
            runtime_state=deep_runtime.get("runtime_state"),
            mode=mode,
            engine=str(deep_runtime.get("engine") or mode or "multi_agent"),
        )

    artifacts = state.get("deep_research_artifacts")
    if isinstance(artifacts, dict) and any(
        key in artifacts
        for key in (
            "sources",
            "claims",
            "fetched_pages",
            "queries",
            "quality_summary",
            "final_report",
            "executive_summary",
        )
    ):
        return dict(artifacts)
    return {}


__all__ = [
    "build_public_deep_research_artifacts",
    "build_public_deep_research_artifacts_from_state",
]
