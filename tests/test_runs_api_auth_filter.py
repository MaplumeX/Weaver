import pytest
from httpx import ASGITransport, AsyncClient

import main
from common.metrics import metrics_registry
from common.thread_ownership import set_thread_owner


@pytest.mark.asyncio
async def test_run_metrics_forbidden_for_other_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(metrics_registry, "_runs", {})

    thread_id = "thread_run_alice"
    set_thread_owner(thread_id, "alice")
    metrics_registry.start(thread_id, model="dummy", route="direct")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        forbidden = await ac.get(
            f"/api/runs/{thread_id}",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "bob",
            },
        )
        assert forbidden.status_code == 403

        allowed = await ac.get(
            f"/api/runs/{thread_id}",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
        )
        assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_runs_list_is_filtered_by_principal_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(metrics_registry, "_runs", {})

    alice_run = "thread_run_alice_list"
    bob_run = "thread_run_bob_list"
    set_thread_owner(alice_run, "alice")
    set_thread_owner(bob_run, "bob")
    metrics_registry.start(alice_run, model="dummy", route="direct")
    metrics_registry.start(bob_run, model="dummy", route="direct")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/runs",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    run_ids = [r.get("run_id") for r in payload.get("runs", [])]
    assert run_ids == [alice_run]

