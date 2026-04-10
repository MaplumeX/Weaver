"""Artifact-store helpers for the multi-agent Deep Research runtime."""

from __future__ import annotations

import copy
from typing import Any


def _normalize_source_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(item.get("title") or item.get("url") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "provider": str(item.get("provider") or "").strip(),
        "published_date": item.get("published_date"),
    }


def _group_artifacts_by_task(items: Any) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("task_id") or item.get("id") or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(dict(item))
    return grouped


class LightweightArtifactStore:
    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        self._scope = dict(snapshot.get("scope") or {})
        self._outline = dict(snapshot.get("outline") or {})
        self._plan = dict(snapshot.get("plan") or {})
        self._evidence_bundles = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("evidence_bundles", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        section_draft_items = snapshot.get("section_drafts")
        if not isinstance(section_draft_items, list):
            section_draft_items = []
        self._section_drafts = {
            str(item.get("section_id") or item.get("task_id") or item.get("id")): dict(item)
            for item in section_draft_items or []
            if isinstance(item, dict) and (item.get("section_id") or item.get("task_id") or item.get("id"))
        }
        section_review_items = snapshot.get("section_reviews")
        if not isinstance(section_review_items, list):
            section_review_items = []
        self._section_reviews = {
            str(item.get("section_id") or item.get("task_id") or item.get("id")): dict(item)
            for item in section_review_items or []
            if isinstance(item, dict) and (item.get("section_id") or item.get("task_id") or item.get("id"))
        }
        self._section_certifications = {
            str(item.get("section_id") or item.get("id")): dict(item)
            for item in snapshot.get("section_certifications", []) or []
            if isinstance(item, dict) and (item.get("section_id") or item.get("id"))
        }
        self._branch_query_rounds = {
            str(item.get("task_id") or item.get("id")): [dict(entry) for entry in task_items if isinstance(entry, dict)]
            for item, task_items in (
                (
                    {"task_id": task_id},
                    round_items,
                )
                for task_id, round_items in _group_artifacts_by_task(snapshot.get("branch_query_rounds", [])).items()
            )
        }
        self._branch_coverages = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("branch_coverages", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        self._branch_qualities = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("branch_qualities", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        self._branch_contradictions = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("branch_contradictions", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        self._branch_groundings = {
            str(item.get("task_id") or item.get("id")): dict(item)
            for item in snapshot.get("branch_groundings", []) or []
            if isinstance(item, dict) and (item.get("task_id") or item.get("id"))
        }
        self._branch_decisions = {
            str(item.get("task_id") or item.get("id")): [dict(entry) for entry in task_items if isinstance(entry, dict)]
            for item, task_items in (
                (
                    {"task_id": task_id},
                    decision_items,
                )
                for task_id, decision_items in _group_artifacts_by_task(snapshot.get("branch_decisions", [])).items()
            )
        }
        self._final_report = dict(snapshot.get("final_report") or {})

    def scope(self) -> dict[str, Any]:
        return copy.deepcopy(self._scope)

    def set_scope(self, scope: dict[str, Any]) -> None:
        self._scope = copy.deepcopy(scope)

    def outline(self) -> dict[str, Any]:
        return copy.deepcopy(self._outline)

    def set_outline(self, outline: dict[str, Any]) -> None:
        self._outline = copy.deepcopy(outline)

    def plan(self) -> dict[str, Any]:
        return copy.deepcopy(self._plan)

    def set_plan(self, plan: dict[str, Any]) -> None:
        self._plan = copy.deepcopy(plan)

    def evidence_bundles(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(self._evidence_bundles.values(), key=lambda value: str(value.get("task_id") or ""))
        ]

    def set_evidence_bundle(self, bundle: dict[str, Any]) -> None:
        key = str(bundle.get("task_id") or bundle.get("id") or "").strip()
        if key:
            self._evidence_bundles[key] = copy.deepcopy(bundle)

    def evidence_bundle(self, task_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._evidence_bundles.get(task_id, {}))

    def section_drafts(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(
                self._section_drafts.values(),
                key=lambda value: (
                    int(value.get("section_order", 0) or 0),
                    str(value.get("section_id") or value.get("task_id") or ""),
                ),
            )
        ]

    def set_section_draft(self, draft: dict[str, Any]) -> None:
        key = str(draft.get("section_id") or draft.get("task_id") or draft.get("id") or "").strip()
        if key:
            self._section_drafts[key] = copy.deepcopy(draft)

    def section_draft(self, section_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._section_drafts.get(section_id, {}))

    def section_reviews(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(
                self._section_reviews.values(),
                key=lambda value: (
                    int(value.get("section_order", 0) or 0),
                    str(value.get("section_id") or value.get("task_id") or ""),
                ),
            )
        ]

    def set_section_review(self, review: dict[str, Any]) -> None:
        key = str(review.get("section_id") or review.get("task_id") or review.get("id") or "").strip()
        if key:
            self._section_reviews[key] = copy.deepcopy(review)

    def section_review(self, section_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._section_reviews.get(section_id, {}))

    def clear_section_review(self, section_id: str) -> None:
        key = str(section_id or "").strip()
        if key:
            self._section_reviews.pop(key, None)

    def section_certifications(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in sorted(
                self._section_certifications.values(),
                key=lambda value: (
                    int(value.get("section_order", 0) or 0),
                    str(value.get("section_id") or ""),
                ),
            )
        ]

    def set_section_certification(self, certification: dict[str, Any]) -> None:
        key = str(certification.get("section_id") or certification.get("id") or "").strip()
        if key:
            self._section_certifications[key] = copy.deepcopy(certification)

    def section_certification(self, section_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._section_certifications.get(section_id, {}))

    def branch_query_rounds(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for rounds in self._branch_query_rounds.values():
            items.extend(copy.deepcopy(rounds))
        return sorted(items, key=lambda value: (str(value.get("task_id") or ""), int(value.get("round_index", 0) or 0)))

    def set_branch_query_rounds(self, task_id: str, rounds: list[dict[str, Any]]) -> None:
        key = str(task_id or "").strip()
        if key:
            self._branch_query_rounds[key] = [copy.deepcopy(item) for item in rounds if isinstance(item, dict)]

    def branch_coverage(self, task_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._branch_coverages.get(str(task_id or "").strip(), {}))

    def set_branch_coverage(self, coverage: dict[str, Any]) -> None:
        key = str(coverage.get("task_id") or coverage.get("id") or "").strip()
        if key:
            self._branch_coverages[key] = copy.deepcopy(coverage)

    def branch_qualities(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._branch_qualities.values()]

    def branch_quality(self, task_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._branch_qualities.get(str(task_id or "").strip(), {}))

    def set_branch_quality(self, quality: dict[str, Any]) -> None:
        key = str(quality.get("task_id") or quality.get("id") or "").strip()
        if key:
            self._branch_qualities[key] = copy.deepcopy(quality)

    def branch_contradiction(self, task_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._branch_contradictions.get(str(task_id or "").strip(), {}))

    def set_branch_contradiction(self, contradiction: dict[str, Any]) -> None:
        key = str(contradiction.get("task_id") or contradiction.get("id") or "").strip()
        if key:
            self._branch_contradictions[key] = copy.deepcopy(contradiction)

    def branch_grounding(self, task_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._branch_groundings.get(str(task_id or "").strip(), {}))

    def set_branch_grounding(self, grounding: dict[str, Any]) -> None:
        key = str(grounding.get("task_id") or grounding.get("id") or "").strip()
        if key:
            self._branch_groundings[key] = copy.deepcopy(grounding)

    def branch_decisions(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for decisions in self._branch_decisions.values():
            items.extend(copy.deepcopy(decisions))
        return sorted(items, key=lambda value: (str(value.get("task_id") or ""), int(value.get("round_index", 0) or 0)))

    def set_branch_decisions(self, task_id: str, decisions: list[dict[str, Any]]) -> None:
        key = str(task_id or "").strip()
        if key:
            self._branch_decisions[key] = [copy.deepcopy(item) for item in decisions if isinstance(item, dict)]

    def final_report(self) -> dict[str, Any]:
        return copy.deepcopy(self._final_report)

    def set_final_report(self, report: dict[str, Any]) -> None:
        self._final_report = copy.deepcopy(report)

    def certified_section_drafts(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.section_drafts()
            if bool(item.get("certified"))
        ]

    def reportable_section_drafts(self) -> list[dict[str, Any]]:
        reportable: list[dict[str, Any]] = []
        for item in self.section_drafts():
            summary = str(item.get("summary") or "").strip()
            findings = [
                str(value).strip()
                for value in item.get("key_findings", []) or []
                if str(value).strip()
            ]
            if summary or findings:
                reportable.append(item)
        return reportable

    def all_sources(self) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        seen: set[str] = set()
        for bundle in self.evidence_bundles():
            for source in bundle.get("sources", []) or []:
                if not isinstance(source, dict):
                    continue
                normalized = _normalize_source_item(source)
                url = normalized["url"]
                if not url or url in seen:
                    continue
                seen.add(url)
                sources.append(normalized)
        return sources

    def snapshot(self) -> dict[str, Any]:
        return {
            "scope": copy.deepcopy(self._scope),
            "outline": copy.deepcopy(self._outline),
            "plan": copy.deepcopy(self._plan),
            "evidence_bundles": self.evidence_bundles(),
            "section_drafts": self.section_drafts(),
            "section_reviews": self.section_reviews(),
            "section_certifications": self.section_certifications(),
            "branch_query_rounds": self.branch_query_rounds(),
            "branch_coverages": [copy.deepcopy(item) for item in self._branch_coverages.values()],
            "branch_qualities": [copy.deepcopy(item) for item in self._branch_qualities.values()],
            "branch_contradictions": [copy.deepcopy(item) for item in self._branch_contradictions.values()],
            "branch_groundings": [copy.deepcopy(item) for item in self._branch_groundings.values()],
            "branch_decisions": self.branch_decisions(),
            "final_report": copy.deepcopy(self._final_report),
        }


__all__ = ["LightweightArtifactStore"]
