"""
Multi-provider web search (API-based).

This is adapted from Shannon's `llm_service/tools/builtin/web_search.py`, but implemented
with Weaver's settings and sync `requests` calls so it can be used inside LangChain tools.

Why this exists:
- Directly opening Google/Bing/DuckDuckGo in Playwright often triggers anti-bot challenges.
- API search providers (Serper/SerpAPI/Bing/Exa/Firecrawl/Google CSE) are far more stable.
"""

from __future__ import annotations

import json
import logging
import re
import textwrap
from typing import Any

import requests
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from common.config import settings

logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT_S = 20
_SUMMARY_TOP_RESULTS = 1


def _is_valid_api_key(api_key: str) -> bool:
    if not api_key or not isinstance(api_key, str):
        return False
    api_key = api_key.strip()
    if len(api_key) < 10:
        return False
    if api_key.lower() in {"test", "demo", "example", "your_api_key_here", "xxx"}:
        return False
    return True


def _sanitize_error_message(error: str) -> str:
    sanitized = str(error)
    sanitized = re.sub(r"https?://[^\s]+", "[URL_REDACTED]", sanitized)
    sanitized = re.sub(r"\b[A-Za-z0-9]{32,}\b", "[KEY_REDACTED]", sanitized)
    sanitized = re.sub(
        r"api[_\-]?key[\s=:]+[\w\-]+",
        "api_key=[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"bearer\s+[\w\-\.]+", "Bearer [REDACTED]", sanitized, flags=re.IGNORECASE)
    if len(sanitized) > 300:
        sanitized = sanitized[:300] + "..."
    return sanitized


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


def _trim_text(text: str, max_len: int = 4000) -> str:
    if not text:
        return ""
    return text[:max_len]


def _summarize_content(raw_content: str) -> str | None:
    if not raw_content or not settings.openai_api_key:
        return None

    try:
        params: dict[str, Any] = {
            "model": settings.primary_model,
            "temperature": 0.3,
            "api_key": settings.openai_api_key,
            "timeout": settings.openai_timeout or None,
        }
        if settings.use_azure:
            params.update(
                {
                    "azure_endpoint": settings.azure_endpoint or None,
                    "azure_deployment": settings.primary_model,
                    "api_version": settings.azure_api_version or None,
                    "api_key": settings.azure_api_key or settings.openai_api_key,
                }
            )
        elif settings.openai_base_url:
            params["base_url"] = settings.openai_base_url

        merged_extra: dict[str, Any] = {}
        if settings.openai_extra_body:
            try:
                merged_extra.update(json.loads(settings.openai_extra_body))
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in openai_extra_body; ignoring.")
        if merged_extra:
            params["extra_body"] = merged_extra

        llm = ChatOpenAI(**params)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a concise analyst. Summarize the page into 3-5 bullet points. "
                    "Keep key facts, avoid filler, cite numbers if present.",
                ),
                ("human", "{content}"),
            ]
        )
        response = llm.invoke(prompt.format_messages(content=_trim_text(raw_content, 3500)))
        content = getattr(response, "content", None) or ""
        return textwrap.dedent(content).strip() or None
    except Exception as e:
        logger.warning("Summarization failed: %s", e)
        return None


def tavily_api_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    try:
        try:
            from tavily import TavilyClient  # type: ignore
        except Exception:
            logger.error(
                "Missing dependency: tavily-python. Install with `pip install tavily-python`."
            )
            return []

        if not settings.tavily_api_key:
            logger.warning("TAVILY_API_KEY not configured; returning empty results.")
            return []

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
            include_raw_content=True,
        )

        results = []
        seen_urls = set()
        sorted_results = sorted(
            response.get("results", []), key=lambda r: r.get("score", 0), reverse=True
        )

        for result in sorted_results:
            url = result.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            raw_content = result.get("raw_content", "") or result.get("content", "")
            summary = _summarize_content(raw_content) if len(results) < _SUMMARY_TOP_RESULTS else None

            results.append(
                {
                    "title": result.get("title", ""),
                    "url": url,
                    "summary": summary or _trim_text(result.get("content", ""), 600),
                    "snippet": _trim_text(result.get("content", ""), 600),
                    "raw_excerpt": _trim_text(raw_content, 1200),
                    "score": result.get("score", 0),
                    "published_date": result.get("published_date"),
                    "source": "tavily",
                }
            )

            if len(results) >= max_results:
                break

        logger.info("Tavily search for '%s' returned %s results", query, len(results))
        return results

    except Exception as e:
        logger.error("Tavily search error: %s", e)
        return []


