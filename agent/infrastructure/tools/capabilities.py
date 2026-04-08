from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from agent.infrastructure.tools.providers import ProviderContext, StaticToolProvider
from agent.infrastructure.tools.runtime_context import (
    ToolRuntimeContext,
    build_tool_runtime_context,
)
from common.config import settings
from tools import execute_python_code, web_search
from tools.automation.ask_human_tool import ask_human
from tools.automation.bash_tool import safe_bash
from tools.automation.computer_use_tool import build_computer_use_tools
from tools.automation.str_replace_tool import str_replace
from tools.automation.task_list_tool import build_task_list_tools
from tools.browser.browser_tools import build_browser_tools
from tools.browser.browser_use_tool import build_browser_use_tools
from tools.code.chart_viz_tool import chart_visualize
from tools.crawl.crawl4ai_tool import crawl4ai
from tools.crawl.crawl_tools import build_crawl_tools
from tools.mcp import get_live_mcp_tools
from tools.planning.planning_tool import plan_steps
from tools.sandbox import (
    build_image_edit_tools,
    build_presentation_outline_tools,
    build_presentation_v2_tools,
    build_sandbox_browser_tools,
    build_sandbox_files_tools,
    build_sandbox_presentation_tools,
    build_sandbox_sheets_tools,
    build_sandbox_shell_tools,
    build_sandbox_vision_tools,
    build_sandbox_web_dev_tools,
    build_sandbox_web_search_tools,
)

logger = logging.getLogger(__name__)

_E2B_PLACEHOLDER_KEYS = {
    "e2b_...",
    "e2b_39ce8c3d299470afd09b42629c436edec32728d8",
}


def _e2b_api_key_configured() -> bool:
    key = (settings.e2b_api_key or "").strip()
    if not key:
        return False
    if key in _E2B_PLACEHOLDER_KEYS:
        return False
    if not key.startswith("e2b_"):
        return False
    return True


def _configurable(config: RunnableConfig) -> dict[str, Any]:
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        if isinstance(cfg, dict):
            return cfg
    return {}
@dataclass(frozen=True)
class ToolBuildContext:
    config: RunnableConfig
    configurable: dict[str, Any]
    profile: dict[str, Any]
    thread_id: str
    e2b_ready: bool
    runtime: ToolRuntimeContext


ToolFactory = Callable[[ToolBuildContext], list[BaseTool]]


@dataclass(frozen=True)
class ToolProviderSpec:
    key: str
    factory: ToolFactory


def _build_web_search_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return [web_search]


def _build_rag_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    if not bool(getattr(settings, "rag_enabled", False)):
        return []
    try:
        from tools.rag.rag_tool import rag_search

        return [rag_search]
    except Exception as exc:  # pragma: no cover
        logger.warning(f"Failed to load rag_search tool: {exc}")
        return []


def _build_crawl_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return [*build_crawl_tools(), crawl4ai]


def _build_browser_tools(ctx: ToolBuildContext) -> list[BaseTool]:
    return build_browser_tools(ctx.thread_id)


def _build_sandbox_browser_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_browser_tools(ctx.thread_id)
    return []


def _build_browser_use_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if not bool(settings.enable_browser_use):
        return []
    return build_browser_use_tools(ctx.thread_id)


def _build_sandbox_web_search_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_web_search_tools(ctx.thread_id)
    return []


def _build_sandbox_files_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_files_tools(ctx.thread_id)
    return []


def _build_sandbox_shell_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_shell_tools(ctx.thread_id)
    return []


def _build_sandbox_sheets_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_sheets_tools(ctx.thread_id)
    return []


def _build_sandbox_presentation_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_presentation_tools(ctx.thread_id)
    return []


def _build_sandbox_vision_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_vision_tools(ctx.thread_id)
    return []


def _build_image_edit_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_image_edit_tools(ctx.thread_id)
    return []


def _build_sandbox_web_dev_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_web_dev_tools(ctx.thread_id)
    return []


def _build_presentation_outline_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_presentation_outline_tools(ctx.thread_id)
    return []


def _build_presentation_v2_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_presentation_v2_tools(ctx.thread_id)
    return []


def _build_python_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return [execute_python_code, chart_visualize]


def _build_task_tools(ctx: ToolBuildContext) -> list[BaseTool]:
    return build_task_list_tools(ctx.thread_id)


def _build_computer_use_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    return list(build_computer_use_tools(ctx.thread_id) or [])


def _build_ask_human_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return [ask_human]


