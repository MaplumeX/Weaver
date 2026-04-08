from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from agent.infrastructure.tools.capabilities import (
    build_default_tool_providers,
    build_tool_context,
)
from agent.infrastructure.tools.policy import filter_tools_by_name, resolve_profile_tool_policy
from agent.infrastructure.tools.providers import ProviderContext, compose_provider_tools
from agent.infrastructure.tools.registry import build_tool_registry
from common.config import settings
from tools.core.wrappers import wrap_tools_with_events
from tools.mcp import get_live_mcp_tools


def _configurable(config: RunnableConfig) -> dict[str, Any]:
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        if isinstance(cfg, dict):
            return cfg
    return {}


def _provider_context(config: RunnableConfig) -> ProviderContext:
    context = build_tool_context(config)
    return ProviderContext(
        thread_id=context.thread_id,
        profile=context.profile,
        configurable=context.configurable,
        e2b_ready=context.e2b_ready,
        runtime=context.runtime,
    )


def build_tool_inventory(config: RunnableConfig) -> list[BaseTool]:
    return compose_provider_tools(build_default_tool_providers(), _provider_context(config))


def build_tools_for_names(
    names: set[str],
    config: RunnableConfig | None = None,
) -> list[BaseTool]:
    wanted = {str(name).strip() for name in names if str(name).strip()}
    if not wanted:
        return []
    inventory = build_tool_inventory(config or {"configurable": {"thread_id": "default", "agent_profile": {}}})
    return [tool for tool in inventory if getattr(tool, "name", "") in wanted]


def build_agent_toolset(config: RunnableConfig) -> list[BaseTool]:
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    thread_id = str(configurable.get("thread_id") or "default")
    tool_list = build_tool_inventory(config)
    resolution = resolve_profile_tool_policy(
        build_tool_registry(config),
        profile=profile,
    )
    allowed = list(resolution.allowed_tool_names)
    metadata = profile.get("metadata") or {}
    if allowed and isinstance(metadata, dict) and bool(metadata.get("protected")):
        allowed.extend(
            [
                str(getattr(tool, "name", "")).strip()
                for tool in get_live_mcp_tools()
                if str(getattr(tool, "name", "")).strip()
            ]
        )
    tool_list = filter_tools_by_name(
        tool_list,
        allowed=allowed,
        blocked=resolution.blocked_tool_names,
    )

    emit_events = bool(profile.get("emit_tool_events", settings.emit_tool_events))
    if emit_events:
        tool_list = wrap_tools_with_events(tool_list, thread_id=thread_id)

    return tool_list
