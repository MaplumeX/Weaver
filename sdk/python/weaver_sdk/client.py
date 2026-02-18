from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from .sse import parse_sse_frame
from .types import StreamEvent


@dataclass(frozen=True)
class WeaverApiError(RuntimeError):
    status: int
    path: str
    body_text: str

    def __str__(self) -> str:
        suffix = f": {self.body_text}" if self.body_text else ""
        return f"Weaver API request failed ({self.status}) {self.path}{suffix}"


def _normalize_base_url(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "http://127.0.0.1:8001"
    return text.rstrip("/")


class WeaverClient:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8001",
        headers: dict[str, str] | None = None,
        timeout_s: float = 60.0,
        http: httpx.Client | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.headers = headers or {}
        self.timeout_s = float(timeout_s)
        self._http = http or httpx.Client(timeout=self.timeout_s)

    def _url(self, path: str) -> str:
        p = path if str(path).startswith("/") else f"/{path}"
        return f"{self.base_url}{p}"

    def request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        merged_headers = {"Accept": "application/json", **self.headers, **(headers or {})}
        resp = self._http.request(
            method=method,
            url=self._url(path),
            headers=merged_headers,
            params=params,
            json=json_body,
        )

        body_text = resp.text or ""
        if resp.status_code < 200 or resp.status_code >= 300:
            raise WeaverApiError(status=resp.status_code, path=path, body_text=body_text)

        if not body_text.strip():
            return None

        try:
            return resp.json()
        except Exception:
            return body_text

    def chat_sse(self, payload: dict[str, Any]) -> Iterator[StreamEvent]:
        """
        Start a chat request and yield StreamEvent items parsed from SSE frames.

        The server typically emits JSON envelope objects: {"type": "...", "data": {...}}.
        This method yields that envelope when present, otherwise falls back to
        {"type": <event>, "data": <parsed data>}.
        """
        merged_headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            **self.headers,
        }

        with self._http.stream(
            "POST",
            self._url("/api/chat/sse"),
            headers=merged_headers,
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ) as resp:
            body_text = ""
            if resp.status_code < 200 or resp.status_code >= 300:
                try:
                    body_text = resp.read().decode("utf-8", errors="ignore")
                except Exception:
                    body_text = ""
                raise WeaverApiError(status=resp.status_code, path="/api/chat/sse", body_text=body_text)

            buffer = ""
            for chunk in resp.iter_bytes():
                try:
                    buffer += chunk.decode("utf-8", errors="ignore")
                except Exception:
                    continue

                buffer = buffer.replace("\r\n", "\n")
                frames = buffer.split("\n\n")
                buffer = frames.pop() or ""

                for frame in frames:
                    parsed = parse_sse_frame(frame)
                    if not parsed:
                        continue

                    data = parsed.get("data")
                    if isinstance(data, dict) and "type" in data and "data" in data:
                        yield data  # type: ignore[misc]
                        continue

                    event_name = parsed.get("event")
                    if isinstance(event_name, str) and event_name:
                        yield {"type": event_name, "data": data}

            tail = buffer.strip()
            if tail:
                parsed = parse_sse_frame(tail)
                if parsed:
                    data = parsed.get("data")
                    if isinstance(data, dict) and "type" in data and "data" in data:
                        yield data  # type: ignore[misc]
                    else:
                        event_name = parsed.get("event")
                        if isinstance(event_name, str) and event_name:
                            yield {"type": event_name, "data": data}
