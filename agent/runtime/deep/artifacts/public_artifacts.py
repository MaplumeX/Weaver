"""
Public Deep Research artifact adapters derived from the multi-agent runtime.
"""

from __future__ import annotations

from typing import Any

from agent.runtime.deep.state import read_deep_runtime_snapshot, resolve_deep_runtime_mode
from agent.research.source_url_utils import canonicalize_source_url, compact_unique_sources


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


def _sorted_artifact_dicts(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return sorted(
        (item for item in items if isinstance(item, dict)),
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )


def _latest_branch_validation_summaries_snapshot(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = _sorted_artifact_dicts(artifact_store.get("branch_validation_summaries", []))
    briefs = _sorted_artifact_dicts(artifact_store.get("branch_briefs", []))
    summary_by_id = {
        str(item.get("id") or "").strip(): item
        for item in summaries
        if str(item.get("id") or "").strip()
    }
    brief_by_branch = {
        str(item.get("id") or "").strip(): item
        for item in briefs
        if str(item.get("id") or "").strip()
    }
    by_branch: dict[str, dict[str, Any]] = {}

    for brief in briefs:
        branch_id = str(brief.get("id") or "").strip()
        summary = summary_by_id.get(str(brief.get("latest_verification_id") or "").strip())
        if branch_id and isinstance(summary, dict) and str(summary.get("branch_id") or "").strip() == branch_id:
            by_branch[branch_id] = summary

    for summary in summaries:
        branch_id = str(summary.get("branch_id") or "").strip()
        if not branch_id or branch_id in by_branch:
            continue
        brief = brief_by_branch.get(branch_id, {})
        latest_task_id = str(brief.get("latest_task_id") or "").strip()
        summary_task_id = str(summary.get("task_id") or "").strip()
        if latest_task_id and summary_task_id and latest_task_id != summary_task_id:
            continue
        by_branch[branch_id] = summary

    if by_branch:
        return list(by_branch.values())

    fallback: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        branch_id = str(summary.get("branch_id") or summary.get("task_id") or "").strip()
        if branch_id:
            fallback[branch_id] = summary
    return list(fallback.values())


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
            "locator": dict(item.get("locator") or {}),
            "source_published_date": item.get("source_published_date"),
            "passage_kind": str(item.get("passage_kind") or "quote").strip(),
            "admissible": bool(item.get("admissible", True)),
            "authoritative": bool(item.get("admissible", True)),
        }
        passages.append(passage)
    return passages


def _normalize_answer_units(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    raw_answer_units = artifact_store.get("answer_units", []) if isinstance(artifact_store, dict) else []
    raw_claim_units = artifact_store.get("claim_units", []) if isinstance(artifact_store, dict) else []
    units = raw_answer_units if isinstance(raw_answer_units, list) and raw_answer_units else raw_claim_units
    items: list[dict[str, Any]] = []
    for unit in units if isinstance(units, list) else []:
        if not isinstance(unit, dict):
            continue
        text = str(unit.get("text") or unit.get("claim") or "").strip()
        unit_id = str(unit.get("id") or "").strip()
        if not unit_id or not text:
            continue
        items.append(
            {
                "id": unit_id,
                "task_id": unit.get("task_id"),
                "branch_id": unit.get("branch_id"),
                "text": text,
                "unit_type": str(unit.get("unit_type") or "claim").strip(),
                "required": bool(unit.get("required", True)),
                "obligation_ids": list(unit.get("obligation_ids") or []),
                "supporting_passage_ids": list(
                    unit.get("supporting_passage_ids") or unit.get("evidence_passage_ids") or []
                ),
                "dependent_answer_unit_ids": list(unit.get("dependent_answer_unit_ids") or []),
                "citation_urls": [
                    canonicalize_source_url(url)
                    for url in unit.get("citation_urls", []) or []
                    if canonicalize_source_url(url)
                ],
                "provenance": dict(unit.get("provenance") or unit.get("claim_provenance") or {}),
            }
        )
    return items


def _normalize_branch_validation_summaries(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for summary in _latest_branch_validation_summaries_snapshot(artifact_store):
        items.append(
            {
                "id": summary.get("id"),
                "task_id": summary.get("task_id"),
                "branch_id": summary.get("branch_id"),
                "synthesis_id": summary.get("synthesis_id"),
                "ready_for_report": bool(summary.get("ready_for_report")),
                "blocking": bool(summary.get("blocking")),
                "summary": str(summary.get("summary") or "").strip(),
                "answer_unit_ids": list(summary.get("answer_unit_ids") or []),
                "supported_answer_unit_ids": list(summary.get("supported_answer_unit_ids") or []),
                "partially_supported_answer_unit_ids": list(
                    summary.get("partially_supported_answer_unit_ids") or []
                ),
                "unsupported_answer_unit_ids": list(summary.get("unsupported_answer_unit_ids") or []),
                "contradicted_answer_unit_ids": list(summary.get("contradicted_answer_unit_ids") or []),
                "obligation_ids": list(summary.get("obligation_ids") or []),
                "satisfied_obligation_ids": list(summary.get("satisfied_obligation_ids") or []),
                "partially_satisfied_obligation_ids": list(
                    summary.get("partially_satisfied_obligation_ids") or []
                ),
                "unsatisfied_obligation_ids": list(summary.get("unsatisfied_obligation_ids") or []),
                "issue_ids": list(summary.get("issue_ids") or []),
                "blocking_issue_ids": list(summary.get("blocking_issue_ids") or []),
                "consistency_result_ids": list(summary.get("consistency_result_ids") or []),
                "advisory_notes": list(summary.get("advisory_notes") or []),
            }
        )
    return items


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
    answer_units = artifact_store.get("answer_units", []) if isinstance(artifact_store, dict) else []
    claim_units = artifact_store.get("claim_units", []) if isinstance(artifact_store, dict) else []
    grounding_results = (
        artifact_store.get("claim_grounding_results", []) if isinstance(artifact_store, dict) else []
    )
    revision_issues = artifact_store.get("revision_issues", []) if isinstance(artifact_store, dict) else []
    structured_units = answer_units if isinstance(answer_units, list) and answer_units else claim_units
    if isinstance(structured_units, list) and structured_units:
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
        for unit in structured_units:
            if not isinstance(unit, dict):
                continue
            claim_id = str(unit.get("id") or "").strip()
            claim_text = str(unit.get("text") or unit.get("claim") or "").strip()
            if not claim_id or not claim_text:
                continue
            grounding = grounding_by_claim.get(claim_id, {})
            grounding_status = str(grounding.get("status") or "").strip().lower()
            status = (
                "verified"
                if grounding_status == "grounded"
                else (
                    "contradicted"
                    if grounding_status == "contradicted"
                    else ("partial" if grounding_status == "unresolved" else grounding_status or "unsupported")
                )
            )
            evidence_passage_ids = list(
                grounding.get("evidence_passage_ids")
                or unit.get("supporting_passage_ids")
                or unit.get("evidence_passage_ids")
                or []
            )
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
                    "unit_type": str(unit.get("unit_type") or "claim").strip(),
                    "branch_id": unit.get("branch_id"),
                    "task_id": unit.get("task_id"),
                    "required": bool(unit.get("required", True)),
                    "obligation_ids": list(unit.get("obligation_ids") or []),
                    "issue_ids": list(dict.fromkeys(issue_ids_by_claim.get(claim_id, []))),
                    "evidence_urls": evidence_urls,
                    "evidence_passages": evidence_passages,
                    "score": grounding.get("metadata", {}).get("score", 0.0)
                    if isinstance(grounding.get("metadata"), dict)
                    else 0.0,
                    "notes": str(grounding.get("summary") or "").strip(),
                    "provenance": dict(unit.get("provenance") or unit.get("claim_provenance") or {}),
                    "authoritative": True,
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


def _normalize_knowledge_gaps(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = artifact_store.get("knowledge_gaps", []) if isinstance(artifact_store, dict) else []
    items: list[dict[str, Any]] = []
    for gap in gaps if isinstance(gaps, list) else []:
        if not isinstance(gap, dict):
            continue
        items.append(
            {
                "id": gap.get("id"),
                "branch_id": gap.get("branch_id"),
                "aspect": str(gap.get("aspect") or "").strip(),
                "importance": str(gap.get("importance") or "").strip(),
                "reason": str(gap.get("reason") or "").strip(),
                "suggested_queries": list(gap.get("suggested_queries") or []),
                "advisory": bool(gap.get("advisory", True)),
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
                    "title": str(item.get("title") or "").strip(),
                    "excerpt": str(item.get("excerpt") or "").strip(),
                    "content": str(item.get("content") or ""),
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
                    "url": url,
                    "text": str(item.get("text") or ""),
                    "quote": str(item.get("quote") or "").strip(),
                    "source_title": str(item.get("source_title") or "").strip(),
                    "snippet_hash": str(item.get("snippet_hash") or "").strip(),
                    "heading_path": list(item.get("heading_path") or []),
                }
            )
    return passages


def _normalize_lightweight_branch_results(artifact_store: dict[str, Any]) -> list[dict[str, Any]]:
    items = artifact_store.get("branch_results", []) if isinstance(artifact_store, dict) else []
    return [
        {
            "id": item.get("id"),
            "task_id": item.get("task_id"),
            "branch_id": item.get("branch_id"),
            "title": str(item.get("title") or "").strip(),
            "objective": str(item.get("objective") or "").strip(),
            "summary": str(item.get("summary") or "").strip(),
            "key_findings": list(item.get("key_findings") or []),
            "source_urls": [
                canonicalize_source_url(url)
                for url in item.get("source_urls", []) or []
                if canonicalize_source_url(url)
            ],
            "validation_status": str(item.get("validation_status") or "pending").strip(),
        }
        for item in items if isinstance(item, dict)
    ]


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
    runtime_snapshot = runtime_state if isinstance(runtime_state, dict) else {}
    sources = _normalize_lightweight_sources(store_snapshot)
    fetched_pages = _normalize_lightweight_fetched_pages(store_snapshot)
    passages = _normalize_lightweight_passages(store_snapshot)
    branch_results = _normalize_lightweight_branch_results(store_snapshot)
    validation_summary = _normalize_lightweight_validation(store_snapshot)
    final_report = store_snapshot.get("final_report") if isinstance(store_snapshot, dict) else {}
    if not isinstance(final_report, dict):
        final_report = {}
    merged_quality = dict(quality_summary or {})
    if "query_coverage_score" not in merged_quality and queries:
        passed = int(validation_summary.get("passed_branch_count") or 0)
        merged_quality["query_coverage_score"] = round(passed / max(1, len(queries)), 3)

    return {
        "mode": mode,
        "engine": engine,
        "query": queries[0] if queries else "",
        "queries": queries,
        "scope": dict(store_snapshot.get("scope")) if isinstance(store_snapshot.get("scope"), dict) else {},
        "plan": dict(store_snapshot.get("plan")) if isinstance(store_snapshot.get("plan"), dict) else {},
        "tasks": _sorted_tasks(queue_snapshot),
        "research_topology": research_topology if isinstance(research_topology, dict) else {},
        "sources": sources,
        "branch_results": branch_results,
        "validation_summary": validation_summary,
        "quality_summary": merged_quality,
        "final_report": str(final_report.get("report_markdown") or ""),
        "executive_summary": str(final_report.get("executive_summary") or ""),
        "runtime_state": runtime_snapshot,
        "terminal_status": str(runtime_snapshot.get("terminal_status") or ""),
        "control_plane": {
            "active_agent": str(runtime_snapshot.get("active_agent") or ""),
        },
        "fetched_pages": fetched_pages,
        "passages": passages,
        "claims": [],
        "answer_units": [],
        "coverage_obligations": [],
        "consistency_results": [],
        "revision_issues": [],
        "revision_briefs": [],
        "knowledge_gaps": [],
        "query_coverage": (
            {"score": float(merged_quality.get("query_coverage_score"))}
            if isinstance(merged_quality.get("query_coverage_score"), (int, float))
            else {}
        ),
        "freshness_summary": dict(merged_quality.get("freshness_summary") or {}),
    }


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
    public_passages = _normalize_passages(store_snapshot)
    passages_by_id = {
        str(item.get("id")): item
        for item in public_passages
        if isinstance(item.get("id"), str) and item.get("id")
    }
    answer_units = _normalize_answer_units(store_snapshot)
    branch_validation_summaries = _normalize_branch_validation_summaries(store_snapshot)
    claims = _normalize_claims(store_snapshot, passages_by_id)
    obligations = _normalize_obligations(store_snapshot)
    consistency_results = _normalize_consistency_results(store_snapshot)
    revision_issues = _normalize_revision_issues(store_snapshot)
    revision_briefs = _normalize_revision_briefs(store_snapshot)
    knowledge_gaps = _normalize_knowledge_gaps(store_snapshot)
    merged_quality = _merge_quality_summary(quality_summary, claims)
    query_coverage_score = merged_quality.get("query_coverage_score")
    final_report = store_snapshot.get("final_report") if isinstance(store_snapshot, dict) else {}
    if not isinstance(final_report, dict):
        final_report = {}
    freshness_summary = merged_quality.get("freshness_summary")
    if not isinstance(freshness_summary, dict):
        freshness_summary = {}
    runtime_snapshot = runtime_state if isinstance(runtime_state, dict) else {}
    latest_handoff = runtime_snapshot.get("handoff_envelope")
    if not isinstance(latest_handoff, dict):
        latest_handoff = {}

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
        "answer_units": answer_units,
        "claims": claims,
        "coverage_obligations": obligations,
        "consistency_results": consistency_results,
        "branch_validation_summaries": branch_validation_summaries,
        "revision_issues": revision_issues,
        "revision_briefs": revision_briefs,
        "knowledge_gaps": knowledge_gaps,
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
        "runtime_state": runtime_snapshot,
        "control_plane": {
            "active_agent": str(runtime_snapshot.get("active_agent") or ""),
            "latest_handoff": dict(latest_handoff),
            "handoff_history": list(runtime_snapshot.get("handoff_history") or []),
        },
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
            "branch_results",
            "scope",
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
