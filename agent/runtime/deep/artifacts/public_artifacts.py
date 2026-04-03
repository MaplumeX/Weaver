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
