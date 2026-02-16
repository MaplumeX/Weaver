from common.sse import format_sse_event


def test_format_sse_event_includes_event_and_data_and_double_newline():
    text = format_sse_event(
        event="status",
        data={"type": "status", "data": {"text": "hi"}},
        event_id=3,
    )
    assert "id: 3\n" in text
    assert "event: status\n" in text
    assert "data: " in text
    assert text.endswith("\n\n")

