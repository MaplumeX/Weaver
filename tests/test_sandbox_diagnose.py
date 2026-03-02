import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_sandbox_browser_diagnose_reports_missing_e2b_key(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "e2b_api_key", "")
    monkeypatch.setitem(main.settings.__dict__, "sandbox_template_browser", "")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sandbox/browser/diagnose")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ready"] is False
    assert "E2B_API_KEY" in payload["missing"]

