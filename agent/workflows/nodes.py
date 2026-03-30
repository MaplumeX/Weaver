from __future__ import annotations

import agent.contracts.events as _events
import agent.contracts.search_cache as _search_cache_contracts
import agent.runtime.nodes._shared as _shared
import agent.workflows.agent_factory as _agent_factory
import agent.workflows.agent_tools as _agent_tools
import agent.workflows.deepsearch_optimized as _deepsearch_optimized
import agent.workflows.stuck_middleware as _stuck_middleware
from agent.runtime.nodes.answer import (
    agent_node,
    direct_answer_node,
    writer_node,
)
from agent.runtime.nodes.deepsearch import (
    coordinator_node,
    deepsearch_node,
)
from agent.runtime.nodes.planning import (
    compressor_node,
    initiate_research,
    perform_parallel_search,
    planner_node,
    refine_plan_node,
    web_search_plan_node,
)
from agent.runtime.nodes.review import (
    _format_sources_snapshot_for_instruction,
    _hitl_checkpoint_active,
    _hitl_checkpoints_enabled,
    _parse_research_plan_content,
    evaluator_node,
    hitl_draft_review_node,
    hitl_plan_review_node,
    hitl_sources_review_node,
    human_review_node,
    revise_report_node,
    should_continue_research,
)
from agent.runtime.nodes.routing import clarify_node, route_node

ENHANCED_TOOLS_AVAILABLE = _shared.ENHANCED_TOOLS_AVAILABLE
ToolEventType = _events.ToolEventType
get_emitter_sync = _events.get_emitter_sync
QueryDeduplicator = _search_cache_contracts.QueryDeduplicator
_answer_simple_agent_query = _shared._answer_simple_agent_query
_apply_output_contract = _shared._apply_output_contract
_auto_mode_prefers_linear = _shared._auto_mode_prefers_linear
_build_compact_unique_source_preview = _shared._build_compact_unique_source_preview
_build_fast_agent_search_query = _shared._build_fast_agent_search_query
_build_user_content = _shared._build_user_content
_chat_model = _shared._chat_model
_configurable = _shared._configurable
_event_results_limit = _shared._event_results_limit
_extract_exact_reply_target = _shared._extract_exact_reply_target
_extract_tool_call_fields = _shared._extract_tool_call_fields
_format_fast_search_results = _shared._format_fast_search_results
_get_writer_tools = _shared._get_writer_tools
_guess_mime = _shared._guess_mime
_is_narrow_comparison_prompt = _shared._is_narrow_comparison_prompt
_is_tool_enabled = _shared._is_tool_enabled
_log_usage = _shared._log_usage
_model_for_task = _shared._model_for_task
_normalize_images = _shared._normalize_images
_run_fast_agent_search = _shared._run_fast_agent_search
_selected_model = _shared._selected_model
_selected_reasoning_model = _shared._selected_reasoning_model
_should_use_fast_agent_path = _shared._should_use_fast_agent_path
check_cancellation = _shared.check_cancellation
handle_cancellation = _shared.handle_cancellation
initialize_enhanced_tools = _shared.initialize_enhanced_tools
logger = _shared.logger
settings = _shared.settings
build_tool_agent = _agent_factory.build_tool_agent
build_writer_agent = _agent_factory.build_writer_agent
build_agent_tools = _agent_tools.build_agent_tools
run_deepsearch_auto = _deepsearch_optimized.run_deepsearch_auto
detect_stuck = _stuck_middleware.detect_stuck
inject_stuck_hint = _stuck_middleware.inject_stuck_hint


__all__ = [
    "ENHANCED_TOOLS_AVAILABLE",
    "QueryDeduplicator",
    "ToolEventType",
    "_answer_simple_agent_query",
    "_apply_output_contract",
    "_auto_mode_prefers_linear",
    "_build_compact_unique_source_preview",
    "_build_fast_agent_search_query",
    "_build_user_content",
    "_chat_model",
    "_configurable",
    "_event_results_limit",
    "_extract_exact_reply_target",
    "_extract_tool_call_fields",
    "_format_fast_search_results",
    "_format_sources_snapshot_for_instruction",
    "_get_writer_tools",
    "_guess_mime",
    "_hitl_checkpoint_active",
    "_hitl_checkpoints_enabled",
    "_is_narrow_comparison_prompt",
    "_is_tool_enabled",
    "_log_usage",
    "_model_for_task",
    "_normalize_images",
    "_parse_research_plan_content",
    "_run_fast_agent_search",
    "_selected_model",
    "_selected_reasoning_model",
    "_should_use_fast_agent_path",
    "agent_node",
    "build_agent_tools",
    "build_tool_agent",
    "build_writer_agent",
    "check_cancellation",
    "clarify_node",
    "compressor_node",
    "coordinator_node",
    "deepsearch_node",
    "detect_stuck",
    "direct_answer_node",
    "evaluator_node",
    "get_emitter_sync",
    "handle_cancellation",
    "hitl_draft_review_node",
    "hitl_plan_review_node",
    "hitl_sources_review_node",
    "human_review_node",
    "initialize_enhanced_tools",
    "initiate_research",
    "inject_stuck_hint",
    "logger",
    "perform_parallel_search",
    "planner_node",
    "refine_plan_node",
    "revise_report_node",
    "route_node",
    "run_deepsearch_auto",
    "settings",
    "should_continue_research",
    "web_search_plan_node",
    "writer_node",
]
