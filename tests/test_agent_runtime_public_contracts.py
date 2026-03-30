from agent.contracts.events import ToolEventType
from agent.contracts.research import ClaimVerifier, extract_message_sources
from agent.contracts.search_cache import get_search_cache as get_public_search_cache
from agent.contracts.source_registry import SourceRegistry
from agent.contracts.worker_context import get_worker_context_store
from agent.core.search_cache import get_search_cache as get_core_search_cache
from agent.runtime.deep import selector
from agent.runtime.nodes import deepsearch_node, route_node
from agent.workflows.nodes import deepsearch_node as legacy_deepsearch_node
from agent.workflows.nodes import route_node as legacy_route_node


def test_runtime_node_entrypoints_match_legacy_exports():
    assert route_node is legacy_route_node
    assert deepsearch_node is legacy_deepsearch_node


def test_public_search_cache_contract_uses_core_singleton():
    assert get_public_search_cache() is get_core_search_cache()


def test_public_contracts_are_importable():
    assert ToolEventType.SEARCH.value == "search"
    assert isinstance(SourceRegistry(), SourceRegistry)
    assert isinstance(ClaimVerifier(), ClaimVerifier)
    assert get_worker_context_store() is not None
    assert extract_message_sources([]) == []


def test_runtime_selector_dispatches_multi_agent(monkeypatch):
    monkeypatch.setattr(selector._legacy_runtime, "_resolve_deepsearch_engine", lambda _config: "multi_agent")
    monkeypatch.setattr(
        selector,
        "run_multi_agent_deepsearch",
        lambda _state, _config: {"engine": "multi_agent", "is_cancelled": False},
    )

    result = selector.run_deepsearch_auto({"input": "AI chips"}, {"configurable": {}})

    assert result["engine"] == "multi_agent"
    assert result["_deepsearch_events_emitted"] is True


def test_runtime_selector_dispatches_legacy_linear(monkeypatch):
    monkeypatch.setattr(selector._legacy_runtime, "_resolve_deepsearch_engine", lambda _config: "legacy")
    monkeypatch.setattr(selector._legacy_runtime, "_resolve_deepsearch_mode", lambda _config: "linear")
    monkeypatch.setattr(
        selector._legacy_runtime,
        "run_deepsearch_optimized",
        lambda _state, _config: {"engine": "legacy-linear", "is_cancelled": False},
    )

    result = selector.run_deepsearch_auto({"input": "AI chips"}, {"configurable": {}})

    assert result["engine"] == "legacy-linear"
    assert result["_deepsearch_events_emitted"] is True
