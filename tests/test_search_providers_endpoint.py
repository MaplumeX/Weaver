import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_search_providers_endpoint_exposes_provider_health(monkeypatch):
    # Make the response deterministic by patching the orchestrator if the endpoint
    # implementation imports it into `main`.
    if hasattr(main, "get_search_orchestrator"):
        from tools.search.multi_search import MultiSearchOrchestrator, SearchProvider, SearchResult
        from tools.search.reliability import ProviderReliabilityManager, ReliabilityPolicy

        class DummyProvider(SearchProvider):
            def __init__(self, name: str):
                super().__init__(name=name, api_key="dummy")

            def is_available(self) -> bool:
                return True

            def search(self, query: str, max_results: int = 10):  # type: ignore[override]
                return [
                    SearchResult(
                        title="x",
                        url="https://example.com",
                        snippet="y",
                        provider=self.name,
                    )
                ]

        reliability = ProviderReliabilityManager(
            ReliabilityPolicy(
                max_retries=0,
                retry_backoff_seconds=0.0,
                circuit_breaker_failures=2,
                circuit_breaker_reset_seconds=60.0,
            )
        )

        provider = DummyProvider("dummy")
        provider.stats.total_calls = 10
        provider.stats.success_count = 7
        provider.stats.error_count = 3
        provider.stats.total_latency_ms = 700.0
        provider.stats.avg_result_quality = 0.75
        provider.stats.is_healthy = False
        provider.stats.last_error = "boom"
        provider.stats.last_error_time = "2026-02-20T00:00:00"

        # Open circuit for this provider.
        reliability._record_failure(provider.name)  # pylint: disable=protected-access
        reliability._record_failure(provider.name)  # pylint: disable=protected-access

        orch = MultiSearchOrchestrator(
            providers=[provider],
            reliability_manager=reliability,
        )

        monkeypatch.setattr(main, "get_search_orchestrator", lambda: orch)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/search/providers")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("providers"), list)
    assert data["providers"] and data["providers"][0]["name"] == "dummy"
    assert "circuit" in data["providers"][0]
    assert isinstance(data["providers"][0]["circuit"].get("is_open"), bool)

