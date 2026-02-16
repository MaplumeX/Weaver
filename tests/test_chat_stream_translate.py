from common.chat_stream_translate import translate_legacy_line_to_sse


def test_translate_legacy_line_to_sse_maps_type_to_event():
    line = '0:{"type":"text","data":{"content":"hello"}}\n'
    out = translate_legacy_line_to_sse(line, seq=1)
    assert "event: text" in out
    assert "id: 1" in out

