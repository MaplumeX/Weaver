import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main
from main import SearchMode, _coerce_search_mode_input, _normalize_search_mode


def test_normalize_search_mode_defaults_to_agent():
    mode = _normalize_search_mode(None)
    assert mode == {"mode": "agent"}


def test_normalize_search_mode_deep_object():
    mode = _normalize_search_mode(SearchMode(mode="deep"))
    assert mode == {"mode": "deep"}


def test_normalize_search_mode_accepts_canonical_mode_dict():
    mode = _normalize_search_mode({"mode": "agent"})
    assert mode == {"mode": "agent"}


def test_normalize_search_mode_ignores_missing_mode_in_internal_dict():
    mode = _normalize_search_mode({})
    assert mode == {"mode": "agent"}


@pytest.mark.parametrize(
    "payload,expected",
    [
        ("mcp", "removed on 2026-04-02"),
        ({"useWebSearch": True}, "legacy fields"),
        ({"mode": "web"}, "removed on 2026-04-02"),
    ],
)
def test_search_mode_payload_rejects_removed_modes_and_legacy_fields(payload, expected):
    with pytest.raises(ValueError, match=expected):
        _coerce_search_mode_input(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/sse"])
@pytest.mark.parametrize(
    "search_mode,expected",
    [
        ("mcp", "removed on 2026-04-02"),
        ({"useAgent": True}, "legacy fields"),
        ({"mode": "web"}, "removed on 2026-04-02"),
    ],
)
async def test_chat_http_endpoints_reject_removed_search_mode_payloads(
    endpoint, search_mode, expected
):
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            endpoint,
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "search_mode": search_mode,
            },
        )

    assert response.status_code == 422
    assert expected in response.text