def serper_search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    api_key = (getattr(settings, "serper_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": int(max_results or 10)}

    resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Serper API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: list[dict[str, Any]] = []

    kg = data.get("knowledgeGraph")
    if isinstance(kg, dict) and (kg.get("title") or kg.get("description") or kg.get("website")):
        results.append(
            {
                "title": kg.get("title", "") or "",
                "snippet": kg.get("description", "") or "",
                "url": kg.get("website", "") or "",
                "source": "serper_knowledge_graph",
                "type": kg.get("type", ""),
                "position": 0,
            }
        )

    organic = data.get("organic") or []
    if isinstance(organic, list):
        for idx, item in enumerate(organic, 1):
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": item.get("snippet", "") or "",
                    "url": item.get("link", "") or "",
                    "source": "serper",
                    "position": int(item.get("position") or idx),
                    "date": item.get("date"),
                }
            )

    return results[: int(max_results or 10)]


def serpapi_search(
    query: str, max_results: int = 10, *, engine: str = "google"
) -> list[dict[str, Any]]:
    api_key = (getattr(settings, "serpapi_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "engine": (engine or "google").strip().lower(),
        "q": query,
        "api_key": api_key,
        "num": max(1, min(int(max_results or 10), 100)),
    }

    resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"SerpAPI error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: list[dict[str, Any]] = []

    kg = data.get("knowledge_graph")
    if isinstance(kg, dict) and (kg.get("title") or kg.get("description")):
        kg_url = ""
        kg_source = kg.get("source")
        if isinstance(kg_source, dict):
            kg_url = kg_source.get("link", "") or ""
        elif isinstance(kg_source, str):
            kg_url = kg_source
        results.append(
            {
                "title": kg.get("title", "") or "",
                "snippet": kg.get("description", "") or "",
                "url": kg_url,
                "source": "serpapi_knowledge_graph",
                "type": kg.get("type", ""),
                "position": 0,
            }
        )

    organic = data.get("organic_results") or []
    if isinstance(organic, list):
        for idx, item in enumerate(organic, 1):
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": item.get("snippet", "") or "",
                    "url": item.get("link", "") or "",
                    "source": "serpapi",
                    "position": int(item.get("position") or idx),
                    "date": item.get("date"),
                }
            )

    return results[: int(max_results or 10)]


def bing_search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    api_key = (getattr(settings, "bing_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://api.cognitive.microsoft.com/bing/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {
        "q": query,
        "count": max(1, min(int(max_results or 10), 50)),
        "textDecorations": True,
        "textFormat": "HTML",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Bing Search API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: list[dict[str, Any]] = []

    web_pages = data.get("webPages") if isinstance(data, dict) else None
    values = web_pages.get("value") if isinstance(web_pages, dict) else None
    if isinstance(values, list):
        for idx, item in enumerate(values, 1):
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("name", "") or "",
                    "snippet": item.get("snippet", "") or "",
                    "url": item.get("url", "") or "",
                    "source": "bing",
                    "position": idx,
                    "date": item.get("dateLastCrawled"),
                }
            )

    return results[: int(max_results or 10)]


