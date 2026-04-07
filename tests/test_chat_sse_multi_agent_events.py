import asyncio
import json

import pytest

import main
from agent.core.events import EventEmitter, ToolEvent


@pytest.mark.asyncio
async def test_stream_flushes_multi_agent_events_before_graph_completion(monkeypatch):
    emitter = EventEmitter(thread_id="thread_test")
    event_released = asyncio.Event()

    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            await emitter.emit(
                ToolEvent.RESEARCH_AGENT_START,
                {"agent_id": "supervisor-1", "role": "supervisor", "phase": "initial_plan"},
            )
            event_released.set()
            await asyncio.sleep(0.2)
            yield {
                "event": "on_graph_end",
                "name": "agent",
                "data": {"output": {"is_complete": True, "final_report": "done"}},
            }

    async def _noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "research_graph", _DummyGraph())
    monkeypatch.setattr(main, "get_emitter", _noop_async)
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)
    async def _fake_get_emitter(thread_id):
        return emitter

    monkeypatch.setattr(main, "get_emitter", _fake_get_emitter)

    stream = main.stream_agent_events("hi", thread_id="thread_test")

    first_chunk = await anext(stream)
    first_payload = json.loads(first_chunk[2:])
    assert first_payload["type"] == "status"

    second_chunk_task = asyncio.create_task(anext(stream))
    await asyncio.wait_for(event_released.wait(), timeout=0.05)
    second_chunk = await asyncio.wait_for(second_chunk_task, timeout=0.05)
    payload = json.loads(second_chunk[2:])

    assert payload["type"] == "research_agent_start"
    assert payload["data"]["role"] == "supervisor"


@pytest.mark.asyncio
async def test_multi_agent_stream_suppresses_generic_clarify_progress(monkeypatch):
    emitter = EventEmitter(thread_id="thread_multi_agent")

    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            await emitter.emit(
                ToolEvent.RESEARCH_AGENT_START,
                {"agent_id": "clarify-1", "role": "clarify", "phase": "intake"},
            )
            yield {"event": "on_node_start", "name": "clarify", "data": {}}
            yield {
                "event": "on_graph_end",
                "name": "agent",
                "data": {"output": {"is_complete": True, "final_report": "done"}},
            }

    async def _noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "research_graph", _DummyGraph())
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)

    async def _fake_get_emitter(thread_id):
        return emitter

    monkeypatch.setattr(main, "get_emitter", _fake_get_emitter)

    events = []
    async for chunk in main.stream_agent_events(
        "hi",
        thread_id="thread_multi_agent",
        search_mode={
            "mode": "deep",
        },
    ):
        events.append(json.loads(chunk[2:]))

    assert any(event["type"] == "research_agent_start" for event in events)
    assert not any(
        event["type"] == "status" and event["data"].get("step") == "clarifying"
        for event in events
    )
    assert not any(
        event["type"] == "thinking" and event["data"].get("node") == "clarify"
        for event in events
    )
