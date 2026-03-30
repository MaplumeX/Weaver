"""
Shared helper functions for the legacy deep-research runtime.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
import sys
import time
from typing import Any, Dict, List, Optional

from agent.contracts.search_cache import get_search_cache
from agent.workflows.domain_router import ResearchDomain, build_provider_profile
from common.cancellation import check_cancellation as _check_cancel_token
from common.config import settings
from tools.search.multi_search import SearchStrategy, multi_search
from tools.search.search import tavily_search

logger = logging.getLogger(__name__)
_COMPAT_EXPORTS = (
    ResearchDomain,
    build_provider_profile,
    get_search_cache,
    multi_search,
    tavily_search,
)

_DEEPSEARCH_MODES = {"auto", "tree", "linear"}
_DEEPSEARCH_ENGINES = {"legacy", "multi_agent"}
_SIMPLE_FACT_PATTERNS = (
    r"\bwhat\s+is\b",
    r"\bwho\s+is\b",
    r"\bwhen\s+(?:is|was|did)\b",
    r"\bwhere\s+(?:is|was)\b",
    r"\bwhich\s+is\b",
    r"\bhow\s+many\b",
    r"\bcapital\s+of\b",
    r"\bpopulation\s+of\b",
    r"\breply\s+with\b",
    r"\bone\s+word\b",
    r"是什么",
    r"谁是",
    r"何时",
    r"哪里",
    r"在哪",
    r"多少",
    r"首都",
    r"人口",
    r"只回答",
    r"一个词",
)
_BROAD_RESEARCH_CUES = (
    "analysis",
    "analyze",
    "assess",
    "case study",
    "cases",
    "compare",
    "comparison",
    "deep research",
    "evaluate",
    "framework",
    "histor",
    "impact",
    "investigate",
    "latest",
    "market",
    "overview",
    "policy",
    "regulation",
    "report",
    "research",
    "survey",
    "timeline",
    "trend",
    "updates",
    "versus",
    "vs",
    "分析",
    "影响",
    "报告",
    "对比",
    "挑战",
    "政策",
    "框架",
    "比较",
    "法规",
    "深度",
    "研究",
    "综述",
    "调研",
    "趋势",
    "历史",
)


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.workflows.deepsearch_optimized")
    if compat is not None:
        return compat
    return sys.modules[__name__]


def _check_cancel(state: Dict[str, Any]) -> None:
    """Respect cancellation flags/tokens."""
    if state.get("is_cancelled"):
        raise asyncio.CancelledError("Task was cancelled (flag)")
    token_id = state.get("cancel_token_id")
    if token_id:
        _check_cancel_token(token_id)


def _normalize_deepsearch_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode in _DEEPSEARCH_MODES:
        return mode
    return "auto"


def _resolve_deepsearch_mode(config: Dict[str, Any]) -> str:
    cfg = config.get("configurable") or {}
    runtime_mode = cfg.get("deepsearch_mode") if isinstance(cfg, dict) else None
    if runtime_mode is not None:
        return _normalize_deepsearch_mode(runtime_mode)
    return _normalize_deepsearch_mode(getattr(settings, "deepsearch_mode", "auto"))


def _normalize_deepsearch_engine(value: Any) -> str:
    engine = str(value or "").strip().lower()
    if engine in _DEEPSEARCH_ENGINES:
        return engine
    return "legacy"


def _resolve_deepsearch_engine(config: Dict[str, Any]) -> str:
    cfg = config.get("configurable") or {}
    runtime_engine = cfg.get("deepsearch_engine") if isinstance(cfg, dict) else None
    if runtime_engine is not None:
        return _normalize_deepsearch_engine(runtime_engine)
    return _normalize_deepsearch_engine(getattr(settings, "deepsearch_engine", "legacy"))


def _configurable_value(config: Dict[str, Any], key: str) -> Any:
    cfg = config.get("configurable") or {}
    if isinstance(cfg, dict):
        return cfg.get(key)
    return None


def _configurable_int(config: Dict[str, Any], key: str, default: int) -> int:
    value = _configurable_value(config, key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _configurable_float(config: Dict[str, Any], key: str, default: float) -> float:
    value = _configurable_value(config, key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _browser_visualization_enabled(config: Dict[str, Any]) -> bool:
    value = _configurable_value(config, "deepsearch_visualize_browser")
    if value is None:
        return bool(getattr(settings, "deepsearch_visualize_browser", True))
    return bool(value)


def _auto_mode_prefers_linear(topic: str) -> bool:
    text = re.sub(r"\s+", " ", str(topic or "")).strip()
    if not text:
        return False

    lowered = text.lower()
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in _SIMPLE_FACT_PATTERNS):
        return True

    if any(cue in lowered for cue in _BROAD_RESEARCH_CUES):
        return False
    return False


def _resolve_search_strategy() -> SearchStrategy:
    raw = str(getattr(settings, "search_strategy", "fallback") or "fallback").strip().lower()
    try:
        return SearchStrategy(raw)
    except ValueError:
        logger.warning("[deepsearch] invalid search_strategy='%s', fallback to 'fallback'", raw)
        return SearchStrategy.FALLBACK


def _normalize_multi_search_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        normalized.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "summary": r.get("summary") or r.get("snippet", ""),
                "raw_excerpt": r.get("raw_excerpt") or r.get("content", ""),
                "score": float(r.get("score", 0.5) or 0.5),
                "published_date": r.get("published_date"),
                "provider": r.get("provider", ""),
            }
        )
    return normalized


def _resolve_provider_profile(state: Dict[str, Any]) -> Optional[List[str]]:
    deps = _resolve_deps()
    domain_config = state.get("domain_config") or {}
    suggested_sources = domain_config.get("suggested_sources", [])
    domain_value = state.get("domain") or domain_config.get("domain") or "general"
    try:
        domain = deps.ResearchDomain(str(domain_value).strip().lower())
    except ValueError:
        domain = deps.ResearchDomain.GENERAL
    profile = deps.build_provider_profile(suggested_sources=suggested_sources, domain=domain)
    return profile or None


def _cache_query_key(
    query: str,
    max_results: int,
    strategy: SearchStrategy,
    provider_profile: Optional[List[str]] = None,
) -> str:
    profile = ",".join((provider_profile or []))
    return f"deepsearch::{strategy.value}::{max_results}::{profile}::{query}"


def _estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, len(str(text)) // 4)


def _estimate_tokens_from_results(results: List[Dict[str, Any]]) -> int:
    tokens = 0
    for result in results or []:
        if not isinstance(result, dict):
            continue
        tokens += _estimate_tokens_from_text(result.get("title", ""))
        snippet = (
            result.get("raw_excerpt")
            or result.get("summary")
            or result.get("snippet")
            or result.get("content")
            or ""
        )
        tokens += _estimate_tokens_from_text(str(snippet)[:600])
    return tokens


def _budget_stop_reason(
    start_ts: float,
    tokens_used: int,
    max_seconds: float,
    max_tokens: int,
) -> Optional[str]:
    if max_seconds > 0 and (time.time() - start_ts) >= max_seconds:
        return "time_budget_exceeded"
    if max_tokens > 0 and tokens_used >= max_tokens:
        return "token_budget_exceeded"
    return None


def _search_query(
    query: str,
    max_results: int,
    config: Dict[str, Any],
    provider_profile: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    deps = _resolve_deps()
    strategy = deps._resolve_search_strategy()
    cache = deps.get_search_cache()
    cache_key = deps._cache_query_key(query, max_results, strategy, provider_profile)
    cached = cache.get(cache_key)
    if cached is not None:
        deps.logger.info(f"[deepsearch] cache hit for query='{query[:80]}'")
        return copy.deepcopy(cached)

    try:
        kwargs: Dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "strategy": strategy,
        }
        if provider_profile:
            kwargs["provider_profile"] = provider_profile
        multi_results = deps.multi_search(**kwargs)
        normalized = deps._normalize_multi_search_results(multi_results)
        if normalized:
            cache.set(cache_key, copy.deepcopy(normalized))
            return normalized
        deps.logger.info(f"[deepsearch] multi_search returned no results for query='{query[:80]}'")
    except Exception as e:
        deps.logger.warning(f"[deepsearch] multi_search failed, falling back to tavily: {e}")

    try:
        fallback_results = deps.tavily_search.invoke(
            {"query": query, "max_results": max_results},
            config=config,
        )
        if fallback_results:
            cache.set(cache_key, copy.deepcopy(fallback_results))
        return fallback_results
    except Exception as e:
        deps.logger.warning(f"[deepsearch] tavily fallback failed: {e}")
        return []


def _selected_model(config: Dict[str, Any], fallback: str) -> str:
    cfg = config.get("configurable") or {}
    if isinstance(cfg, dict):
        val = cfg.get("model")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _selected_reasoning_model(config: Dict[str, Any], fallback: str) -> str:
    cfg = config.get("configurable") or {}
    if isinstance(cfg, dict):
        val = cfg.get("reasoning_model")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _model_for_task(task_type: str, config: Dict[str, Any]) -> str:
    deps = _resolve_deps()
    try:
        from agent.core.multi_model import TaskType, get_model_router

        tt = TaskType(task_type)
        router = get_model_router()
        return router.get_model_name(tt, config)
    except Exception:
        if task_type in ("planning", "query_gen", "critique", "gap_analysis"):
            return deps._selected_reasoning_model(config, deps.settings.reasoning_model)
        return deps._selected_model(config, deps.settings.primary_model)


__all__ = [
    "_auto_mode_prefers_linear",
    "_browser_visualization_enabled",
    "_budget_stop_reason",
    "_cache_query_key",
    "_check_cancel",
    "_configurable_float",
    "_configurable_int",
    "_configurable_value",
    "_estimate_tokens_from_results",
    "_estimate_tokens_from_text",
    "_model_for_task",
    "_normalize_deepsearch_engine",
    "_normalize_deepsearch_mode",
    "_normalize_multi_search_results",
    "_resolve_deepsearch_engine",
    "_resolve_deepsearch_mode",
    "_resolve_provider_profile",
    "_resolve_search_strategy",
    "_search_query",
    "_selected_model",
    "_selected_reasoning_model",
]