def google_cse_search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    api_key = (getattr(settings, "google_search_api_key", "") or "").strip()
    search_engine_id = (getattr(settings, "google_search_engine_id", "") or "").strip()
    if not (_is_valid_api_key(api_key) and search_engine_id):
        return []

    url = "https://customsearch.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": search_engine_id,
        "q": query,
        "num": min(max(1, int(max_results or 10)), 10),
    }

    resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Google CSE API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: list[dict[str, Any]] = []

    items = data.get("items") or []
    if isinstance(items, list):
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet", "") or ""
            content = snippet
            page_map = item.get("pagemap") or {}
            if isinstance(page_map, dict):
                metatags = page_map.get("metatags")
                if isinstance(metatags, list) and metatags and isinstance(metatags[0], dict):
                    mt = metatags[0]
                    content = (mt.get("og:description") or mt.get("description") or content) or ""
                    content = content[:500]

            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": snippet,
                    "url": item.get("link", "") or "",
                    "source": "google_cse",
                    "position": idx,
                    "display_link": item.get("displayLink", ""),
                    "content": content,
                }
            )

    return results[: int(max_results or 10)]


def exa_search(
    query: str,
    max_results: int = 10,
    *,
    search_type: str = "auto",
    category: str | None = None,
) -> list[dict[str, Any]]:
    api_key = (getattr(settings, "exa_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://api.exa.ai/search"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    search_type_norm = (search_type or "auto").strip().lower()
    if search_type_norm not in {"neural", "keyword", "auto"}:
        search_type_norm = "auto"

    payload: dict[str, Any] = {
        "query": query,
        "numResults": max(1, min(int(max_results or 10), 100)),
        "type": search_type_norm,
        "useAutoprompt": True,
        "contents": {
            "text": {"maxCharacters": 2000, "includeHtmlTags": False},
            "highlights": {"numSentences": 3, "highlightsPerUrl": 2},
        },
        "liveCrawl": "fallback",
    }
    if category:
        payload["category"] = category

    resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Exa API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: list[dict[str, Any]] = []

    items = data.get("results") or []
    if isinstance(items, list):
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            highlights = item.get("highlights") or []
            snippet = ""
            if isinstance(highlights, list):
                parts = [h.strip() for h in highlights if isinstance(h, str) and h.strip()]
                snippet = " ... ".join(parts)[:500]
            if not snippet:
                snippet = (item.get("text", "") or "")[:500]

            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": snippet,
                    "url": item.get("url", "") or "",
                    "source": "exa",
                    "position": idx,
                    "score": item.get("score", 0),
                    "published_date": item.get("publishedDate"),
                    "author": item.get("author"),
                    "highlights": highlights,
                }
            )

    return results[: int(max_results or 10)]


def firecrawl_search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    api_key = (getattr(settings, "firecrawl_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://api.firecrawl.dev/v2/search"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "query": query,
        "limit": min(max(1, int(max_results or 10)), 20),
        "sources": ["web"],
        "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Firecrawl API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: list[dict[str, Any]] = []

    # Firecrawl responses can be:
    # - {"data": [...]} (older)
    # - {"data": {"web": [...]}} (v2)
    raw_items: Any = data.get("data") or []
    items: list[Any] = []
    if isinstance(raw_items, list):
        items = raw_items
    elif isinstance(raw_items, dict):
        # Prefer the "web" bucket when present (matches our request sources=["web"]).
        web_items = raw_items.get("web")
        if isinstance(web_items, list):
            items = web_items
        else:
            # Fallback: first list-valued field.
            for val in raw_items.values():
                if isinstance(val, list):
                    items = val
                    break

    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        content = ""
        if item.get("markdown"):
            content = str(item.get("markdown") or "")[:300]
        elif item.get("description"):
            content = str(item.get("description") or "")

        results.append(
            {
                "title": item.get("title", "") or "",
                "snippet": content,
                "url": item.get("url", "") or "",
                "source": "firecrawl",
                "position": idx,
                "markdown": item.get("markdown", "") or "",
            }
        )

    return results[: int(max_results or 10)]


__all__ = [
    "_sanitize_error_message",
    "bing_search",
    "exa_search",
    "firecrawl_search",
    "google_cse_search",
    "serpapi_search",
    "serper_search",
    "tavily_api_search",
]
