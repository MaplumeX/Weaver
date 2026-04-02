"""
Structured runtime entrypoints for agent execution internals.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

__all__ = [
    "agent_node",
    "check_cancellation",
    "clarify_node",
    "compressor_node",
    "create_research_graph",
    "coordinator_node",
    "deepsearch_node",
    "evaluator_node",
    "handle_cancellation",
    "hitl_draft_review_node",
    "hitl_plan_review_node",
    "hitl_sources_review_node",
    "human_review_node",
    "initialize_enhanced_tools",
    "initiate_research",
    "perform_parallel_search",
    "planner_node",
    "refine_plan_node",
    "revise_report_node",
    "route_node",
    "run_deepsearch_auto",
    "run_deepsearch_runtime",
    "run_multi_agent_deepsearch",
    "writer_node",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    "agent_node": "agent.runtime.nodes",
    "check_cancellation": "agent.runtime.nodes",
    "clarify_node": "agent.runtime.nodes",
    "compressor_node": "agent.runtime.nodes",
    "create_research_graph": "agent.runtime.graph",
    "coordinator_node": "agent.runtime.nodes",
    "deepsearch_node": "agent.runtime.nodes",
    "evaluator_node": "agent.runtime.nodes",
    "handle_cancellation": "agent.runtime.nodes",
    "hitl_draft_review_node": "agent.runtime.nodes",
    "hitl_plan_review_node": "agent.runtime.nodes",
    "hitl_sources_review_node": "agent.runtime.nodes",
    "human_review_node": "agent.runtime.nodes",
    "initialize_enhanced_tools": "agent.runtime.nodes",
    "initiate_research": "agent.runtime.nodes",
    "perform_parallel_search": "agent.runtime.nodes",
    "planner_node": "agent.runtime.nodes",
    "refine_plan_node": "agent.runtime.nodes",
    "revise_report_node": "agent.runtime.nodes",
    "route_node": "agent.runtime.nodes",
    "run_deepsearch_auto": "agent.runtime.deep",
    "run_deepsearch_runtime": "agent.runtime.deep",
    "run_multi_agent_deepsearch": "agent.runtime.deep",
    "writer_node": "agent.runtime.nodes",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
