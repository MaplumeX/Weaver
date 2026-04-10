from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig

from agent.tooling.capabilities import build_default_tool_providers, build_tool_context
from agent.tooling.providers import ProviderContext

_PROVIDER_CAPABILITY_MAP: dict[str, tuple[str, ...]] = {
    "web_search": ("search",),
    "rag": ("search", "knowledge"),
    "crawl": ("search", "browser"),
    "browser": ("browser",),
    "browser_use": ("browser", "automation"),
    "sandbox_browser": ("browser", "sandbox"),
    "sandbox_web_search": ("search", "sandbox"),
    "sandbox_files": ("files", "sandbox"),
    "sandbox_shell": ("shell", "sandbox"),
    "sandbox_sheets": ("sheets", "sandbox"),
    "sandbox_presentation": ("presentation", "sandbox"),
    "sandbox_vision": ("vision", "sandbox"),
    "sandbox_image_edit": ("image", "sandbox"),
    "sandbox_web_dev": ("web_dev", "sandbox"),
    "presentation_outline": ("planning", "presentation"),
    "presentation_v2": ("presentation",),
    "python": ("python",),
    "task_list": ("planning",),
    "computer_use": ("computer", "automation"),
    "ask_human": ("human",),
    "str_replace": ("files",),
    "bash": ("shell",),
    "planning": ("planning",),
    "mcp": ("mcp",),
    "sandbox_daytona": ("sandbox", "runtime"),
}


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    tool_name: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    source: str = ""
    module_name: str = ""
    class_name: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "standard"


def _tool_parameters(tool: Any) -> dict[str, Any]:
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is None:
        return {}
    try:
        if hasattr(args_schema, "model_json_schema"):
            return dict(args_schema.model_json_schema())
        if hasattr(args_schema, "schema"):
            return dict(args_schema.schema())
    except Exception:
        return {}
    return {}


def _normalize_texts(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def _provider_context(config: RunnableConfig) -> ProviderContext:
    context = build_tool_context(config)
    return ProviderContext(
        thread_id=context.thread_id,
        profile=context.profile,
        configurable=context.configurable,
        e2b_ready=context.e2b_ready,
        runtime=context.runtime,
    )


def _tool_risk_level(tool_name: str, capabilities: tuple[str, ...]) -> str:
    name = str(tool_name or "").strip()
    if "shell" in capabilities or name in {"execute_python_code", "safe_bash"}:
        return "high"
    if "files" in capabilities or "browser" in capabilities or "mcp" in capabilities:
        return "medium"
    return "standard"


def build_tool_registry(config: RunnableConfig) -> dict[str, ToolSpec]:
    registry: dict[str, ToolSpec] = {}
    context = _provider_context(config)
    for provider in build_default_tool_providers():
        capability_keys = _PROVIDER_CAPABILITY_MAP.get(provider.key, (provider.key,))
        for tool in provider.build_tools(context):
            tool_name = str(getattr(tool, "name", "") or "").strip()
            if not tool_name:
                continue
            tags = _normalize_texts(tuple(getattr(tool, "tags", None) or ()))
            capabilities = _normalize_texts((*capability_keys, *tags))
            existing = registry.get(tool_name)
            if existing is not None:
                registry[tool_name] = ToolSpec(
                    tool_id=existing.tool_id,
                    tool_name=existing.tool_name,
                    description=existing.description or str(getattr(tool, "description", "") or ""),
                    capabilities=_normalize_texts((*existing.capabilities, *capabilities)),
                    tags=_normalize_texts((*existing.tags, *tags)),
                    source=existing.source or provider.key,
                    module_name=existing.module_name or str(getattr(tool, "__module__", "") or ""),
                    class_name=existing.class_name
                    or str(getattr(tool.__class__, "__name__", "") or ""),
                    parameters=existing.parameters or _tool_parameters(tool),
                    risk_level=existing.risk_level,
                )
                continue

            registry[tool_name] = ToolSpec(
                tool_id=tool_name,
                tool_name=tool_name,
                description=str(getattr(tool, "description", "") or ""),
                capabilities=capabilities,
                tags=tags,
                source=provider.key,
                module_name=str(getattr(tool, "__module__", "") or ""),
                class_name=str(getattr(tool.__class__, "__name__", "") or ""),
                parameters=_tool_parameters(tool),
                risk_level=_tool_risk_level(tool_name, capabilities),
            )
    return registry


__all__ = ["ToolSpec", "build_tool_registry"]
