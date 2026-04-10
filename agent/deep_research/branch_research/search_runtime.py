"""Search-runtime helpers for Deep Research branches."""

from __future__ import annotations

import logging
from typing import Any

from agent.execution.intake.domain_router import ResearchDomain, build_provider_profile
from tools.search.contracts import SearchStrategy
from tools.search.web_search import resolve_search_strategy, run_web_search

logger = logging.getLogger(__name__)


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


__all__ = [
    "_resolve_provider_profile",
    "_resolve_search_strategy",
    "_search_query",
    "run_web_search",
]
