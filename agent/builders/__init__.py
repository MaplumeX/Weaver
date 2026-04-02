"""Builder-owned helpers for agent construction and tool wiring."""

from agent.builders.agent_factory import (
    build_deep_research_tool_agent,
    build_tool_agent,
    build_writer_agent,
    resolve_deep_research_role_tool_names,
)
from agent.builders.agent_tools import build_agent_tools
from agent.builders.provider_safe_middleware import ProviderSafeToolSelectorMiddleware
from agent.builders.stuck_middleware import detect_stuck, inject_stuck_hint

__all__ = [
    "ProviderSafeToolSelectorMiddleware",
    "build_agent_tools",
    "build_deep_research_tool_agent",
    "build_tool_agent",
    "build_writer_agent",
    "detect_stuck",
    "inject_stuck_hint",
    "resolve_deep_research_role_tool_names",
]