def _build_str_replace_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return [str_replace]


def _build_bash_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return [safe_bash]


def _build_planning_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return [plan_steps]


def _build_mcp_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    return list(get_live_mcp_tools())


def _build_daytona_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode != "daytona":
        return []
    from tools.sandbox import daytona_create, daytona_stop

    return [daytona_create, daytona_stop]


TOOL_PROVIDER_SPECS: tuple[ToolProviderSpec, ...] = (
    ToolProviderSpec(key="web_search", factory=_build_web_search_tools),
    ToolProviderSpec(key="rag", factory=_build_rag_tools),
    ToolProviderSpec(key="crawl", factory=_build_crawl_tools),
    ToolProviderSpec(key="sandbox_browser", factory=_build_sandbox_browser_tools_for_agent),
    ToolProviderSpec(key="browser", factory=_build_browser_tools),
    ToolProviderSpec(key="browser_use", factory=_build_browser_use_tools_for_agent),
    ToolProviderSpec(key="sandbox_web_search", factory=_build_sandbox_web_search_tools_for_agent),
    ToolProviderSpec(key="sandbox_files", factory=_build_sandbox_files_tools_for_agent),
    ToolProviderSpec(key="sandbox_shell", factory=_build_sandbox_shell_tools_for_agent),
    ToolProviderSpec(key="sandbox_sheets", factory=_build_sandbox_sheets_tools_for_agent),
    ToolProviderSpec(key="sandbox_presentation", factory=_build_sandbox_presentation_tools_for_agent),
    ToolProviderSpec(key="sandbox_vision", factory=_build_sandbox_vision_tools_for_agent),
    ToolProviderSpec(key="sandbox_image_edit", factory=_build_image_edit_tools_for_agent),
    ToolProviderSpec(key="sandbox_web_dev", factory=_build_sandbox_web_dev_tools_for_agent),
    ToolProviderSpec(key="presentation_outline", factory=_build_presentation_outline_tools_for_agent),
    ToolProviderSpec(key="presentation_v2", factory=_build_presentation_v2_tools_for_agent),
    ToolProviderSpec(key="python", factory=_build_python_tools),
    ToolProviderSpec(key="task_list", factory=_build_task_tools),
    ToolProviderSpec(key="computer_use", factory=_build_computer_use_tools_for_agent),
    ToolProviderSpec(key="ask_human", factory=_build_ask_human_tools),
    ToolProviderSpec(key="str_replace", factory=_build_str_replace_tools),
    ToolProviderSpec(key="bash", factory=_build_bash_tools),
    ToolProviderSpec(key="planning", factory=_build_planning_tools),
    ToolProviderSpec(key="mcp", factory=_build_mcp_tools),
    ToolProviderSpec(key="sandbox_daytona", factory=_build_daytona_tools),
)


def build_tool_context(config: RunnableConfig) -> ToolBuildContext:
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}
    e2b_ready = _e2b_api_key_configured()
    return ToolBuildContext(
        config=config,
        configurable=configurable,
        profile=profile,
        thread_id=str(configurable.get("thread_id") or "default"),
        e2b_ready=e2b_ready,
        runtime=build_tool_runtime_context(config, e2b_ready=e2b_ready),
    )


def _provider_context_from_tool_context(context: ToolBuildContext) -> ProviderContext:
    return ProviderContext(
        thread_id=context.thread_id,
        profile=dict(context.profile),
        configurable=dict(context.configurable),
        e2b_ready=context.e2b_ready,
        runtime=context.runtime,
    )


def _tool_context_from_provider_context(context: ProviderContext) -> ToolBuildContext:
    return ToolBuildContext(
        config={"configurable": dict(context.configurable)},
        configurable=dict(context.configurable),
        profile=dict(context.profile),
        thread_id=context.thread_id,
        e2b_ready=context.e2b_ready,
        runtime=context.runtime,
    )


def build_default_tool_providers() -> tuple[StaticToolProvider, ...]:
    providers: list[StaticToolProvider] = []
    for spec in TOOL_PROVIDER_SPECS:
        providers.append(
            StaticToolProvider(
                key=spec.key,
                factory=lambda provider_context, current_spec=spec: current_spec.factory(
                    _tool_context_from_provider_context(provider_context)
                ),
            )
        )
    return tuple(providers)


__all__ = [
    "TOOL_PROVIDER_SPECS",
    "ToolBuildContext",
    "ToolFactory",
    "ToolProviderSpec",
    "build_default_tool_providers",
    "build_tool_context",
]
