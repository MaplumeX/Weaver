from __future__ import annotations

import sys
from pathlib import Path

SDK_PYTHON_ROOT = Path(__file__).resolve().parent.parent / "sdk" / "python"
sys.path.insert(0, str(SDK_PYTHON_ROOT))

from weaver_sdk.sse import iter_sse_events_from_text, parse_sse_frame  # noqa: E402


def test_parse_sse_frame_extracts_id_event_and_json_data() -> None:
    frame = (
        "id: 3\n"
        "event: text\n"
        'data: {"type":"text","data":{"content":"hi"}}\n'
        "\n"
    )
    parsed = parse_sse_frame(frame)
    assert parsed
    assert parsed.get("id") == 3
    assert parsed.get("event") == "text"
    assert parsed.get("data") == {"type": "text", "data": {"content": "hi"}}


def test_iter_sse_events_ignores_keepalive_comments() -> None:
    text = (
        ": keepalive\n\n"
        "event: status\n"
        'data: {"type":"status","data":{"text":"working"}}\n'
        "\n"
    )
    events = iter_sse_events_from_text(text)
    assert len(events) == 1
    assert events[0]["event"] == "status"
