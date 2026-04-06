import pytest

import agent.runtime as runtime_pkg
import agent.runtime.nodes as runtime_nodes
from agent.contracts.events import ToolEventType
from agent.contracts.research import ClaimVerifier, extract_message_sources
from agent.contracts.search_cache import get_search_cache as get_public_search_cache
from agent.contracts.source_registry import SourceRegistry
from agent.contracts.worker_context import get_worker_context_store
from agent.core.search_cache import get_search_cache as get_core_search_cache
from agent.runtime.deep import entrypoints
from agent.runtime.nodes import deep_research_node, route_node


def test_runtime_node_entrypoints_are_importable():
    assert callable(route_node)
    assert callable(deep_research_node)


def test_removed_outer_runtime_nodes_are_not_exported():
    removed = {
        "clarify_node",
        "compressor_node",
        "evaluator_node",
        "hitl_draft_review_node",
        "hitl_plan_review_node",
        "hitl_sources_review_node",
        "initiate_research",
        "perform_parallel_search",
        "planner_node",
        "refine_plan_node",
        "revise_report_node",
        "writer_node",
    }

    for name in removed:
        assert name not in runtime_nodes.__all__
        assert name not in runtime_pkg.__all__
        with pytest.raises(AttributeError):
            getattr(runtime_pkg, name)


def test_runtime_active_entrypoints_remain_importable():
    assert callable(runtime_nodes.route_node)
    assert callable(runtime_nodes.chat_respond_node)
    assert callable(runtime_nodes.deep_research_node)
    assert callable(runtime_nodes.finalize_answer_node)
    assert callable(runtime_nodes.human_review_node)
    assert callable(runtime_nodes.tool_agent_node)


def test_legacy_agent_node_is_no_longer_exported():
    assert "agent_node" not in runtime_nodes.__all__
    assert "agent_node" not in runtime_pkg.__all__
    with pytest.raises(AttributeError):
        getattr(runtime_nodes, "agent_node")
    with pytest.raises(AttributeError):
        getattr(runtime_pkg, "agent_node")


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
        "_run_multi_agent_deep_research",
        lambda _state, _config: {"engine": "multi_agent", "is_cancelled": False},
    )

    result = entrypoints.run_deep_research({"input": "AI chips"}, {"configurable": {}})

    assert result["engine"] == "multi_agent"
    assert result["_deep_research_events_emitted"] is True


def test_runtime_entrypoint_rejects_legacy_engine_override():
    with pytest.raises(ValueError, match="removed on 2026-04-01"):
        entrypoints.run_deep_research(
            {"input": "AI chips"},
            {"configurable": {"deepsearch_engine": "legacy"}},
        )
