"""
Factory to create LangChain agents with official middleware (selector, retry, limits, HITL).
"""

import logging
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    HumanInTheLoopMiddleware,
    TodoListMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from agent.infrastructure.agents.provider_safe_middleware import ProviderSafeToolSelectorMiddleware
from agent.infrastructure.tools import build_tools_for_names
from common.config import settings

logger = logging.getLogger(__name__)

DEEP_RESEARCH_CONTROL_PLANE_ROLES = frozenset({"clarify", "scope", "supervisor"})
DEEP_RESEARCH_EXECUTION_ROLES = frozenset({"researcher", "verifier", "reporter"})

_DEEP_RESEARCH_ROLE_TOOL_ALLOWLISTS = {
    "clarify": {"fabric"},
    "scope": {"fabric"},
    "supervisor": {"fabric"},
    "researcher": {
        "fabric",
        "web_search",
        "browser_search",
        "sandbox_web_search",
        "sandbox_search_and_click",
        "sandbox_extract_search_results",
        "browser_navigate",
        "browser_click",
        "crawl_url",
        "crawl_urls",
        "sb_browser_navigate",
        "sb_browser_click",
        "sb_browser_type",
        "sb_browser_press",
        "sb_browser_scroll",
        "sb_browser_extract_text",
        "sb_browser_screenshot",
    },
    "verifier": {
        "fabric",
        "web_search",
        "browser_search",
        "sandbox_web_search",
        "sandbox_search_and_click",
        "sandbox_extract_search_results",
        "browser_navigate",
        "browser_click",
        "crawl_url",
        "crawl_urls",
        "sb_browser_navigate",
        "sb_browser_click",
        "sb_browser_type",
        "sb_browser_press",
        "sb_browser_scroll",
        "sb_browser_extract_text",
        "sb_browser_screenshot",
    },
    "reporter": {"fabric", "execute_python_code"},
}

_DEEP_RESEARCH_TOOL_ALIASES = {
    "search": {
        "web_search",
        "browser_search",
        "sandbox_web_search",
        "sandbox_search_and_click",
        "crawl_url",
        "crawl_urls",
    },
    "read": {
        "browser_navigate",
        "browser_click",
        "browser_extract_text",
        "sb_browser_navigate",
        "sb_browser_click",
        "sb_browser_extract_text",
        "sandbox_extract_search_results",
    },
    "extract": {
        "browser_extract_text",
        "sb_browser_extract_text",
        "sandbox_extract_search_results",
        "crawl_url",
        "crawl_urls",
    },
    "synthesize": {
        "fabric",
        "execute_python_code",
    },
}


@dataclass(frozen=True)
class DeepResearchToolPolicy:
    role: str
    requested_tools: tuple[str, ...]
    allowed_tool_names: tuple[str, ...]


def _build_llm(model: str, temperature: float = 0.7) -> ChatOpenAI:
    params = {
        "model": model,
        "temperature": temperature,
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout or None,
    }
    if settings.use_azure:
        params.update(
            {
                "azure_endpoint": settings.azure_endpoint or None,
                "azure_deployment": model,
                "api_version": settings.azure_api_version or None,
                "api_key": settings.azure_api_key or settings.openai_api_key,
            }
        )
    elif settings.openai_base_url:
        params["base_url"] = settings.openai_base_url

    return ChatOpenAI(**params)


def _selector_llm() -> ChatOpenAI:
    return _build_llm(settings.tool_selector_model or settings.primary_model, temperature=0)


def _tool_selector_methods() -> tuple[str, ...]:
    """Choose structured-output methods in provider-preferred order."""
    if settings.use_azure:
        return ("json_schema", "function_calling", "json_mode")
    base_url = (settings.openai_base_url or "").strip().lower()
    if not base_url:
        return ("json_schema", "function_calling", "json_mode")
    if "api.openai.com" in base_url:
        return ("json_schema", "function_calling", "json_mode")
    # DeepSeek and other OpenAI-compatible gateways have been more reliable with
    # JSON mode than function-calling for tool-selection prompts.
    return ("json_mode", "function_calling", "json_schema")


