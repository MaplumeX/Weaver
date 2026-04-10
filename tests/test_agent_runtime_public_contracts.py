import importlib

import pytest

import agent.core as core_pkg
import agent.domain as domain_pkg
import agent.infrastructure.agents as agents_pkg
import agent.prompts as prompts_pkg
import agent.research as research_pkg
import agent.runtime as runtime_pkg
import agent.runtime.deep.researcher_runtime as deep_researcher_runtime_pkg
import agent.runtime.deep.roles as deep_roles_pkg
import agent.runtime.deep.support as deep_support_pkg
import agent.runtime.nodes as runtime_nodes
from agent.contracts.events import ToolEventType
from agent.contracts.research import ClaimVerifier, extract_message_sources
from agent.contracts.search_cache import get_search_cache as get_public_search_cache
from agent.contracts.source_registry import SourceRegistry
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
        "human_review_node",
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
            getattr(runtime_nodes, name)
        with pytest.raises(AttributeError):
            getattr(runtime_pkg, name)


def test_runtime_active_entrypoints_remain_importable():
    removed_symbol = "initialize" + "_enhanced_tools"
    assert callable(runtime_nodes.route_node)
    assert callable(runtime_nodes.chat_respond_node)
    assert callable(runtime_nodes.deep_research_node)
    assert callable(runtime_nodes.finalize_answer_node)
    assert callable(runtime_nodes.tool_agent_node)
    assert not hasattr(runtime_nodes, removed_symbol)


def test_legacy_agent_node_is_no_longer_exported():
    assert "agent_node" not in runtime_nodes.__all__
    assert "agent_node" not in runtime_pkg.__all__
    with pytest.raises(AttributeError):
        _ = runtime_nodes.agent_node
    with pytest.raises(AttributeError):
        _ = runtime_pkg.agent_node


def test_legacy_core_config_export_is_no_longer_exposed():
    assert "AgentProcessorConfig" not in core_pkg.__all__
    with pytest.raises(AttributeError):
        _ = core_pkg.AgentProcessorConfig


def test_removed_core_reserve_exports_are_no_longer_exposed():
    for name in {
        "enforce_tool_call_limit",
        "retry_call",
    }:
        assert name not in core_pkg.__all__
        with pytest.raises(AttributeError):
            getattr(core_pkg, name)


def test_legacy_xml_parser_module_is_no_longer_importable():
    assert importlib.util.find_spec("agent.parsers.xml_parser") is None


def test_removed_research_helper_modules_are_no_longer_importable():
    removed = {
        "agent.contracts.result_aggregator",
        "agent.contracts.worker_context",
        "agent.core.context",
        "agent.research.browser_visualizer",
        "agent.research.compressor",
        "agent.research.parsing_utils",
        "agent.research.quality_assessor",
        "agent.research.query_strategy",
        "agent.research.viz_planner",
    }

    for name in removed:
        assert importlib.util.find_spec(name) is None


def test_removed_research_helpers_are_no_longer_exported():
    removed = {
        "ChartSpec",
        "ChartType",
        "ClaimVerification",
        "CompressedKnowledge",
        "DomainClassification",
        "ExtractedFact",
        "GeneratedChart",
        "QualityAssessor",
        "QualityReport",
        "ResearchCompressor",
        "VizPlanner",
        "analyze_query_coverage",
        "backfill_diverse_queries",
        "classify_domain",
        "embed_charts_in_report",
        "extract_response_content",
        "format_search_results",
        "is_time_sensitive_topic",
        "parse_json_from_text",
        "parse_list_output",
        "query_dimensions",
        "show_browser_status_page",
        "visualize_urls",
        "visualize_urls_from_results",
    }

    for name in removed:
        assert name not in research_pkg.__all__
        assert not hasattr(research_pkg, name)


def test_removed_worker_context_contracts_are_no_longer_exported():
    removed = {
        "ResearchWorkerContext",
        "SubAgentContext",
        "WorkerContextStore",
        "build_research_worker_context",
        "get_worker_context_store",
        "merge_research_worker_context",
    }

    import agent.contracts as contracts_pkg

    for name in removed:
        assert name not in contracts_pkg.__all__
        assert not hasattr(contracts_pkg, name)


def test_removed_research_contract_helpers_are_no_longer_exported():
    import agent.contracts as contracts_pkg
    import agent.contracts.research as research_contracts_pkg

    assert "ResultAggregator" not in contracts_pkg.__all__
    assert not hasattr(contracts_pkg, "ResultAggregator")
    assert "ResultAggregator" not in research_contracts_pkg.__all__
    assert not hasattr(research_contracts_pkg, "ResultAggregator")


