from __future__ import annotations

from types import SimpleNamespace

import pytest

import main
from agent.infrastructure.tools.capabilities import _build_mcp_tools
from agent.infrastructure.tools.providers import ProviderContext
from main import MCPConfigPayload
from tools.mcp import get_live_mcp_tools


def test_build_mcp_tools_reads_live_mcp_snapshot(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.capabilities.get_live_mcp_tools",
        lambda: [SimpleNamespace(name="mcp_fetch", description="fetch")],
    )

    tools = _build_mcp_tools(
        ProviderContext(thread_id="mcp-1", profile={}, configurable={}, e2b_ready=False)
    )

    assert [tool.name for tool in tools] == ["mcp_fetch"]


@pytest.mark.asyncio
async def test_update_mcp_config_returns_loaded_tool_count(monkeypatch):
    async def _reload(*_args, **_kwargs):
        return [SimpleNamespace(name="mcp_fetch", description="fetch")]

    async def _close():
        return None

    monkeypatch.setattr(
        main,
        "reload_mcp_tools",
        _reload,
    )
    monkeypatch.setattr(main, "close_mcp_tools", _close)

    payload = MCPConfigPayload(enable=True, servers={"demo": {"type": "sse", "url": "https://example.com"}})
    result = await main.update_mcp_config(payload)

    assert result["enabled"] is True
    assert result["loaded_tools"] == 1


def test_get_live_mcp_tools_defaults_to_empty_list():
    assert get_live_mcp_tools() == []