def _tool_selector_always_include() -> list[str]:
    names = list(settings.tool_selector_always_include_list)
    if settings.enable_todo_middleware and "write_todos" not in names:
        names.append("write_todos")
    return names


def _build_todo_middleware() -> TodoListMiddleware:
    kwargs = {}
    custom_prompt = (settings.todo_system_prompt or "").strip()
    custom_description = (settings.todo_tool_description or "").strip()
    if custom_prompt:
        kwargs["system_prompt"] = custom_prompt
    if custom_description:
        kwargs["tool_description"] = custom_description
    return TodoListMiddleware(**kwargs)


def _build_middlewares() -> list:
    mws: list = []

    # Tool selector
    if settings.tool_selector:
        selector_kwargs = {
            "model": _selector_llm(),
            "max_tools": settings.tool_selector_max_tools or 3,
            "always_include": _tool_selector_always_include(),
            "selection_methods": _tool_selector_methods(),
        }
        # Don't pass `None` here — it overrides LangChain's DEFAULT_SYSTEM_PROMPT
        # and will crash when the middleware appends max_tools guidance.
        custom_prompt = (settings.tool_selector_prompt or "").strip()
        if custom_prompt:
            selector_kwargs["system_prompt"] = custom_prompt

        mws.append(ProviderSafeToolSelectorMiddleware(**selector_kwargs))

    # Tool retry
    if settings.tool_retry:
        mws.append(
            ToolRetryMiddleware(
                max_retries=max(settings.tool_retry_max_attempts - 1, 1),
                backoff_factor=settings.tool_retry_backoff or 1.5,
                initial_delay=settings.tool_retry_initial_delay or 1.0,
                max_delay=settings.tool_retry_max_delay or 60.0,
                jitter=True,
                on_failure="continue",
            )
        )

    # Tool call limit
    if settings.tool_call_limit > 0:
        mws.append(
            ToolCallLimitMiddleware(
                run_limit=settings.tool_call_limit,
                exit_behavior="end",
            )
        )

    # Context editing: clear old tool uses if requested
    if settings.strip_tool_messages:
        mws.append(
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=settings.context_edit_trigger_tokens or 1000,
                        clear_at_least=0,
                        keep=settings.context_edit_keep_tools or 3,
                        clear_tool_inputs=False,
                        exclude_tools=(),
                        placeholder="[cleared]",
                    )
                ],
                token_count_method="approximate",
            )
        )

    # Todo list middleware (optional)
    if settings.enable_todo_middleware:
        mws.append(_build_todo_middleware())

    # Human-in-the-loop for risky tools
    if settings.tool_approval:
        # Apply to high-impact tools by default.
        interrupt_cfg = {
            "execute_python_code": True,
            # Lightweight browser tools (network + navigation)
            "browser_search": True,
            "browser_navigate": True,
            "browser_click": True,
            # Sandbox browser tools (network + navigation)
            "sb_browser_navigate": True,
            "sb_browser_click": True,
            "sb_browser_type": True,
            "sb_browser_press": True,
            "sb_browser_scroll": True,
            "sb_browser_extract_text": True,
            "sb_browser_screenshot": True,
            # Crawling helpers (network fetch)
            "crawl_url": True,
            "crawl_urls": True,
        }
        mws.append(
            HumanInTheLoopMiddleware(
                interrupt_on=interrupt_cfg,
                description_prefix="Tool execution pending approval",
            )
        )

    return mws
def build_tool_agent(*, model: str, tools: list[BaseTool], temperature: float = 0.7) -> object:
    """
    Create a generic tool-calling agent using the shared middleware stack.
    """
    model_name = (model or settings.primary_model).strip()
    return create_agent(
        _build_llm(model_name, temperature=temperature),
        tools,
        middleware=_build_middlewares(),
    )


