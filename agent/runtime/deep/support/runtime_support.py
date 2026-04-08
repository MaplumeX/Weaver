"""
Shared helpers for the multi-agent deep runtime.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agent.infrastructure.agents.factory import resolve_deep_research_role_tool_policy
from agent.infrastructure.tools import build_tool_context
from agent.research.domain_router import ResearchDomain, build_provider_profile
from common.config import settings
from tools.search.contracts import SearchStrategy
from tools.search.web_search import resolve_search_strategy, run_web_search

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


def _tool_runtime_context_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    try:
        runtime = build_tool_context(config).runtime
    except Exception:
        return {}
    return {
        "thread_id": runtime.thread_id,
        "user_id": runtime.user_id,
        "session_id": runtime.session_id,
        "agent_id": runtime.agent_id,
        "run_id": runtime.run_id,
        "roles": list(runtime.roles),
        "capabilities": list(runtime.capabilities),
        "blocked_capabilities": list(runtime.blocked_capabilities),
        "e2b_ready": bool(runtime.e2b_ready),
    }


def _deep_research_role_tool_policy_snapshot(
    role: str,
    *,
    allowed_tools: list[str] | None = None,
) -> dict[str, Any]:
    policy = resolve_deep_research_role_tool_policy(
        role,
        allowed_tools=allowed_tools,
        enable_supervisor_world_tools=bool(
            getattr(settings, "deep_research_supervisor_allow_world_tools", False)
        ),
        enable_reporter_python_tools=bool(
            getattr(settings, "deep_research_reporter_enable_python_tools", True)
        ),
    )
    return {
        "role": policy.role,
        "requested_tools": list(policy.requested_tools),
        "allowed_tool_names": list(policy.allowed_tool_names),
    }


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
    return resolve_search_strategy()


def _search_query(
    query: str,
    max_results: int,
    config: dict[str, Any],
    provider_profile: list[str] | None = None,
) -> list[dict[str, Any]]:
    strategy = _resolve_search_strategy()
    try:
        return run_web_search(
            query=query,
            max_results=max_results,
            strategy=strategy,
            provider_profile=provider_profile,
        )
    except Exception as exc:
        logger.warning("[deep-research-multi-agent] web_search failed: %s", exc)
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
    "_deep_research_role_tool_policy_snapshot",
    "_estimate_tokens_from_results",
    "_estimate_tokens_from_text",
    "_model_for_task",
    "_new_id",
    "_resolve_provider_profile",
    "_search_query",
    "_tool_runtime_context_snapshot",
]
