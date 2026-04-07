import json

import pytest
from langgraph.errors import GraphInterrupt
from langgraph.types import Interrupt

import main


async def _noop_async(*args, **kwargs):
    return None


def _common_stream_monkeypatch(monkeypatch):
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)

    class _DummyEmitter:
        def on_event(self, listener):
            self.listener = listener

        def off_event(self, listener):
            return None

    async def _fake_get_emitter(thread_id):
        return _DummyEmitter()

    monkeypatch.setattr(main, "get_emitter", _fake_get_emitter)


class _FakeCheckpointTuple:
    def __init__(self, prompts):
        self.pending_writes = [("task", "__interrupt__", prompts)]


def _install_interrupt_checkpoint(monkeypatch, prompt):
    class _DummyCheckpointer:
        def get_tuple(self, config):
            return _FakeCheckpointTuple([prompt])

    monkeypatch.setattr(main, "checkpointer", _DummyCheckpointer())


@pytest.mark.asyncio
async def test_stream_emits_interrupt_when_graph_ends_without_final_output(monkeypatch):
    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            yield {"event": "on_node_start", "name": "clarify", "data": {}}
            yield {"event": "on_graph_end", "name": "agent", "data": {"output": {}}}

    _common_stream_monkeypatch(monkeypatch)
    _install_interrupt_checkpoint(
        monkeypatch,
        {
            "checkpoint": "deep_research_clarify",
            "message": "请补充研究目标",
            "instruction": "Answer the clarification question so Deep Research can draft the scope.",
        },
    )
    monkeypatch.setattr(main, "research_graph", _DummyGraph())

    payloads = []
    async for chunk in main.stream_agent_events("hi", thread_id="thread_test_interrupt_end"):
        if chunk.startswith("0:"):
            payloads.append(json.loads(chunk[2:]))

    types = [payload.get("type") for payload in payloads]
    assert "interrupt" in types
    interrupt_payload = payloads[types.index("interrupt")]
    assert interrupt_payload["data"]["prompts"][0]["checkpoint"] == "deep_research_clarify"
    assert "completion" not in types
    assert "done" not in types


@pytest.mark.asyncio
async def test_stream_emits_interrupt_when_graph_bubbles_up_interrupt(monkeypatch):
    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            yield {"event": "on_node_start", "name": "clarify", "data": {}}
            raise GraphInterrupt(
                (
                    Interrupt(
                        value={
                            "checkpoint": "deep_research_clarify",
                            "message": "请补充研究目标",
                        }
                    ),
                )
            )

    _common_stream_monkeypatch(monkeypatch)
    _install_interrupt_checkpoint(
        monkeypatch,
        {
            "checkpoint": "deep_research_clarify",
            "message": "请补充研究目标",
            "instruction": "Answer the clarification question so Deep Research can draft the scope.",
        },
    )
    monkeypatch.setattr(main, "research_graph", _DummyGraph())

    payloads = []
    async for chunk in main.stream_agent_events("hi", thread_id="thread_test_interrupt_raise"):
        if chunk.startswith("0:"):
            payloads.append(json.loads(chunk[2:]))

    types = [payload.get("type") for payload in payloads]
    assert "interrupt" in types
    interrupt_payload = payloads[types.index("interrupt")]
    assert interrupt_payload["data"]["prompts"][0]["checkpoint"] == "deep_research_clarify"
    assert "error" not in types
