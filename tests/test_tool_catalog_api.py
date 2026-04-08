from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import main
from agent.infrastructure.tools.registry import ToolSpec


@pytest.mark.asyncio
async def test_tools_catalog_endpoint_uses_runtime_inventory(monkeypatch):
    monkeypatch.setattr(
        main,
        "build_tool_inventory",
        lambda _config: [SimpleNamespace(name="browser_navigate", description="open url")],
    )
    monkeypatch.setattr(
        main,
        "build_tool_registry",
        lambda _config: {
            "browser_navigate": ToolSpec(
                tool_id="browser_navigate",
                tool_name="browser_navigate",
                capabilities=("browser",),
                source="browser",
                risk_level="medium",
            )
        },
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/tools/catalog")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["stats"]["total_tools"] == 1
    assert payload["tools"][0]["name"] == "browser_navigate"
    assert payload["tools"][0]["tool_id"] == "browser_navigate"
    assert payload["tools"][0]["capabilities"] == ["browser"]
    assert payload["tools"][0]["source"] == "browser"
    assert payload["tools"][0]["risk_level"] == "medium"


@pytest.mark.asyncio
async def test_agent_health_endpoint_uses_catalog_inventory_count(monkeypatch):
    monkeypatch.setattr(
        main,
        "build_tool_inventory",
        lambda _config: [
            SimpleNamespace(name="browser_navigate", description="open url"),
            SimpleNamespace(name="crawl_url", description="crawl"),
        ],
    )
    monkeypatch.setattr(
        main,
        "build_tool_registry",
        lambda _config: {
            "browser_navigate": ToolSpec(
                tool_id="browser_navigate",
                tool_name="browser_navigate",
                capabilities=("browser",),
                source="browser",
                risk_level="medium",
            ),
            "crawl_url": ToolSpec(
                tool_id="crawl_url",
                tool_name="crawl_url",
                capabilities=("search", "browser"),
                source="crawl",
                risk_level="medium",
            ),
        },
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health/agent")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tool_catalog_total_tools"] == 2
