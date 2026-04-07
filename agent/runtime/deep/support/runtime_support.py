"""
Shared helpers for the multi-agent deep runtime.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from typing import Any

from agent.contracts.search_cache import get_search_cache
from agent.research.domain_router import ResearchDomain, build_provider_profile
from common.config import settings
from tools import tavily_search
from tools.search.multi_search import SearchStrategy, multi_search

logger = logging.getLogger(__name__)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _configurable_value(config: dict[str, Any], key: str) -> Any:
    cfg = config.get("configurable") or {}
    if isinstance(cfg, dict):
        return cfg.get(key)
    return None


def _configurable_int(config: dict[str, Any], key: str, default: int) -> int:
    value = _configurable_value(config, key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _configurable_float(config: dict[str, Any], key: str, default: float) -> float:
    value = _configurable_value(config, key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _selected_model(config: dict[str, Any], fallback: str) -> str:
    value = _configurable_value(config, "model")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _selected_reasoning_model(config: dict[str, Any], fallback: str) -> str:
    value = _configurable_value(config, "reasoning_model")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _model_for_task(task_type: str, config: dict[str, Any]) -> str:
    try:
        from agent.core.multi_model import TaskType, get_model_router

        task = TaskType(task_type)
        return get_model_router().get_model_name(task, config)
    except Exception:
        if task_type in {"planning", "query_gen", "critique", "gap_analysis"}:
            return _selected_reasoning_model(config, settings.reasoning_model)
        return _selected_model(config, settings.primary_model)


def _resolve_provider_profile(state: dict[str, Any]) -> list[str] | None:
    domain_config = state.get("domain_config") or {}
    suggested_sources = domain_config.get("suggested_sources", [])
    domain_value = state.get("domain") or domain_config.get("domain") or "general"
    try:
        domain = ResearchDomain(str(domain_value).strip().lower())
    except ValueError:
        domain = ResearchDomain.GENERAL
    profile = build_provider_profile(suggested_sources=suggested_sources, domain=domain)
    return profile or None


def _resolve_search_strategy() -> SearchStrategy:
    raw = str(getattr(settings, "search_strategy", "fallback") or "fallback").strip().lower()
    try:
        return SearchStrategy(raw)
    except ValueError:
        logger.warning(
            "[deep-research-multi-agent] invalid search_strategy=%s, fallback to fallback",
            raw,
        )
        return SearchStrategy.FALLBACK


def _normalize_multi_search_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "summary": item.get("summary") or item.get("snippet", ""),
                "raw_excerpt": item.get("raw_excerpt") or item.get("content", ""),
                "score": float(item.get("score", 0.5) or 0.5),
                "published_date": item.get("published_date"),
                "provider": item.get("provider", ""),
            }
        )
    return normalized


def _cache_query_key(
    query: str,
    max_results: int,
    strategy: SearchStrategy,
    provider_profile: list[str] | None,
) -> str:
    joined_profile = ",".join(provider_profile or [])
    return f"deep-research-multi-agent::{strategy.value}::{max_results}::{joined_profile}::{query}"


def _search_query(
    query: str,
    max_results: int,
    config: dict[str, Any],
    provider_profile: list[str] | None = None,
) -> list[dict[str, Any]]:
    strategy = _resolve_search_strategy()
    cache = get_search_cache()
    cache_key = _cache_query_key(query, max_results, strategy, provider_profile)
    cached = cache.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    try:
        kwargs: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "strategy": strategy,
        }
        if provider_profile:
            kwargs["provider_profile"] = provider_profile
        multi_results = multi_search(**kwargs)
        normalized = _normalize_multi_search_results(multi_results)
        if normalized:
            cache.set(cache_key, copy.deepcopy(normalized))
            return normalized
    except Exception as exc:
        logger.warning("[deep-research-multi-agent] multi_search failed, falling back: %s", exc)

    try:
        fallback_results = tavily_search.invoke(
            {"query": query, "max_results": max_results},
            config=config,
        )
        if fallback_results:
            cache.set(cache_key, copy.deepcopy(fallback_results))
        return fallback_results or []
    except Exception as exc:
        logger.warning("[deep-research-multi-agent] tavily_search failed: %s", exc)
        return []


def _estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, len(str(text)) // 4)


def _estimate_tokens_from_results(results: list[dict[str, Any]]) -> int:
    total = 0
    for item in results or []:
        if not isinstance(item, dict):
            continue
        total += _estimate_tokens_from_text(item.get("title", ""))
        total += _estimate_tokens_from_text(
            str(
                item.get("raw_excerpt")
                or item.get("summary")
                or item.get("snippet")
                or item.get("content")
                or ""
            )[:600]
        )
    return total


def _budget_stop_reason(
    *,
    start_ts: float,
    searches_used: int,
    tokens_used: int,
    max_seconds: float,
    max_tokens: int,
    max_searches: int,
) -> str | None:
    if max_seconds > 0 and (time.time() - start_ts) >= max_seconds:
        return "time_budget_exceeded"
    if max_tokens > 0 and tokens_used >= max_tokens:
        return "token_budget_exceeded"
    if max_searches > 0 and searches_used >= max_searches:
        return "search_budget_exceeded"
    return None


def _compact_sources(results: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    seen: set[str] = set()
    compacted: list[dict[str, Any]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        compacted.append(
            {
                "title": item.get("title", "") or url,
                "url": url,
                "provider": item.get("provider", ""),
                "published_date": item.get("published_date"),
            }
        )
        if len(compacted) >= limit:
            break
    return compacted


__all__ = [
    "_budget_stop_reason",
    "_compact_sources",
    "_configurable_float",
    "_configurable_int",
    "_configurable_value",
    "_estimate_tokens_from_results",
    "_estimate_tokens_from_text",
    "_model_for_task",
    "_new_id",
    "_resolve_provider_profile",
    "_search_query",
]
