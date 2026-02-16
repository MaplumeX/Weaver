from __future__ import annotations

import re
from typing import Optional

import requests

from agent.workflows.source_registry import SourceRegistry
from common.config import settings
from tools.research.models import FetchedPage, truncate_bytes

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _strip_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<noscript.*?>.*?</noscript>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _content_type(headers: object) -> str:
    if not headers:
        return ""
    if isinstance(headers, dict):
        for key in ("content-type", "Content-Type", "CONTENT-TYPE"):
            value = headers.get(key)
            if value:
                return str(value)
        return ""
    return ""


class ContentFetcher:
    def __init__(self) -> None:
        self._registry = SourceRegistry()

    def fetch(self, url: str) -> FetchedPage:
        raw_url = (url or "").strip()
        canonical_url = self._registry.canonicalize_url(raw_url)
        if not canonical_url:
            return FetchedPage(
                url="",
                raw_url=raw_url,
                method="direct_http",
                error="url is required",
                attempts=1,
            )

        try:
            resp = requests.get(
                canonical_url,
                timeout=settings.research_fetch_timeout_s,
                headers={"User-Agent": DEFAULT_UA},
            )
        except Exception as exc:
            return FetchedPage(
                url=canonical_url,
                raw_url=raw_url,
                method="direct_http",
                error=str(exc),
                attempts=1,
            )

        status_code: Optional[int]
        try:
            status_code = int(getattr(resp, "status_code", None))
        except Exception:
            status_code = None

        headers = getattr(resp, "headers", None)
        content_type = _content_type(headers).lower()

        raw_bytes = getattr(resp, "content", b"") or b""
        raw_bytes = truncate_bytes(raw_bytes, max_bytes=settings.research_fetch_max_bytes)

        decoded = ""
        if raw_bytes:
            decoded = raw_bytes.decode("utf-8", errors="replace")
        else:
            decoded = str(getattr(resp, "text", "") or "")

        text = decoded
        if "html" in content_type:
            text = _strip_html(decoded)

        return FetchedPage(
            url=canonical_url,
            raw_url=raw_url,
            method="direct_http",
            text=text or None,
            http_status=status_code,
            attempts=1,
        )
