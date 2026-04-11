import asyncio
import json

import pytest
from langgraph.types import Command

import main
from agent.foundation.events import EventEmitter, ToolEvent


async def _noop_async(*args, **kwargs):
    return None


def _common_stream_monkeypatch(monkeypatch):
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)


@pytest.mark.asyncio
async def test_stream_uses_top_level_tool_name_for_langchain_events(monkeypatch):
    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            yield {
                "event": "on_tool_start",
                "name": "demo_search",
                "run_id": "tool-run-1",
                "data": {"input": {"query": "agent observability"}},
            }
            yield {
                "event": "on_tool_end",
                "name": "demo_search",
                "run_id": "tool-run-1",
                "data": {
                    "input": {"query": "agent observability"},
                    "output": {"ok": True},
                },
            }
            yield {
                "event": "on_graph_end",
                "name": "agent",
                "data": {"output": {"is_complete": True, "final_report": "done"}},
            }

    _common_stream_monkeypatch(monkeypatch)
    monkeypatch.setattr(main, "research_graph", _DummyGraph())

    chunks = []
    async for chunk in main.stream_agent_events("hi", thread_id="thread_test_tools"):
        chunks.append(chunk)

    payloads = [json.loads(chunk[2:]) for chunk in chunks if chunk.startswith("0:")]
    tool_events = [p for p in payloads if p.get("type") == "tool"]

    assert len(tool_events) >= 2
    assert tool_events[0]["data"]["name"] == "demo_search"
    assert tool_events[0]["data"]["tool_id"] == "demo_search"
    assert tool_events[0]["data"]["phase"] == "start"
    assert tool_events[0]["data"]["status"] == "running"
    assert tool_events[0]["data"]["toolCallId"] == "tool-run-1"
    assert tool_events[1]["data"]["name"] == "demo_search"
    assert tool_events[1]["data"]["tool_id"] == "demo_search"
    assert tool_events[1]["data"]["phase"] == "result"
    assert tool_events[1]["data"]["status"] == "completed"
    assert tool_events[1]["data"]["toolCallId"] == "tool-run-1"


@pytest.mark.asyncio
async def test_stream_flushes_tool_progress_before_graph_completion(monkeypatch):
    emitter = EventEmitter(thread_id="thread_test_progress")
    progress_event_released = asyncio.Event()

    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            await emitter.emit(
                ToolEvent.TOOL_PROGRESS,
                {"tool": "browser_search", "action": "navigate", "info": "https://example.com"},
            )
            progress_event_released.set()
            await asyncio.sleep(0.2)
            yield {
                "event": "on_graph_end",
                "name": "agent",
                "data": {"output": {"is_complete": True, "final_report": "done"}},
            }

    _common_stream_monkeypatch(monkeypatch)
    monkeypatch.setattr(main, "research_graph", _DummyGraph())

    async def _fake_get_emitter(thread_id):
        return emitter

    monkeypatch.setattr(main, "get_emitter", _fake_get_emitter)

    stream = main.stream_agent_events("hi", thread_id="thread_test_progress")

    first_chunk = await anext(stream)
    first_payload = json.loads(first_chunk[2:])
    assert first_payload["type"] == "status"

    second_chunk_task = asyncio.create_task(anext(stream))
    await asyncio.wait_for(progress_event_released.wait(), timeout=0.05)
    second_chunk = await asyncio.wait_for(second_chunk_task, timeout=0.05)
    payload = json.loads(second_chunk[2:])

    assert payload["type"] == "tool_progress"
    assert payload["data"]["name"] == "browser_search"
    assert payload["data"]["tool"] == "browser_search"
    assert payload["data"]["tool_id"] == "browser_search"
    assert payload["data"]["phase"] == "progress"

    remaining = []
    async for chunk in stream:
        remaining.append(chunk)

    remaining_payloads = [json.loads(chunk[2:]) for chunk in remaining if chunk.startswith("0:")]
    remaining_types = [payload["type"] for payload in remaining_payloads]
    assert "completion" in remaining_types


@pytest.mark.asyncio
async def test_format_stream_event_serializes_langgraph_command_payload():
    payload = main._build_langchain_tool_stream_payload(
        status="completed",
        event_name="demo_search",
        data={
            "input": {"query": "agent observability"},
            "output": Command(resume={"approved": True}),
        },
        run_id="tool-run-2",
    )

    chunk = await main.format_stream_event("tool", payload)
    decoded = json.loads(chunk[2:])

    assert decoded["type"] == "tool"
    assert decoded["data"]["toolCallId"] == "tool-run-2"
    assert decoded["data"]["payload"]["output"]["resume"] == {"approved": True}
