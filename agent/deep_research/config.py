"""
Validation and normalization for the supported Deep Research runtime inputs.
"""

from __future__ import annotations

from typing import Any

from agent.execution.config_utils import configurable_dict
from common.config import settings

SUPPORTED_DEEP_RESEARCH_RUNTIME = "multi_agent"
REMOVAL_DATE = "2026-04-01"
DEAD_KNOB_REMOVAL_DATE = "2026-04-11"

_configurable = configurable_dict


def ensure_supported_runtime_inputs(config: dict[str, Any] | None) -> None:
    cfg = _configurable(config)
    removed_runtime_key = str(cfg.get("deepsearch_engine") or "").strip()
    if removed_runtime_key:
        raise ValueError(
            "Deep Research runtime selection was removed on "
            f"{REMOVAL_DATE}. Remove `deepsearchEngine={removed_runtime_key}` and use the built-in "
            f"`{SUPPORTED_DEEP_RESEARCH_RUNTIME}` runtime."
        )

    runtime_key = str(cfg.get("deep_research_engine") or "").strip()
    if runtime_key:
        raise ValueError(
            "Deep Research runtime selection was removed on "
            f"{REMOVAL_DATE}. Remove `deep_research_engine={runtime_key}` and use the built-in "
            f"`{SUPPORTED_DEEP_RESEARCH_RUNTIME}` runtime."
        )

    if "deepsearch_mode" in cfg:
        raise ValueError(
            "Deep Research mode selection (`deepsearch_mode`) was removed on "
            f"{REMOVAL_DATE}. Remove tree/linear/auto overrides and use the "
            f"`{SUPPORTED_DEEP_RESEARCH_RUNTIME}` runtime defaults."
        )
    if "deep_research_mode" in cfg:
        raise ValueError(
            "Deep Research mode selection (`deep_research_mode`) was removed on "
            f"{REMOVAL_DATE}. Remove tree/linear/auto overrides and use the "
            f"`{SUPPORTED_DEEP_RESEARCH_RUNTIME}` runtime defaults."
        )

    if "tree_parallel_branches" in cfg:
        raise ValueError(
            "Deep Research config `tree_parallel_branches` was removed on "
            f"{REMOVAL_DATE}. Rename it to `deep_research_parallel_workers`."
        )

    if "deepsearch_tree_max_searches" in cfg:
        raise ValueError(
            "Deep Research config `deepsearch_tree_max_searches` was removed on "
            f"{REMOVAL_DATE}. Rename it to `deep_research_max_searches`."
        )

    if "deep_research_query_num" in cfg:
        raise ValueError(
            "Deep Research config `deep_research_query_num` was removed on "
            f"{DEAD_KNOB_REMOVAL_DATE}. Query planning is now derived from the "
            "branch planner and `deep_research_results_per_query`."
        )

    if "deep_research_clarify_round_limit" in cfg:
        raise ValueError(
            "Deep Research config `deep_research_clarify_round_limit` was removed on "
            f"{DEAD_KNOB_REMOVAL_DATE}. Clarify retries are now runtime-owned."
        )


def resolve_parallel_workers(config: dict[str, Any]) -> int:
    cfg = _configurable(config)
    value = cfg.get("deep_research_parallel_workers")
    if value is None:
        return int(getattr(settings, "deep_research_parallel_workers", 3))
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(getattr(settings, "deep_research_parallel_workers", 3))


def resolve_max_searches(config: dict[str, Any]) -> int:
    cfg = _configurable(config)
    value = cfg.get("deep_research_max_searches")
    if value is None:
        return int(getattr(settings, "deep_research_max_searches", 30) or 30)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(getattr(settings, "deep_research_max_searches", 30) or 30)


__all__ = [
    "SUPPORTED_DEEP_RESEARCH_RUNTIME",
    "ensure_supported_runtime_inputs",
    "resolve_max_searches",
    "resolve_parallel_workers",
]
