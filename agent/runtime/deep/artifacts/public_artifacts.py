"""
Public Deep Research artifact adapters for the lightweight runtime contract.
"""

from __future__ import annotations

from typing import Any

from agent.runtime.deep.state import read_deep_runtime_snapshot, resolve_deep_runtime_mode
from agent.research.source_url_utils import canonicalize_source_url, compact_unique_sources

_PUBLIC_SIGNAL_KEYS = (
    "queries",
    "scope",
    "plan",
    "tasks",
    "research_topology",
    "sources",
    "branch_results",
    "validation_summary",
    "quality_summary",
    "final_report",
    "executive_summary",
    "runtime_state",
    "fetched_pages",
    "passages",
    "query_coverage",
    "freshness_summary",
)


def _has_lightweight_snapshot(artifact_store: dict[str, Any]) -> bool:
    if not isinstance(artifact_store, dict):
        return False
    return any(
        key in artifact_store
        for key in ("scope", "plan", "evidence_bundles", "branch_results", "validation_summaries")
    )


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


def _coerce_queries(value: Any) -> list[str]:
    if isinstance(value, list):
        queries: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            queries.append(text)
        return queries
    text = str(value or "").strip()
    return [text] if text else []


def _normalize_public_sources(items: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "title": item.get("title", ""),
                "url": item.get("raw_url") or item.get("rawUrl") or item.get("url") or "",
                "provider": item.get("provider", ""),
                "published_date": item.get("published_date") or item.get("publishedDate"),
            }
        )
    return compact_unique_sources(candidates, limit=max(5, len(candidates) or 5))


def _normalize_legacy_sources(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
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
            }
        )

    final_report = artifact_store.get("final_report", {}) if isinstance(artifact_store, dict) else {}
    citation_urls = final_report.get("citation_urls", []) if isinstance(final_report, dict) else []
    for url in citation_urls if isinstance(citation_urls, list) else []:
        candidates.append({"title": str(url or ""), "url": url})

    return compact_unique_sources(candidates, limit=max(5, len(candidates) or 5))


def _normalize_public_fetched_pages(items: Any) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = canonicalize_source_url(item.get("url") or item.get("raw_url") or item.get("rawUrl"))
        if not url:
            continue
        page = {
            "id": item.get("id"),
            "task_id": item.get("task_id"),
            "branch_id": item.get("branch_id"),
            "url": url,
            "raw_url": str(item.get("raw_url") or item.get("rawUrl") or item.get("url") or ""),
            "title": str(item.get("title") or "").strip(),
            "excerpt": str(item.get("excerpt") or "").strip(),
            "content": str(item.get("content") or ""),
            "text": item.get("text"),
            "method": item.get("method"),
            "published_date": item.get("published_date"),
            "retrieved_at": item.get("retrieved_at"),
            "markdown": item.get("markdown"),
            "http_status": item.get("http_status"),
            "error": item.get("error"),
            "attempts": item.get("attempts"),
            "source_candidate_id": item.get("source_candidate_id"),
        }
        pages.append(page)
    return pages


def _normalize_legacy_fetched_pages(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
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


def _normalize_public_passages(items: Any) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = canonicalize_source_url(item.get("url"))
        if not url:
            continue
        heading_path = item.get("heading_path")
        heading_items = heading_path if isinstance(heading_path, list) else []
        passages.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "branch_id": item.get("branch_id"),
                "document_id": item.get("document_id"),
                "url": url,
                "text": str(item.get("text") or ""),
                "quote": str(item.get("quote") or "").strip(),
                "source_title": str(item.get("source_title") or "").strip(),
                "snippet_hash": str(item.get("snippet_hash") or "").strip(),
                "heading": item.get("heading") or (heading_items[0] if heading_items else None),
                "heading_path": list(heading_items),
                "page_title": item.get("page_title"),
                "start_char": item.get("start_char"),
                "end_char": item.get("end_char"),
                "retrieved_at": item.get("retrieved_at"),
                "method": item.get("method"),
                "locator": dict(item.get("locator") or {}),
                "source_published_date": item.get("source_published_date"),
                "passage_kind": str(item.get("passage_kind") or "quote").strip(),
                "admissible": bool(item.get("admissible", True)),
                "authoritative": bool(item.get("authoritative", item.get("admissible", True))),
            }
        )
    return passages


