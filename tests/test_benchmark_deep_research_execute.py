
from scripts.benchmark_deep_research import (
    _parse_sse_frame,
)


def test_parse_sse_frame_extracts_event_and_json():
    parsed = _parse_sse_frame('event: status\ndata: {"text":"hi"}\n')
    assert parsed == ("status", {"text": "hi"})


def test_parse_sse_frame_unwraps_legacy_envelope():
    parsed = _parse_sse_frame('event: text\ndata: {"type":"text","data":{"content":"hi"}}\n')
    assert parsed == ("text", {"content": "hi"})


def test_parse_sse_frame_ignores_empty_and_comments():
    assert _parse_sse_frame("") is None
    assert _parse_sse_frame(": keepalive\n\n") is None
    assert _parse_sse_frame("data: x\n") is None
