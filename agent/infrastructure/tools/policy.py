from __future__ import annotations

from collections.abc import Iterable

from langchain_core.tools import BaseTool


def filter_tools_by_name(
    tools: list[BaseTool],
    *,
    allowed: Iterable[str] | None = None,
    blocked: Iterable[str] | None = None,
) -> list[BaseTool]:
    allowed_names = {str(item).strip() for item in (allowed or []) if str(item).strip()}
    blocked_names = {str(item).strip() for item in (blocked or []) if str(item).strip()}
    filtered = tools
    if allowed_names:
        filtered = [tool for tool in filtered if getattr(tool, "name", "") in allowed_names]
    if blocked_names:
        filtered = [tool for tool in filtered if getattr(tool, "name", "") not in blocked_names]
    return filtered
