"""LLM agent factory implementations used by the runtime."""

from agent.infrastructure.agents.factory import (
    DEEP_RESEARCH_CONTROL_PLANE_ROLES,
    DEEP_RESEARCH_EXECUTION_ROLES,
    _build_middlewares,
    _build_todo_middleware,
    _tool_selector_always_include,
    _tool_selector_methods,
    build_deep_research_tool_agent,
    build_tool_agent,
    build_writer_agent,
    classify_deep_research_role,
    resolve_deep_research_role_tool_names,
)
from agent.infrastructure.agents.provider_safe_middleware import ProviderSafeToolSelectorMiddleware
from agent.infrastructure.agents.stuck_middleware import detect_stuck, inject_stuck_hint

__all__ = [
    "DEEP_RESEARCH_CONTROL_PLANE_ROLES",
    "DEEP_RESEARCH_EXECUTION_ROLES",
    "ProviderSafeToolSelectorMiddleware",
    "_build_middlewares",
    "_build_todo_middleware",
    "_tool_selector_always_include",
    "_tool_selector_methods",
    "build_deep_research_tool_agent",
    "build_tool_agent",
    "build_writer_agent",
    "classify_deep_research_role",
    "detect_stuck",
    "inject_stuck_hint",
    "resolve_deep_research_role_tool_names",
]
