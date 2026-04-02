import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_public_config_endpoint_exposes_safe_defaults():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/config/public")

    assert resp.status_code == 200
    payload = resp.json()

    assert payload["version"] == main.app.version
    assert payload["defaults"]["primary_model"] == main.settings.primary_model
    assert payload["defaults"]["reasoning_model"] == main.settings.reasoning_model

    assert payload["streaming"]["chat"]["protocol"] in {"sse", "legacy"}
    assert payload["streaming"]["research"]["protocol"] in {"sse", "legacy"}

    # Should not leak secrets.
    as_text = resp.text
    assert "OPENAI_API_KEY" not in as_text
    assert "E2B_API_KEY" not in as_text


def test_public_model_options_only_include_explicit_backend_models(monkeypatch):
    monkeypatch.setattr(main.settings, "primary_model", "deepseek-v3-2-251201")
    monkeypatch.setattr(main.settings, "reasoning_model", "deepseek-r1")
    monkeypatch.setattr(main.settings, "planner_model", "gpt-5")
    monkeypatch.setattr(main.settings, "researcher_model", "")
    monkeypatch.setattr(main.settings, "writer_model", " ")
    monkeypatch.setattr(main.settings, "evaluator_model", "claude-sonnet-4-5-20250514")
    monkeypatch.setattr(main.settings, "critic_model", "deepseek-r1")

    assert main._public_model_options() == [
        "deepseek-v3-2-251201",
        "deepseek-r1",
        "gpt-5",
        "claude-sonnet-4-5-20250514",
    ]
