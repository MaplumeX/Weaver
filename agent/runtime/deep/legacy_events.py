"""
Legacy deep-research diagnostics, event emission, and persistence helpers.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agent.contracts.events import get_emitter_sync
from agent.workflows.query_strategy import (
    analyze_query_coverage,
    is_time_sensitive_topic,
    summarize_freshness,
)
from agent.workflows.source_url_utils import compact_unique_sources
from common.config import settings

logger = logging.getLogger(__name__)


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.workflows.deepsearch_optimized")
    if compat is None:
        import agent.workflows.deepsearch_optimized as compat
    return compat


def _safe_filename(name: str) -> str:
    return re.sub(r'[\/\\:\*\?"<>\|]', "_", name)[:80]


def _build_quality_diagnostics(
    topic: str,
    queries: List[str],
    search_runs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    deps = _resolve_deps()
    query_coverage = getattr(deps, "analyze_query_coverage", analyze_query_coverage)(queries)
    freshness_summary = getattr(deps, "summarize_freshness", summarize_freshness)(search_runs)
    time_sensitive_query = getattr(deps, "is_time_sensitive_topic", is_time_sensitive_topic)(topic)
    cfg = getattr(deps, "settings", settings)
    min_known_results = max(
        1,
        int(getattr(cfg, "deepsearch_freshness_warning_min_known", 3) or 3),
    )
    min_fresh_ratio = max(
        0.0,
        min(
            1.0,
            float(getattr(cfg, "deepsearch_freshness_warning_min_ratio", 0.4) or 0.4),
        ),
    )

    freshness_warning = ""
    if (
        time_sensitive_query
        and freshness_summary.get("known_count", 0) >= min_known_results
        and freshness_summary.get("fresh_30_ratio", 0.0) < min_fresh_ratio
    ):
        freshness_warning = "low_freshness_for_time_sensitive_query"

    return {
        "query_coverage": query_coverage,
        "query_coverage_score": query_coverage.get("score", 0.0),
        "query_dimensions_covered": query_coverage.get("covered_dimensions", []),
        "query_dimensions_missing": query_coverage.get("missing_dimensions", []),
        "query_dimension_hits": query_coverage.get("dimension_hits", {}),
        "freshness_summary": freshness_summary,
        "time_sensitive_query": time_sensitive_query,
        "freshness_warning": freshness_warning,
    }


def _resolve_event_emitter(state: Dict[str, Any], config: Dict[str, Any]) -> Any:
    deps = _resolve_deps()
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    thread_id = ""
    if isinstance(cfg, dict):
        thread_id = str(cfg.get("thread_id") or "").strip()
    if not thread_id:
        thread_id = str(state.get("cancel_token_id") or "").strip()
    if not thread_id:
        return None

    try:
        emitter_factory = getattr(deps, "get_emitter_sync", get_emitter_sync)
        return emitter_factory(thread_id)
    except Exception:
        return None


def _emit_event(emitter: Any, event_type: str, data: Dict[str, Any]) -> None:
    deps = _resolve_deps()
    if emitter is None:
        return
    try:
        emitter.emit_sync(event_type, data or {})
    except Exception as exc:
        getattr(deps, "logger", logger).debug(
            "[deepsearch] failed to emit event '%s': %s",
            event_type,
            exc,
        )


def _compact_search_results(results: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    deps = _resolve_deps()
    compact = getattr(deps, "compact_unique_sources", compact_unique_sources)
    return compact(results, limit=limit)


def _provider_breakdown(results: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in results or []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "unknown").strip() or "unknown"
        counts[provider] = counts.get(provider, 0) + 1
    return counts


def _event_results_limit() -> int:
    deps = _resolve_deps()
    cfg = getattr(deps, "settings", settings)
    return max(1, min(20, int(getattr(cfg, "deepsearch_event_results_limit", 5) or 5)))


def _save_deepsearch_data(
    topic: str,
    have_query: List[str],
    summary_notes: List[str],
    search_runs: List[Dict[str, Any]],
    final_report: str,
    epoch: int,
) -> str:
    deps = _resolve_deps()
    cfg = getattr(deps, "settings", settings)
    log = getattr(deps, "logger", logger)
    if not getattr(cfg, "deepsearch_save_data", False):
        return ""

    try:
        save_dir = Path(getattr(cfg, "deepsearch_save_dir"))
        save_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{_safe_filename(topic)}_{ts}.json"
        path = save_dir / fname
        data = {
            "topic": topic,
            "queries": have_query,
            "summaries": summary_notes,
            "search_runs": search_runs,
            "final_report": final_report,
            "epoch": epoch,
            "mode": "deepsearch_optimized",
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("[deepsearch] saved run data -> %s", path)
        return str(path)
    except Exception as exc:
        log.warning("[deepsearch] failed to save data: %s", exc)
        return ""


__all__ = [
    "_build_quality_diagnostics",
    "_compact_search_results",
    "_emit_event",
    "_event_results_limit",
    "_provider_breakdown",
    "_resolve_event_emitter",
    "_safe_filename",
    "_save_deepsearch_data",
]