def test_removed_domain_slice_helpers_are_no_longer_exported():
    removed = {
        "build_state_slices",
        "public_mode_for_execution",
    }

    for name in removed:
        assert name not in domain_pkg.__all__
        assert not hasattr(domain_pkg, name)


def test_removed_agent_factory_reserve_exports_are_no_longer_exposed():
    removed = {
        "build_writer_agent",
        "classify_deep_research_role",
    }

    for name in removed:
        assert name not in agents_pkg.__all__
        assert not hasattr(agents_pkg, name)


def test_removed_deep_support_reserve_exports_are_no_longer_exposed():
    assert "restore_agent_runs" not in deep_support_pkg.__all__
    assert not hasattr(deep_support_pkg, "restore_agent_runs")


def test_removed_deep_roles_reserve_exports_are_no_longer_exposed():
    for name in {
        "ResearchPlanner",
        "SupervisorAction",
        "SupervisorDecision",
    }:
        assert name not in deep_roles_pkg.__all__
        assert not hasattr(deep_roles_pkg, name)


def test_removed_deep_role_planner_module_is_no_longer_importable():
    assert importlib.util.find_spec("agent.runtime.deep.roles.planner") is None


def test_removed_deep_runtime_shared_module_is_no_longer_importable():
    assert importlib.util.find_spec("agent.runtime.deep.shared") is None


def test_removed_deep_schema_control_plane_helpers_are_no_longer_exposed():
    import agent.runtime.deep.schema as deep_schema_pkg

    for name in {
        "REGISTERED_CONTROL_PLANE_AGENTS",
        "ControlPlaneAgent",
        "is_control_plane_agent",
        "validate_control_plane_agent",
    }:
        assert name not in deep_schema_pkg.__all__
        assert not hasattr(deep_schema_pkg, name)


def test_removed_researcher_runtime_reserve_exports_are_no_longer_exposed():
    for name in {
        "BranchContradictionSummary",
        "BranchCoverageSummary",
        "BranchDecision",
        "BranchGroundingSummary",
        "BranchQualitySummary",
        "BranchQueryPlan",
        "BranchResearchState",
    }:
        assert name not in deep_researcher_runtime_pkg.__all__
        assert not hasattr(deep_researcher_runtime_pkg, name)

    assert hasattr(deep_researcher_runtime_pkg, "BranchResearchRunner")


def test_removed_prompt_manager_reserve_exports_are_no_longer_exposed():
    removed = {
        "PromptManager",
        "PromptRegistry",
        "get_agent_prompt",
        "get_deep_research_prompt",
        "get_prompt_manager",
        "get_prompt_registry",
        "get_writer_prompt",
        "reset_prompt_manager",
        "set_prompt_manager",
    }

    for name in removed:
        assert name not in prompts_pkg.__all__
        assert not hasattr(prompts_pkg, name)


def test_removed_reserve_class_methods_are_no_longer_exposed():
    from agent.core.events import EventEmitter
    from agent.core.smart_router import SmartRouter
    from agent.prompts.prompt_manager import PromptManager

    for name in {
        "get_agent_prompt",
        "get_deep_research_prompt",
        "get_direct_answer_prompt",
        "get_planner_prompt",
        "get_writer_prompt",
        "load_custom_prompt",
        "set_custom_prompt",
    }:
        assert not hasattr(PromptManager, name)
    for name in {
        "clear_buffer",
        "emit_content",
        "emit_deep_research_topology_update",
        "emit_done",
        "emit_error",
        "emit_quality_update",
        "emit_research_agent_complete",
        "emit_research_agent_start",
        "emit_research_artifact_update",
        "emit_research_decision",
        "emit_research_node_complete",
        "emit_research_node_start",
        "emit_research_task_update",
        "emit_screenshot",
        "emit_search",
        "emit_task_update",
        "emit_tool_result",
        "emit_tool_start",
    }:
        assert not hasattr(EventEmitter, name)
    assert not hasattr(SmartRouter, "detect_tool_requirements")


def test_public_search_cache_contract_uses_core_singleton():
    assert get_public_search_cache() is get_core_search_cache()


def test_public_contracts_are_importable():
    assert ToolEventType.SEARCH.value == "search"
    assert isinstance(SourceRegistry(), SourceRegistry)
    assert isinstance(ClaimVerifier(), ClaimVerifier)
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
