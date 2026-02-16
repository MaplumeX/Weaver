from __future__ import annotations

import json
from typing import Any


def format_sse_event(*, event: str, data: Any, event_id: int | None = None) -> str:
    """
    Format a single Server-Sent Events (SSE) frame.

    We intentionally emit a single `data:` line containing JSON to keep client
    parsing simple and predictable.
    """
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"

