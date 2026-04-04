from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from agent.domain import ToolCapability
from common.config import settings
from tools import execute_python_code, tavily_search
from tools.automation.ask_human_tool import ask_human
from tools.automation.bash_tool import safe_bash
from tools.automation.computer_use_tool import build_computer_use_tools
from tools.automation.str_replace_tool import str_replace
from tools.automation.task_list_tool import build_task_list_tools
from tools.browser.browser_tools import build_browser_tools
from tools.browser.browser_use_tool import build_browser_use_tools
from tools.code.chart_viz_tool import chart_visualize
from tools.core.registry import get_registered_tools
from tools.crawl.crawl4ai_tool import crawl4ai
from tools.crawl.crawl_tools import build_crawl_tools
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

_CAPABILITY_TOOL_NAME_ALIASES: dict[str, frozenset[str]] = {
    ToolCapability.SEARCH.value: frozenset(
        {
            "browser_search",
            "fallback_search",
            "multi_search",
            "sandbox_extract_search_results",
            "sandbox_search_and_click",
            "sandbox_web_search",
            "tavily_search",
        }
    ),
    ToolCapability.BROWSE.value: frozenset(
        {
            "browser_click",
            "browser_navigate",
            "sb_browser_click",
            "sb_browser_extract_text",
            "sb_browser_navigate",
            "sb_browser_press",
            "sb_browser_scroll",
            "sb_browser_screenshot",
            "sb_browser_type",
        }
    ),
    ToolCapability.READ.value: frozenset(
        {
            "browser_click",
            "browser_navigate",
            "crawl_url",
            "crawl_urls",
            "sb_browser_click",
            "sb_browser_extract_text",
            "sb_browser_navigate",
            "sb_browser_press",
            "sb_browser_scroll",
            "sb_browser_type",
        }
    ),
    ToolCapability.EXTRACT.value: frozenset(
        {
            "crawl_url",
            "crawl_urls",
            "sb_browser_extract_text",
            "sb_browser_screenshot",
        }
    ),
    ToolCapability.EXECUTE.value: frozenset({"execute_python_code"}),
    ToolCapability.WRITE.value: frozenset({"str_replace"}),
    ToolCapability.SYNTHESIZE.value: frozenset(),
    "fabric": frozenset({"fabric"}),
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


def _enabled(profile: dict[str, Any], key: str, default: bool = False) -> bool:
    enabled_tools = profile.get("enabled_tools") or {}
    if isinstance(enabled_tools, dict) and key in enabled_tools:
        return bool(enabled_tools.get(key))
    return default


@dataclass(frozen=True)
class ToolBuildContext:
    config: RunnableConfig
    configurable: dict[str, Any]
    profile: dict[str, Any]
    thread_id: str
    e2b_ready: bool


ToolFactory = Callable[[ToolBuildContext], list[BaseTool]]


@dataclass(frozen=True)
class ToolSpecification:
    key: str
    capabilities: frozenset[ToolCapability]
    default_enabled: bool
    factory: ToolFactory


def _build_web_search_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    if len(settings.search_engines_list) > 1:
        from tools import fallback_search

        return [fallback_search]
    return [tavily_search]


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
    if _enabled(ctx.profile, "sandbox_browser", default=False):
        return []
    return build_browser_tools(ctx.thread_id)


def _build_sandbox_browser_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode == "local" and ctx.e2b_ready:
        return build_sandbox_browser_tools(ctx.thread_id)
    return []


def _build_browser_use_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    return build_browser_use_tools(ctx.thread_id)


def _build_sandbox_web_search_tools_for_agent(ctx: ToolBuildContext) -> list[BaseTool]:
    if _enabled(ctx.profile, "web_search", default=True):
        return []
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
    return list(get_registered_tools())


def _build_daytona_tools(_ctx: ToolBuildContext) -> list[BaseTool]:
    if settings.sandbox_mode != "daytona":
        return []
    from tools.sandbox import daytona_create, daytona_stop

    return [daytona_create, daytona_stop]


TOOL_SPECS: tuple[ToolSpecification, ...] = (
    ToolSpecification(
        key="web_search",
        capabilities=frozenset({ToolCapability.SEARCH}),
        default_enabled=True,
        factory=_build_web_search_tools,
    ),
    ToolSpecification(
        key="rag",
        capabilities=frozenset({ToolCapability.SEARCH, ToolCapability.EXTRACT}),
        default_enabled=False,
        factory=_build_rag_tools,
    ),
    ToolSpecification(
        key="crawl",
        capabilities=frozenset({ToolCapability.READ, ToolCapability.EXTRACT}),
        default_enabled=True,
        factory=_build_crawl_tools,
    ),
    ToolSpecification(
        key="sandbox_browser",
        capabilities=frozenset({ToolCapability.BROWSE, ToolCapability.READ, ToolCapability.EXTRACT}),
        default_enabled=False,
        factory=_build_sandbox_browser_tools_for_agent,
    ),
    ToolSpecification(
        key="browser",
        capabilities=frozenset({ToolCapability.BROWSE, ToolCapability.READ}),
        default_enabled=False,
        factory=_build_browser_tools,
    ),
    ToolSpecification(
        key="browser_use",
        capabilities=frozenset({ToolCapability.BROWSE, ToolCapability.READ, ToolCapability.EXTRACT}),
        default_enabled=bool(settings.enable_browser_use),
        factory=_build_browser_use_tools_for_agent,
    ),
    ToolSpecification(
        key="sandbox_web_search",
        capabilities=frozenset({ToolCapability.SEARCH, ToolCapability.BROWSE}),
        default_enabled=False,
        factory=_build_sandbox_web_search_tools_for_agent,
    ),
    ToolSpecification(
        key="sandbox_files",
        capabilities=frozenset({ToolCapability.READ, ToolCapability.WRITE}),
        default_enabled=False,
        factory=_build_sandbox_files_tools_for_agent,
    ),
    ToolSpecification(
        key="sandbox_shell",
        capabilities=frozenset({ToolCapability.EXECUTE, ToolCapability.READ, ToolCapability.WRITE}),
        default_enabled=False,
        factory=_build_sandbox_shell_tools_for_agent,
    ),
    ToolSpecification(
        key="sandbox_sheets",
        capabilities=frozenset({ToolCapability.WRITE}),
        default_enabled=False,
        factory=_build_sandbox_sheets_tools_for_agent,
    ),
    ToolSpecification(
        key="sandbox_presentation",
        capabilities=frozenset({ToolCapability.WRITE}),
        default_enabled=False,
        factory=_build_sandbox_presentation_tools_for_agent,
    ),
    ToolSpecification(
        key="sandbox_vision",
        capabilities=frozenset({ToolCapability.EXTRACT}),
        default_enabled=False,
        factory=_build_sandbox_vision_tools_for_agent,
    ),
    ToolSpecification(
        key="sandbox_image_edit",
        capabilities=frozenset({ToolCapability.WRITE}),
        default_enabled=False,
        factory=_build_image_edit_tools_for_agent,
    ),
    ToolSpecification(
        key="sandbox_web_dev",
        capabilities=frozenset({ToolCapability.EXECUTE, ToolCapability.WRITE}),
        default_enabled=False,
        factory=_build_sandbox_web_dev_tools_for_agent,
    ),
    ToolSpecification(
        key="presentation_outline",
        capabilities=frozenset({ToolCapability.SYNTHESIZE}),
        default_enabled=False,
        factory=_build_presentation_outline_tools_for_agent,
    ),
    ToolSpecification(
        key="presentation_v2",
        capabilities=frozenset({ToolCapability.WRITE}),
        default_enabled=False,
        factory=_build_presentation_v2_tools_for_agent,
    ),
    ToolSpecification(
        key="python",
        capabilities=frozenset({ToolCapability.EXECUTE, ToolCapability.SYNTHESIZE}),
        default_enabled=False,
        factory=_build_python_tools,
    ),
    ToolSpecification(
        key="task_list",
        capabilities=frozenset({ToolCapability.WRITE}),
        default_enabled=True,
        factory=_build_task_tools,
    ),
    ToolSpecification(
        key="computer_use",
        capabilities=frozenset({ToolCapability.EXECUTE, ToolCapability.BROWSE}),
        default_enabled=False,
        factory=_build_computer_use_tools_for_agent,
    ),
    ToolSpecification(
        key="ask_human",
        capabilities=frozenset({ToolCapability.SYNTHESIZE}),
        default_enabled=True,
        factory=_build_ask_human_tools,
    ),
    ToolSpecification(
        key="str_replace",
        capabilities=frozenset({ToolCapability.WRITE}),
        default_enabled=True,
        factory=_build_str_replace_tools,
    ),
    ToolSpecification(
        key="bash",
        capabilities=frozenset({ToolCapability.EXECUTE}),
        default_enabled=False,
        factory=_build_bash_tools,
    ),
    ToolSpecification(
        key="planning",
        capabilities=frozenset({ToolCapability.SYNTHESIZE}),
        default_enabled=True,
        factory=_build_planning_tools,
    ),
    ToolSpecification(
        key="mcp",
        capabilities=frozenset({ToolCapability.SYNTHESIZE}),
        default_enabled=True,
        factory=_build_mcp_tools,
    ),
    ToolSpecification(
        key="sandbox_daytona",
        capabilities=frozenset({ToolCapability.EXECUTE, ToolCapability.WRITE}),
        default_enabled=True,
        factory=_build_daytona_tools,
    ),
)


class ToolCapabilityRegistry:
    def __init__(self, specs: Iterable[ToolSpecification] = TOOL_SPECS) -> None:
        self._specs = tuple(specs)

    def specs(self) -> tuple[ToolSpecification, ...]:
        return self._specs

    def build_tools(self, config: RunnableConfig) -> list[BaseTool]:
        configurable = _configurable(config)
        profile = configurable.get("agent_profile") or {}
        if not isinstance(profile, dict):
            profile = {}

        context = ToolBuildContext(
            config=config,
            configurable=configurable,
            profile=profile,
            thread_id=str(configurable.get("thread_id") or "default"),
            e2b_ready=_e2b_api_key_configured(),
        )

        tools: list[BaseTool] = []
        for spec in self._specs:
            if not _enabled(profile, spec.key, default=spec.default_enabled):
                continue
            tools.extend(spec.factory(context))

        for tool in tools:
            if hasattr(tool, "thread_id"):
                try:
                    setattr(tool, "thread_id", context.thread_id)
                except Exception:
                    pass

        deduped: dict[str, BaseTool] = {}
        for tool in tools:
            name = getattr(tool, "name", None)
            if isinstance(name, str) and name:
                deduped.setdefault(name, tool)

        tool_list = list(deduped.values())
        whitelist = profile.get("tool_whitelist") or []
        blacklist = profile.get("tool_blacklist") or []
        if whitelist:
            allowed = {str(item).strip() for item in whitelist if str(item).strip()}
            tool_list = [tool for tool in tool_list if getattr(tool, "name", "") in allowed]
        if blacklist:
            denied = {str(item).strip() for item in blacklist if str(item).strip()}
            tool_list = [tool for tool in tool_list if getattr(tool, "name", "") not in denied]
        return tool_list

    def resolve_concrete_tool_names(self, allowed: Iterable[str]) -> set[str]:
        resolved: set[str] = set()
        for item in allowed:
            normalized = str(item or "").strip().lower()
            if not normalized:
                continue
            if normalized in _CAPABILITY_TOOL_NAME_ALIASES:
                resolved.update(_CAPABILITY_TOOL_NAME_ALIASES[normalized])
                continue
            resolved.add(str(item).strip())
        return resolved


_DEFAULT_TOOL_REGISTRY = ToolCapabilityRegistry()


def build_default_tool_registry() -> ToolCapabilityRegistry:
    return _DEFAULT_TOOL_REGISTRY


def resolve_tool_names_for_capabilities(allowed: Iterable[str]) -> set[str]:
    return _DEFAULT_TOOL_REGISTRY.resolve_concrete_tool_names(allowed)

