from __future__ import annotations

from tools.core.registry import ToolRegistry


def test_tool_registry_discovers_module_level_langchain_tools() -> None:
    registry = ToolRegistry()
    discovered = registry.discover_from_module("tools.search.search", tags=["test"])

    names = {m.name for m in discovered}
    assert "tavily_search" in names

    metadata = registry.get_metadata("tavily_search")
    assert metadata is not None
    assert metadata.tool_type == "langchain"

    params = metadata.parameters or {}
    # Pydantic schemas should include properties for tool parameters.
    assert isinstance(params, dict)
    assert "properties" in params
    assert "query" in (params.get("properties") or {})

