from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_session_evidence_unknown_session_returns_404(monkeypatch):
    monkeypatch.setattr(main, "checkpointer", None)
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sessions/nope/evidence")
        assert resp.status_code == 404
        error = (resp.json() or {}).get("error", "")
        assert "Session not found" in error


@pytest.mark.asyncio
async def test_session_evidence_includes_fetched_pages_and_passages(monkeypatch):
    artifacts = {
        "sources": [],
        "quality_summary": {"summary_count": 1},
        "fetched_pages": [
            {
                "url": "https://example.com/",
                "raw_url": "https://example.com/?utm=1",
                "method": "direct_http",
                "text": "hello",
                "http_status": 200,
                "attempts": 1,
            }
        ],
        "passages": [
            {
                "url": "https://example.com/",
                "text": "hello",
                "start_char": 0,
                "end_char": 5,
                "heading": "Intro",
                "heading_path": ["Intro"],
                "page_title": "Example Title",
                "retrieved_at": "2026-02-17T00:00:00+00:00",
                "method": "direct_http",
                "quote": "hello",
                "snippet_hash": "deadbeef",
            }
        ],
    }
    async def fake_get_thread_runtime_state(checkpointer, thread_id: str):
        if thread_id != "thread-evidence":
            return None
        return {"route": "deep", "deep_research_artifacts": artifacts}

    monkeypatch.setattr(main, "checkpointer", object())
    monkeypatch.setattr(main, "get_thread_runtime_state", fake_get_thread_runtime_state)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sessions/thread-evidence/evidence")

    assert resp.status_code == 200
    data = resp.json() or {}
    assert data.get("quality_summary", {}).get("summary_count") == 1
    assert len(data.get("fetched_pages", [])) == 1
    assert len(data.get("passages", [])) == 1
    passage = (data.get("passages", []) or [None])[0] or {}
    assert passage.get("heading") == "Intro"
    assert passage.get("heading_path") == ["Intro"]
    assert passage.get("page_title") == "Example Title"
    assert passage.get("retrieved_at") == "2026-02-17T00:00:00+00:00"
    assert passage.get("method") == "direct_http"
    assert passage.get("quote") == "hello"
    assert passage.get("snippet_hash") == "deadbeef"


@pytest.mark.asyncio
async def test_session_evidence_strips_deprecated_claim_artifacts(monkeypatch):
    state = {
        "deep_research_artifacts": {
            "claims": [{"claim": "Revenue increased in 2024.", "status": "verified"}],
            "answer_units": [{"id": "answer_1"}],
            "passages": [
                {
                    "url": "https://example.com/earnings",
                    "text": "In 2024, the company's revenue increased by 5% year over year.",
                    "start_char": 0,
                    "end_char": 66,
                    "snippet_hash": "passage_123",
                    "quote": "In 2024, the company's revenue increased by 5% year over year.",
                    "heading_path": ["Results"],
                }
            ]
        },
    }

    checkpoint = SimpleNamespace(checkpoint={"channel_values": state}, metadata={}, parent_config=None)
    monkeypatch.setattr(main, "checkpointer", SimpleNamespace(get_tuple=lambda config: checkpoint))

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/sessions/thread-claims/evidence")

    assert resp.status_code == 200
    data = resp.json() or {}
    assert "claims" not in data
    passages = data.get("passages") or []
    assert passages, "expected passages to be preserved"
    passage = passages[0] or {}
    assert passage.get("snippet_hash") == "passage_123"
    assert passage.get("url") == "https://example.com/earnings"
