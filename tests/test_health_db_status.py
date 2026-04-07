import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_health_reports_failed_when_database_url_missing(monkeypatch):
    monkeypatch.setattr(main.settings, "database_url", "")
    monkeypatch.setattr(main, "_checkpointer_status", "failed")
    monkeypatch.setattr(main, "_checkpointer_error", "DATABASE_URL is required for session persistence")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["database"] == "failed"
    assert payload["database_error"] == "DATABASE_URL is required for session persistence"


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


@pytest.mark.asyncio
async def test_initialize_runtime_state_leaves_checkpointer_disabled_without_database_url(monkeypatch):
    async def fake_close_runtime_resources():
        return None

    monkeypatch.setattr(main.settings, "database_url", "")
    monkeypatch.setattr(main.settings, "memory_store_backend", "memory")
    monkeypatch.setattr(main, "checkpointer", object())
    monkeypatch.setattr(main, "store", None)
    monkeypatch.setattr(main, "_close_runtime_resources", fake_close_runtime_resources)
    monkeypatch.setattr(main, "_compile_runtime_graphs", lambda: None)

    await main._initialize_runtime_state()

    assert main.checkpointer is None
    assert main._checkpointer_status == "failed"
    assert main._checkpointer_error == "DATABASE_URL is required for session persistence"


@pytest.mark.asyncio
async def test_initialize_runtime_state_creates_session_service_when_database_url_present(monkeypatch):
    class DummyCheckpointer:
        conn = object()

    class DummySessionStore:
        conn = object()

        async def setup(self):
            return None

    async def fake_close_runtime_resources():
        return None

    async def fake_create_checkpointer(_database_url: str):
        return DummyCheckpointer()

    async def fake_create_session_store(_database_url: str):
        return DummySessionStore()

    monkeypatch.setattr(main.settings, "database_url", "postgresql://example")
    monkeypatch.setattr(main.settings, "memory_store_backend", "memory")
    monkeypatch.setattr(main, "_close_runtime_resources", fake_close_runtime_resources)
    monkeypatch.setattr(main, "_compile_runtime_graphs", lambda: None)
    monkeypatch.setattr(main, "create_checkpointer", fake_create_checkpointer)
    monkeypatch.setattr(main, "create_session_store", fake_create_session_store, raising=False)

    await main._initialize_runtime_state()

    assert main.checkpointer is not None
    assert main.session_store is not None
    assert main.session_service is not None
