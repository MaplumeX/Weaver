import pytest

from agent.contracts.events import ToolEventType
from agent.contracts.research import ClaimVerifier, extract_message_sources
from agent.contracts.search_cache import get_search_cache as get_public_search_cache
from agent.contracts.source_registry import SourceRegistry
from agent.contracts.worker_context import get_worker_context_store
from agent.core.search_cache import get_search_cache as get_core_search_cache
from agent.compat.nodes import deepsearch_node as compat_deepsearch_node
from agent.compat.nodes import route_node as compat_route_node
from agent.runtime.deep import entrypoints
from agent.runtime.nodes import deepsearch_node, route_node


def test_runtime_node_entrypoints_match_compat_exports():
    assert route_node is compat_route_node
    assert deepsearch_node is compat_deepsearch_node


def test_public_search_cache_contract_uses_core_singleton():
    assert get_public_search_cache() is get_core_search_cache()


def test_public_contracts_are_importable():
    assert ToolEventType.SEARCH.value == "search"
    assert isinstance(SourceRegistry(), SourceRegistry)
    assert isinstance(ClaimVerifier(), ClaimVerifier)
    assert get_worker_context_store() is not None
    assert extract_message_sources([]) == []


def test_runtime_entrypoint_dispatches_multi_agent(monkeypatch):
    monkeypatch.setattr(
        entrypoints,
        "_run_deepsearch_runtime",
        lambda _state, _config: {"engine": "multi_agent", "is_cancelled": False},
    )

    result = entrypoints.run_deepsearch_auto({"input": "AI chips"}, {"configurable": {}})

    assert result["engine"] == "multi_agent"
    assert result["_deepsearch_events_emitted"] is True


def test_runtime_entrypoint_rejects_legacy_engine_override():
    with pytest.raises(ValueError, match="removed on 2026-04-01"):
        entrypoints.run_deepsearch_auto(
            {"input": "AI chips"},
            {"configurable": {"deepsearch_engine": "legacy"}},
        )