def _normalize_legacy_passages(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    items = artifact_store.get("evidence_passages", []) if isinstance(artifact_store, dict) else []
    passages: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = canonicalize_source_url(item.get("url"))
        if not url:
            continue
        heading_path = item.get("heading_path")
        heading_items = heading_path if isinstance(heading_path, list) else []
        passages.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "branch_id": item.get("branch_id"),
                "document_id": item.get("document_id"),
                "url": url,
                "text": str(item.get("text") or ""),
                "quote": str(item.get("quote") or "").strip(),
                "source_title": str(item.get("source_title") or "").strip(),
                "snippet_hash": str(item.get("snippet_hash") or "").strip(),
                "heading": heading_items[0] if heading_items else None,
                "heading_path": list(heading_items),
                "locator": dict(item.get("locator") or {}),
                "source_published_date": item.get("source_published_date"),
                "passage_kind": str(item.get("passage_kind") or "quote").strip(),
                "admissible": bool(item.get("admissible", True)),
                "authoritative": bool(item.get("admissible", True)),
            }
        )
    return passages


def _normalize_public_branch_results(items: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "branch_id": item.get("branch_id"),
                "title": str(item.get("title") or "").strip(),
                "objective": str(item.get("objective") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "key_findings": list(item.get("key_findings") or []),
                "open_questions": list(item.get("open_questions") or []),
                "confidence_note": str(item.get("confidence_note") or "").strip(),
                "source_urls": [
                    canonicalize_source_url(url)
                    for url in item.get("source_urls", []) or []
                    if canonicalize_source_url(url)
                ],
                "validation_status": str(item.get("validation_status") or "pending").strip(),
            }
        )
    return results


def _normalize_validation_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    summary: dict[str, Any] = {}
    integer_keys = (
        "passed_branch_count",
        "retry_branch_count",
        "failed_branch_count",
        "advisory_gap_count",
    )
    for key in integer_keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            summary[key] = int(value)
        except (TypeError, ValueError):
            continue

    float_keys = ("coverage_score",)
    for key in float_keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            summary[key] = float(value)
        except (TypeError, ValueError):
            continue

    string_keys = ("status_reason", "notes")
    for key in string_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            summary[key] = value.strip()

    raw_summaries = payload.get("summaries")
    if isinstance(raw_summaries, list):
        summary["summaries"] = [
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "branch_id": item.get("branch_id"),
                "status": str(item.get("status") or "pending").strip(),
                "score": item.get("score", 0.0),
                "missing_aspects": list(item.get("missing_aspects") or []),
                "retry_queries": list(item.get("retry_queries") or []),
                "notes": str(item.get("notes") or "").strip(),
            }
            for item in raw_summaries
            if isinstance(item, dict)
        ]

    return summary


