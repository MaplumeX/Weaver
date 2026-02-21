import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_rate_limit_headers_present_on_api_endpoints(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/memory/status")

    assert resp.status_code == 200
    assert resp.headers.get("x-ratelimit-limit")
    assert resp.headers.get("x-ratelimit-remaining")
    assert resp.headers.get("x-ratelimit-reset")

