import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_session_evidence_unknown_session_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sessions/nope/evidence")
        assert resp.status_code == 404
        error = (resp.json() or {}).get("error", "")
        assert "Session not found" in error
