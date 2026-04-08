from __future__ import annotations

import logging
from typing import Any

from langchain.tools import tool

from common.config import settings
from tools.search.contracts import SearchStrategy
from tools.search.orchestrator import get_search_orchestrator

logger = logging.getLogger(__name__)


def resolve_search_strategy(strategy: SearchStrategy | str | None = None) -> SearchStrategy:
    raw = strategy if strategy is not None else getattr(settings, "search_strategy", "fallback")
    text = str(getattr(raw, "value", raw) or "fallback").strip().lower()
    try:
        return SearchStrategy(text)
    except ValueError:
        logger.warning("[web_search] invalid search_strategy=%s, fallback to fallback", text)
        return SearchStrategy.FALLBACK


def infer_search_source_label(results: list[dict[str, Any]] | None) -> str:
    providers: list[str] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip()
        if provider and provider not in providers:
            providers.append(provider)
    if len(providers) == 1:
        return providers[0]
    return "web_search"


def run_web_search(
    *,
    query: str,
    max_results: int = 5,
    strategy: SearchStrategy | str | None = None,
    provider_profile: list[str] | None = None,
) -> list[dict[str, Any]]:
    effective_profile = [
        str(item).strip()
        for item in (
            provider_profile
            if provider_profile is not None
            else getattr(settings, "search_engines_list", [])
        )
        if str(item).strip()
    ]
    orchestrator = get_search_orchestrator()
    results = orchestrator.search(
        query=query,
        max_results=max_results,
        strategy=resolve_search_strategy(strategy),
        provider_profile=effective_profile or None,
    )
    return [result.to_dict() for result in results]


@tool
def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Search the web via Weaver's unified multi-provider search runtime.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        Normalized search results with summary, snippet, raw excerpt, provider,
        score, and published date where available.
    """
    return run_web_search(query=query, max_results=max_results)


__all__ = [
    "infer_search_source_label",
    "resolve_search_strategy",
    "run_web_search",
    "web_search",
]
