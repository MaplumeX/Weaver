from __future__ import annotations

from types import SimpleNamespace

from agent.infrastructure.tools.catalog import build_tool_catalog_snapshot
from tools.core.registry import ToolRegistry


def test_tool_catalog_snapshot_can_be_built_from_runtime_tools() -> None:
    snapshot = build_tool_catalog_snapshot(
        tools=[SimpleNamespace(name="browser_navigate", description="open url")],
        source="runtime_inventory",
    )

    assert snapshot["total_tools"] == 1
    assert snapshot["tools"][0]["name"] == "browser_navigate"
    assert snapshot["source"] == "runtime_inventory"


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
