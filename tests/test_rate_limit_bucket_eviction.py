import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_rate_limit_bucket_storage_is_capped(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "rate_limit_enabled", True)
    monkeypatch.setitem(main.settings.__dict__, "rate_limit_max_buckets", 3)

    # Clear any global state from other tests.
    main._rate_limit_buckets.clear()  # type: ignore[attr-defined]

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for i in range(10):
            await ac.get(
                "/api/config/public",
                headers={"X-Forwarded-For": f"10.0.0.{i}"},
            )

    assert len(main._rate_limit_buckets) <= 3  # type: ignore[attr-defined]

