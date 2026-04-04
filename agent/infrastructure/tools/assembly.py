from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from agent.infrastructure.tools.capabilities import build_default_tool_registry
from common.config import settings
from tools.core.wrappers import wrap_tools_with_events


def _configurable(config: RunnableConfig) -> dict[str, Any]:
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        if isinstance(cfg, dict):
            return cfg
    return {}


def build_agent_toolset(config: RunnableConfig) -> list[BaseTool]:
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    thread_id = str(configurable.get("thread_id") or "default")
    tool_list = build_default_tool_registry().build_tools(config)

    emit_events = bool(profile.get("emit_tool_events", settings.emit_tool_events))
    if emit_events:
        tool_list = wrap_tools_with_events(tool_list, thread_id=thread_id)

    return tool_list

