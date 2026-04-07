import json

import pytest

import main


async def _noop_async(*args, **kwargs):
    return None


def _common_stream_monkeypatch(monkeypatch):
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)


@pytest.mark.asyncio
async def test_stream_deduplicates_tool_agent_generic_progress(monkeypatch):
    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            for event_name in ("on_graph_start", "on_node_start", "on_chain_start"):
                yield {
                    "event": event_name,
                    "name": "tool_agent",
                    "run_id": "tool-agent-run-1",
                    "data": {},
                }
            yield {
                "event": "on_graph_end",
                "name": "tool_agent",
                "data": {"output": {"is_complete": True, "final_report": "done"}},
            }

    _common_stream_monkeypatch(monkeypatch)
    monkeypatch.setattr(main, "research_graph", _DummyGraph())

    payloads = []
    async for chunk in main.stream_agent_events("hi", thread_id="thread-agent-progress"):
        if chunk.startswith("0:"):
            payloads.append(json.loads(chunk[2:]))

    agent_statuses = [
        payload
        for payload in payloads
        if payload["type"] == "status" and payload["data"].get("step") == "agent_tools"
    ]

    assert len(agent_statuses) == 1
    assert not any(
        payload["type"] == "thinking" and payload["data"].get("node") == "tool_agent"
        for payload in payloads
    )


def test_chat_respond_node_has_no_first_person_thinking_intro():
    assert main._thinking_intro_for_node("chat_respond", use_zh=True) == ""
