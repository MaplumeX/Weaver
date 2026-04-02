import pytest
from langgraph.errors import GraphInterrupt
from langgraph.types import Interrupt

from agent.runtime.deep import entrypoints as deep_entrypoints
import agent.runtime.nodes.deepsearch as nodes


def test_deepsearch_node_uses_auto_runner(monkeypatch):
    called = {"auto": False}

    def fake_auto(state, config):
        called["auto"] = True
        return {"runner": "auto", "state": state}

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)

    result = nodes.deepsearch_node({"input": "test"}, {})

    assert called["auto"] is True
    assert result["runner"] == "auto"


def test_deepsearch_node_delegates_simple_factual_query_to_agent_node(monkeypatch):
    called = {"agent": False}

    def fake_agent(state, config):
        called["agent"] = True
        assert state["route"] == "agent"
        return {"final_report": "Paris", "messages": []}

    def fake_auto(state, config):
        raise AssertionError("deepsearch runner should be skipped for simple factual query")

    monkeypatch.setattr(nodes, "agent_node", fake_agent, raising=False)
    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)

    result = nodes.deepsearch_node(
        {"input": "Use deep research to answer: what is the capital of France?"},
        {"configurable": {}},
    )

    assert called["agent"] is True
    assert result["final_report"] == "Paris"


def test_run_deepsearch_auto_dispatches_supported_runtime(monkeypatch):
    monkeypatch.setattr(
        deep_entrypoints,
        "_run_deepsearch_runtime",
        lambda _state, _config: {"mode": "multi_agent", "is_cancelled": False},
    )

    result = deep_entrypoints.run_deepsearch_auto({"input": "test"}, {"configurable": {}})

    assert result["mode"] == "multi_agent"
    assert result["_deepsearch_events_emitted"] is True


@pytest.mark.parametrize(
    "configurable,expected",
    [
        ({"deepsearch_engine": "legacy"}, "deepsearchEngine=legacy"),
        ({"deepsearch_mode": "linear"}, "deepsearch_mode"),
        ({"tree_parallel_branches": 1}, "tree_parallel_branches"),
        ({"deepsearch_tree_max_searches": 1}, "deepsearch_tree_max_searches"),
    ],
)
def test_run_deepsearch_auto_rejects_legacy_runtime_inputs(configurable, expected):
    with pytest.raises(ValueError, match=expected):
        deep_entrypoints.run_deepsearch_auto({"input": "test"}, {"configurable": configurable})


def test_run_deepsearch_auto_reraises_runtime_interrupt(monkeypatch):
    def fake_runtime(state, config):
        raise GraphInterrupt((Interrupt(value={"checkpoint": "deepsearch_clarify"}),))

    monkeypatch.setattr(deep_entrypoints, "_run_deepsearch_runtime", fake_runtime)

    with pytest.raises(GraphInterrupt):
        deep_entrypoints.run_deepsearch_auto({"input": "test"}, {"configurable": {}})


def test_run_deepsearch_auto_does_not_mark_cancelled_result(monkeypatch):
    monkeypatch.setattr(
        deep_entrypoints,
        "_run_deepsearch_runtime",
        lambda _state, _config: {"is_cancelled": True, "final_report": "cancelled"},
    )

    result = deep_entrypoints.run_deepsearch_auto({"input": "test"}, {"configurable": {}})
    assert "_deepsearch_events_emitted" not in result


def test_deepsearch_node_emits_visualization_events(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.8, "freshness_warning": ""},
            "deepsearch_artifacts": {"research_tree": {"id": "root", "children": []}},
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    result = nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    event_types = [name for name, _ in emitted]

    assert result["final_report"] == "final report"
    assert event_types[0] == "research_node_start"
    assert "quality_update" in event_types
    assert "research_tree_update" in event_types
    assert event_types[-1] == "research_node_complete"
    quality_events = [data for name, data in emitted if name == "quality_update"]
    assert quality_events
    assert quality_events[0].get("stage") == "final"


def test_deepsearch_node_emits_compact_unique_preview_sources(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.8},
            "scraped_content": [
                {
                    "query": "q1",
                    "results": [
                        {
                            "title": "A",
                            "url": "https://example.com/a",
                            "provider": "serper",
                            "published_date": "2026-02-01",
                        },
                        {
                            "title": "B",
                            "url": "https://example.com/b",
                            "provider": "serper",
                            "published_date": "2026-01-20",
                        },
                        {
                            "title": "B duplicate",
                            "url": "https://example.com/b",
                            "provider": "serper",
                            "published_date": "2026-01-20",
                        },
                    ],
                },
                {
                    "query": "q2",
                    "results": [
                        {"title": "C", "url": "https://example.com/c"},
                        {"title": "D", "url": "https://example.com/d"},
                        {"title": "E", "url": "https://example.com/e"},
                        {"title": "F", "url": "https://example.com/f"},
                    ],
                },
            ],
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    complete_events = [data for name, data in emitted if name == "research_node_complete"]
    assert complete_events

    sources = complete_events[0].get("sources", [])
    urls = [src.get("url") for src in sources]
    assert len(sources) <= 5
    assert len(urls) == len(set(urls))
    assert "https://example.com/a" in urls


def test_deepsearch_node_skips_wrapper_events_when_runner_marks_emitted(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.9},
            "_deepsearch_events_emitted": True,
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    event_types = [name for name, _ in emitted]
    assert event_types == ["research_node_start"]


def test_deepsearch_node_emits_completion_for_cancelled_result_even_with_marker(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "is_cancelled": True,
            "final_report": "cancelled",
            "_deepsearch_events_emitted": True,
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    event_types = [name for name, _ in emitted]
    assert "research_node_complete" in event_types


def test_deepsearch_node_reraises_graph_interrupt(monkeypatch):
    def fake_auto(state, config):
        raise GraphInterrupt((Interrupt(value={"checkpoint": "deepsearch_clarify"}),))

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)

    with pytest.raises(GraphInterrupt):
        nodes.deepsearch_node(
            {"input": "test topic"},
            {"configurable": {"thread_id": "thread_test"}},
        )