def _build_query_coverage(
    quality_summary: dict[str, Any],
    explicit_query_coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(explicit_query_coverage, dict) and explicit_query_coverage:
        return dict(explicit_query_coverage)
    score = quality_summary.get("query_coverage_score")
    if isinstance(score, (int, float)):
        return {"score": float(score)}
    nested = quality_summary.get("query_coverage")
    if isinstance(nested, dict):
        return dict(nested)
    return {}


def _normalize_control_plane(
    runtime_state: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    control_plane = dict(payload or {})
    latest_handoff = control_plane.get("latest_handoff")
    if not isinstance(latest_handoff, dict):
        runtime_handoff = runtime_state.get("handoff_envelope")
        latest_handoff = dict(runtime_handoff) if isinstance(runtime_handoff, dict) else {}

    handoff_history = control_plane.get("handoff_history")
    if not isinstance(handoff_history, list):
        raw_history = runtime_state.get("handoff_history")
        handoff_history = [item for item in raw_history if isinstance(item, dict)] if isinstance(raw_history, list) else []

    return {
        "active_agent": str(control_plane.get("active_agent") or runtime_state.get("active_agent") or ""),
        "latest_handoff": dict(latest_handoff),
        "handoff_history": list(handoff_history),
    }


def _build_public_payload(
    *,
    mode: str,
    engine: str,
    queries: list[str],
    scope: dict[str, Any],
    plan: dict[str, Any],
    tasks: list[dict[str, Any]],
    research_topology: dict[str, Any],
    sources: list[dict[str, Any]],
    branch_results: list[dict[str, Any]],
    validation_summary: dict[str, Any],
    quality_summary: dict[str, Any],
    final_report: str,
    executive_summary: str,
    runtime_state: dict[str, Any],
    fetched_pages: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    query_coverage: dict[str, Any] | None = None,
    freshness_summary: dict[str, Any] | None = None,
    control_plane: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_query_coverage = _build_query_coverage(quality_summary, query_coverage)
    resolved_freshness = (
        dict(freshness_summary)
        if isinstance(freshness_summary, dict)
        else dict(quality_summary.get("freshness_summary") or {})
    )
    return {
        "mode": mode,
        "engine": engine,
        "query": queries[0] if queries else "",
        "queries": queries,
        "scope": dict(scope),
        "plan": dict(plan),
        "tasks": list(tasks),
        "research_topology": dict(research_topology),
        "sources": list(sources),
        "branch_results": list(branch_results),
        "validation_summary": dict(validation_summary),
        "quality_summary": dict(quality_summary),
        "final_report": final_report,
        "executive_summary": executive_summary,
        "runtime_state": dict(runtime_state),
        "terminal_status": str(runtime_state.get("terminal_status") or ""),
        "control_plane": _normalize_control_plane(runtime_state, control_plane),
        "fetched_pages": list(fetched_pages),
        "passages": list(passages),
        "query_coverage": resolved_query_coverage,
        "freshness_summary": resolved_freshness,
    }


def _normalize_lightweight_sources(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    bundles = artifact_store.get("evidence_bundles", []) if isinstance(artifact_store, dict) else []
    for bundle in bundles if isinstance(bundles, list) else []:
        if not isinstance(bundle, dict):
            continue
        for source in bundle.get("sources", []) or []:
            if not isinstance(source, dict):
                continue
            candidates.append(
                {
                    "title": source.get("title", ""),
                    "url": source.get("url", ""),
                    "provider": source.get("provider", ""),
                    "published_date": source.get("published_date"),
                }
            )
    final_report = artifact_store.get("final_report", {}) if isinstance(artifact_store, dict) else {}
    citation_urls = final_report.get("citation_urls", []) if isinstance(final_report, dict) else []
    for url in citation_urls if isinstance(citation_urls, list) else []:
        candidates.append({"title": str(url or ""), "url": url})
    return compact_unique_sources(candidates, limit=max(5, len(candidates) or 5))


def _normalize_lightweight_fetched_pages(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    bundles = artifact_store.get("evidence_bundles", []) if isinstance(artifact_store, dict) else []
    for bundle in bundles if isinstance(bundles, list) else []:
        if not isinstance(bundle, dict):
            continue
        for item in bundle.get("documents", []) or []:
            if not isinstance(item, dict):
                continue
            url = canonicalize_source_url(item.get("url"))
            if not url:
                continue
            pages.append(
                {
                    "id": item.get("id"),
                    "task_id": bundle.get("task_id"),
                    "branch_id": bundle.get("branch_id"),
                    "url": url,
                    "raw_url": item.get("raw_url"),
                    "title": str(item.get("title") or "").strip(),
                    "excerpt": str(item.get("excerpt") or "").strip(),
                    "content": str(item.get("content") or ""),
                    "text": item.get("content"),
                    "method": item.get("method"),
                    "published_date": item.get("published_date"),
                    "retrieved_at": item.get("retrieved_at"),
                    "markdown": item.get("markdown"),
                    "http_status": item.get("http_status"),
                    "error": item.get("error"),
                    "attempts": item.get("attempts"),
                }
            )
    return pages


def _normalize_lightweight_passages(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    bundles = artifact_store.get("evidence_bundles", []) if isinstance(artifact_store, dict) else []
    for bundle in bundles if isinstance(bundles, list) else []:
        if not isinstance(bundle, dict):
            continue
        for item in bundle.get("passages", []) or []:
            if not isinstance(item, dict):
                continue
            url = canonicalize_source_url(item.get("url"))
            if not url:
                continue
            passages.append(
                {
                    "id": item.get("id"),
                    "task_id": bundle.get("task_id"),
                    "branch_id": bundle.get("branch_id"),
                    "document_id": item.get("document_id"),
                    "url": url,
                    "text": str(item.get("text") or ""),
                    "quote": str(item.get("quote") or "").strip(),
                    "source_title": str(item.get("source_title") or "").strip(),
                    "snippet_hash": str(item.get("snippet_hash") or "").strip(),
                    "heading": (list(item.get("heading_path") or []) or [None])[0],
                    "heading_path": list(item.get("heading_path") or []),
                    "page_title": item.get("page_title"),
                    "start_char": item.get("start_char"),
                    "end_char": item.get("end_char"),
                    "retrieved_at": item.get("retrieved_at"),
                    "method": item.get("method"),
                    "locator": dict(item.get("locator") or {}),
                    "source_published_date": item.get("source_published_date"),
                    "passage_kind": str(item.get("passage_kind") or "quote").strip(),
                    "admissible": bool(item.get("admissible", True)),
                    "authoritative": bool(item.get("authoritative", item.get("admissible", True))),
                }
            )
    return passages


def _normalize_lightweight_branch_results(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    items = artifact_store.get("branch_results", []) if isinstance(artifact_store, dict) else []
    return _normalize_public_branch_results(items)


def _normalize_lightweight_validation(artifact_store: dict[str, Any]) -> dict[str, Any]:
    items = artifact_store.get("validation_summaries", []) if isinstance(artifact_store, dict) else []
    status_counts = {"passed": 0, "retry": 0, "failed": 0}
    summaries: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status in status_counts:
            status_counts[status] += 1
        summaries.append(
            {
                "id": item.get("id"),
                "task_id": item.get("task_id"),
                "branch_id": item.get("branch_id"),
                "status": status or "pending",
                "score": item.get("score", 0.0),
                "missing_aspects": list(item.get("missing_aspects") or []),
                "retry_queries": list(item.get("retry_queries") or []),
                "notes": str(item.get("notes") or "").strip(),
            }
        )
    return {
        "passed_branch_count": status_counts["passed"],
        "retry_branch_count": status_counts["retry"],
        "failed_branch_count": status_counts["failed"],
        "summaries": summaries,
    }


def _build_lightweight_public_artifacts(
    *,
    queue_snapshot: dict[str, Any],
    store_snapshot: dict[str, Any],
    research_topology: dict[str, Any] | None,
    quality_summary: dict[str, Any] | None,
    runtime_state: dict[str, Any] | None,
    mode: str,
    engine: str,
) -> dict[str, Any]:
    queries = _build_queries(queue_snapshot)
    validation_summary = _normalize_lightweight_validation(store_snapshot)
    merged_quality = dict(quality_summary or {})
    if "query_coverage_score" not in merged_quality and queries:
        passed = int(validation_summary.get("passed_branch_count") or 0)
        merged_quality["query_coverage_score"] = round(passed / max(1, len(queries)), 3)

    final_report = store_snapshot.get("final_report")
    final_report_payload = final_report if isinstance(final_report, dict) else {}
    runtime_snapshot = runtime_state if isinstance(runtime_state, dict) else {}

    return _build_public_payload(
        mode=mode,
        engine=engine,
        queries=queries,
        scope=dict(store_snapshot.get("scope")) if isinstance(store_snapshot.get("scope"), dict) else {},
        plan=dict(store_snapshot.get("plan")) if isinstance(store_snapshot.get("plan"), dict) else {},
        tasks=_sorted_tasks(queue_snapshot),
        research_topology=research_topology if isinstance(research_topology, dict) else {},
        sources=_normalize_lightweight_sources(store_snapshot),
        branch_results=_normalize_lightweight_branch_results(store_snapshot),
        validation_summary=validation_summary,
        quality_summary=merged_quality,
        final_report=str(final_report_payload.get("report_markdown") or ""),
        executive_summary=str(final_report_payload.get("executive_summary") or ""),
        runtime_state=runtime_snapshot,
        fetched_pages=_normalize_lightweight_fetched_pages(store_snapshot),
        passages=_normalize_lightweight_passages(store_snapshot),
    )


def _build_legacy_public_artifacts(
    *,
    queue_snapshot: dict[str, Any],
    store_snapshot: dict[str, Any],
    research_topology: dict[str, Any] | None,
    quality_summary: dict[str, Any] | None,
    runtime_state: dict[str, Any] | None,
    mode: str,
    engine: str,
) -> dict[str, Any]:
    runtime_snapshot = runtime_state if isinstance(runtime_state, dict) else {}
    final_report = store_snapshot.get("final_report")
    final_report_payload = final_report if isinstance(final_report, dict) else {}
    validation_summary = _normalize_validation_summary(runtime_snapshot.get("last_verification_summary"))

    return _build_public_payload(
        mode=mode,
        engine=engine,
        queries=_build_queries(queue_snapshot),
        scope={},
        plan={},
        tasks=_sorted_tasks(queue_snapshot),
        research_topology=research_topology if isinstance(research_topology, dict) else {},
        sources=_normalize_legacy_sources(store_snapshot),
        branch_results=[],
        validation_summary=validation_summary,
        quality_summary=dict(quality_summary or {}),
        final_report=str(final_report_payload.get("report_markdown") or ""),
        executive_summary=str(final_report_payload.get("executive_summary") or ""),
        runtime_state=runtime_snapshot,
        fetched_pages=_normalize_legacy_fetched_pages(store_snapshot),
        passages=_normalize_legacy_passages(store_snapshot),
    )


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
    if _has_lightweight_snapshot(store_snapshot):
        return _build_lightweight_public_artifacts(
            queue_snapshot=queue_snapshot,
            store_snapshot=store_snapshot,
            research_topology=research_topology,
            quality_summary=quality_summary,
            runtime_state=runtime_state,
            mode=mode,
            engine=engine,
        )
    return _build_legacy_public_artifacts(
        queue_snapshot=queue_snapshot,
        store_snapshot=store_snapshot,
        research_topology=research_topology,
        quality_summary=quality_summary,
        runtime_state=runtime_state,
        mode=mode,
        engine=engine,
    )


def _filter_public_artifacts(
    artifacts: dict[str, Any],
    *,
    default_mode: str,
    default_engine: str,
) -> dict[str, Any]:
    quality_summary = dict(artifacts.get("quality_summary") or {}) if isinstance(artifacts.get("quality_summary"), dict) else {}
    runtime_state = dict(artifacts.get("runtime_state") or {}) if isinstance(artifacts.get("runtime_state"), dict) else {}
    queries = _coerce_queries(artifacts.get("queries"))
    if not queries:
        queries = _coerce_queries(artifacts.get("query"))

    final_report = str(artifacts.get("final_report") or "")
    executive_summary = str(artifacts.get("executive_summary") or "")

    payload = _build_public_payload(
        mode=str(artifacts.get("mode") or default_mode or "multi_agent"),
        engine=str(artifacts.get("engine") or artifacts.get("mode") or default_engine or default_mode or "multi_agent"),
        queries=queries,
        scope=dict(artifacts.get("scope")) if isinstance(artifacts.get("scope"), dict) else {},
        plan=dict(artifacts.get("plan")) if isinstance(artifacts.get("plan"), dict) else {},
        tasks=_sorted_tasks({"tasks": artifacts.get("tasks")}) if isinstance(artifacts.get("tasks"), list) else [],
        research_topology=dict(artifacts.get("research_topology")) if isinstance(artifacts.get("research_topology"), dict) else {},
        sources=_normalize_public_sources(artifacts.get("sources")),
        branch_results=_normalize_public_branch_results(artifacts.get("branch_results")),
        validation_summary=_normalize_validation_summary(artifacts.get("validation_summary")),
        quality_summary=quality_summary,
        final_report=final_report,
        executive_summary=executive_summary,
        runtime_state=runtime_state,
        fetched_pages=_normalize_public_fetched_pages(artifacts.get("fetched_pages")),
        passages=_normalize_public_passages(artifacts.get("passages")),
        query_coverage=dict(artifacts.get("query_coverage")) if isinstance(artifacts.get("query_coverage"), dict) else None,
        freshness_summary=(
            dict(artifacts.get("freshness_summary"))
            if isinstance(artifacts.get("freshness_summary"), dict)
            else None
        ),
        control_plane=dict(artifacts.get("control_plane")) if isinstance(artifacts.get("control_plane"), dict) else None,
    )

    if any(payload.get(key) for key in _PUBLIC_SIGNAL_KEYS):
        return payload
    return {}


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
    if isinstance(artifacts, dict) and artifacts:
        mode = resolve_deep_runtime_mode(state, default_mode="multi_agent")
        return _filter_public_artifacts(
            artifacts,
            default_mode=mode,
            default_engine=str(mode or "multi_agent"),
        )
    return {}


__all__ = [
    "build_public_deep_research_artifacts",
    "build_public_deep_research_artifacts_from_state",
]
