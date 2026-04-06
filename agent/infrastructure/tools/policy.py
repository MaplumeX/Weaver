from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain_core.tools import BaseTool


def is_tool_enabled(profile: dict[str, Any], key: str, default: bool = False) -> bool:
    enabled_tools = profile.get("enabled_tools") or {}
    if isinstance(enabled_tools, dict) and key in enabled_tools:
        return bool(enabled_tools.get(key))
    return default


def filter_tools_by_name(
    tools: list[BaseTool],
    *,
    whitelist: Iterable[str] | None = None,
    blacklist: Iterable[str] | None = None,
) -> list[BaseTool]:
    allowed = {str(item).strip() for item in (whitelist or []) if str(item).strip()}
    denied = {str(item).strip() for item in (blacklist or []) if str(item).strip()}
    filtered = tools
    if allowed:
        filtered = [tool for tool in filtered if getattr(tool, "name", "") in allowed]
    if denied:
        filtered = [tool for tool in filtered if getattr(tool, "name", "") not in denied]
    return filtered
