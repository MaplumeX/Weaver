import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_health_reports_not_configured_when_database_url_missing(monkeypatch):
    monkeypatch.setattr(main.settings, "database_url", "")
    monkeypatch.setattr(main, "_checkpointer_status", "not_configured")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["database"] == "not_configured"


@pytest.mark.asyncio
async def test_health_reports_ready_when_database_url_present(monkeypatch):
    monkeypatch.setattr(main.settings, "database_url", "postgresql://example")
    monkeypatch.setattr(main, "_checkpointer_status", "ready")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["database"] == "ready"
