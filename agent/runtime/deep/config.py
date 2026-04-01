"""
Validation and normalization for the supported Deep Research runtime inputs.
"""

from __future__ import annotations

from typing import Any

from common.config import settings

SUPPORTED_DEEPSEARCH_ENGINE = "multi_agent"
REMOVAL_DATE = "2026-04-01"


def _configurable(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    payload = config.get("configurable")
    return payload if isinstance(payload, dict) else {}


def normalize_deepsearch_engine(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text == SUPPORTED_DEEPSEARCH_ENGINE:
        return SUPPORTED_DEEPSEARCH_ENGINE
    raise ValueError(
        "Deep Research legacy engine selection was removed on "
        f"{REMOVAL_DATE}. Remove `deepsearchEngine={text}` and use the built-in "
        "`multi_agent` runtime."
    )


def ensure_supported_runtime_inputs(config: dict[str, Any] | None) -> None:
    cfg = _configurable(config)

    normalize_deepsearch_engine(cfg.get("deepsearch_engine"))

    if "deepsearch_mode" in cfg:
        raise ValueError(
            "Deep Research mode selection (`deepsearch_mode`) was removed on "
            f"{REMOVAL_DATE}. Remove tree/linear/auto overrides and use the "
            "`multi_agent` runtime defaults."
        )

    if "tree_parallel_branches" in cfg:
        raise ValueError(
            "Deep Research config `tree_parallel_branches` was removed on "
            f"{REMOVAL_DATE}. Rename it to `deepsearch_parallel_workers`."
        )

    if "deepsearch_tree_max_searches" in cfg:
        raise ValueError(
            "Deep Research config `deepsearch_tree_max_searches` was removed on "
            f"{REMOVAL_DATE}. Rename it to `deepsearch_max_searches`."
        )


def resolve_parallel_workers(config: dict[str, Any]) -> int:
    cfg = _configurable(config)
    value = cfg.get("deepsearch_parallel_workers")
    if value is None:
        return int(getattr(settings, "deepsearch_parallel_workers", 3))
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(getattr(settings, "deepsearch_parallel_workers", 3))


def resolve_max_searches(config: dict[str, Any]) -> int:
    cfg = _configurable(config)
    value = cfg.get("deepsearch_max_searches")
    if value is None:
        return int(getattr(settings, "deepsearch_max_searches", 30) or 30)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(getattr(settings, "deepsearch_max_searches", 30) or 30)


def supported_engine_for_mode(use_deep: bool) -> str | None:
    return SUPPORTED_DEEPSEARCH_ENGINE if use_deep else None


__all__ = [
    "SUPPORTED_DEEPSEARCH_ENGINE",
    "ensure_supported_runtime_inputs",
    "normalize_deepsearch_engine",
    "resolve_max_searches",
    "resolve_parallel_workers",
    "supported_engine_for_mode",
]
