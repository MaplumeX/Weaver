import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

import main


def test_resolve_requested_model_rejects_models_outside_public_allowlist(monkeypatch):
    monkeypatch.setattr(main.settings, "primary_model", "gpt-4o")
    monkeypatch.setattr(main.settings, "reasoning_model", "o1-mini")
    monkeypatch.setattr(main.settings, "openai_api_key", "dummy")
    monkeypatch.setattr(main.settings, "openai_base_url", "https://api.openai.com/v1")

    with pytest.raises(HTTPException) as exc:
        main._resolve_requested_model("deepseek-chat")

    assert exc.value.status_code == 400
    assert "Unsupported model" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_chat_endpoint_rejects_unsupported_model_before_streaming(monkeypatch):
    monkeypatch.setattr(main.settings, "primary_model", "gpt-4o")
    monkeypatch.setattr(main.settings, "reasoning_model", "o1-mini")
    monkeypatch.setattr(main.settings, "openai_api_key", "dummy")
    monkeypatch.setattr(main.settings, "openai_base_url", "https://api.openai.com/v1")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model": "deepseek-chat",
                "stream": True,
            },
        )

    assert resp.status_code == 400
    assert "Unsupported model" in resp.text
