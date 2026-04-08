import json

import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_tool_events_endpoint_normalizes_lifecycle_events_to_tool(monkeypatch):
    async def _fake_require_thread_owner(*_args, **_kwargs):
        return None

    async def _fake_event_stream_generator(thread_id: str, *, timeout: float, last_event_id=None):
        assert thread_id == "thread_events_norm"
        yield (
            "id: 1\n"
            "event: tool_start\n"
            'data: {"type":"tool_start","data":{"tool":"browser_search","args":{"query":"openai"}}}\n\n'
        )

    monkeypatch.setattr(main, "_require_thread_owner", _fake_require_thread_owner)
    monkeypatch.setattr(main, "event_stream_generator", _fake_event_stream_generator)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/events/thread_events_norm")

    assert resp.status_code == 200
    body = resp.text
    assert "event:" not in body
    data_line = next(line for line in body.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[6:])

    assert payload["type"] == "tool"
    assert payload["data"]["tool"] == "browser_search"
    assert payload["data"]["tool_id"] == "browser_search"
    assert payload["data"]["phase"] == "start"
    assert payload["data"]["status"] == "running"
