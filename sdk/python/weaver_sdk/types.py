from __future__ import annotations

from typing import Any, TypedDict


class StreamEvent(TypedDict):
    type: str
    data: Any


class SseEvent(TypedDict, total=False):
    id: int
    event: str
    data: Any