def _resolve_deep_research_tool_names(allowed_tools: list[str] | None = None) -> set[str]:
    requested = [str(item).strip() for item in (allowed_tools or []) if str(item).strip()]
    if not requested:
        requested = ["web_search", "crawl_url", "sb_browser_extract_text"]
    resolved: set[str] = set()
    for item in requested:
        alias_key = item.lower()
        alias_values = _DEEP_RESEARCH_TOOL_ALIASES.get(alias_key)
        if alias_values:
            resolved.update(alias_values)
        else:
            resolved.add(item)
    return resolved


def _dedupe_texts(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return tuple(deduped)


def resolve_deep_research_role_tool_names(
    role: str,
    *,
    allowed_tools: list[str] | None = None,
    enable_supervisor_world_tools: bool = False,
    enable_reporter_python_tools: bool = True,
) -> set[str]:
    return set(
        resolve_deep_research_role_tool_policy(
            role,
            allowed_tools=allowed_tools,
            enable_supervisor_world_tools=enable_supervisor_world_tools,
            enable_reporter_python_tools=enable_reporter_python_tools,
        ).allowed_tool_names
    )


def resolve_deep_research_role_tool_policy(
    role: str,
    *,
    allowed_tools: list[str] | None = None,
    enable_supervisor_world_tools: bool = False,
    enable_reporter_python_tools: bool = True,
) -> DeepResearchToolPolicy:
    normalized_role = str(role or "").strip().lower()
    requested = list(_DEEP_RESEARCH_ROLE_TOOL_ALLOWLISTS.get(normalized_role, ()))
    if normalized_role == "supervisor" and enable_supervisor_world_tools:
        requested.extend(
            [
                "browser_search",
                "web_search",
                "sandbox_web_search",
                "sandbox_search_and_click",
                "sandbox_extract_search_results",
                "browser_navigate",
                "browser_click",
                "crawl_url",
                "crawl_urls",
                "sb_browser_navigate",
                "sb_browser_click",
                "sb_browser_type",
                "sb_browser_press",
                "sb_browser_scroll",
                "sb_browser_extract_text",
            ]
        )
    if normalized_role == "reporter" and not enable_reporter_python_tools:
        requested = [item for item in requested if item != "execute_python_code"]
    requested.extend(str(item).strip() for item in (allowed_tools or []) if str(item).strip())
    return DeepResearchToolPolicy(
        role=normalized_role,
        requested_tools=_dedupe_texts(requested),
        allowed_tool_names=tuple(sorted(_resolve_deep_research_tool_names(requested))),
    )


def build_deep_research_tool_agent(
    *,
    model: str | None = None,
    role: str | None = None,
    allowed_tools: list[str] | None = None,
    extra_tools: list[BaseTool] | None = None,
    temperature: float = 0.1,
) -> tuple[object, list[BaseTool]]:
    """
    Create a Deep Research-specific tool agent with a restricted toolset.
    """
    model_name = (model or settings.primary_model).strip()
    if role:
        policy = resolve_deep_research_role_tool_policy(
            role,
            allowed_tools=allowed_tools,
            enable_supervisor_world_tools=bool(
                getattr(settings, "deep_research_supervisor_allow_world_tools", False)
            ),
            enable_reporter_python_tools=bool(
                getattr(settings, "deep_research_reporter_enable_python_tools", True)
            ),
        )
        allowed_names = set(policy.allowed_tool_names)
    else:
        allowed_names = _resolve_deep_research_tool_names(allowed_tools)
    tools = list(extra_tools or [])
    existing_names = {tool.name for tool in tools if getattr(tool, "name", None)}
    for tool in build_tools_for_names(allowed_names):
        if tool.name in existing_names:
            continue
        tools.append(tool)
    agent = build_tool_agent(model=model_name, tools=tools, temperature=temperature)
    return agent, tools
