from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_export_report_json_includes_evidence_payload(monkeypatch):
    state = {
        "final_report": "According to the report, revenue increased by 20% in 2024.",
        "deep_research_artifacts": {
            "sources": [
                {
                    "title": "Annual Report",
                    "url": "https://example.com/?utm_source=test",
                }
            ],
            "branch_results": [
                {
                    "id": "branch_1",
                    "task_id": "task_1",
                    "branch_id": "branch_1",
                    "title": "Revenue",
                    "summary": "Revenue increased by 20% in 2024.",
                    "source_urls": ["https://example.com/?utm_source=test"],
                    "validation_status": "passed",
                }
            ],
            "validation_summary": {"passed_branch_count": 1},
            "quality_summary": {"summary_count": 1, "source_count": 1},
        },
    }

    checkpoint = SimpleNamespace(checkpoint={"channel_values": state})
    monkeypatch.setattr(
        main,
        "checkpointer",
        SimpleNamespace(get_tuple=lambda config: checkpoint),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/export/thread-1", params={"format": "json"})

    assert resp.status_code == 200
    assert "application/json" in (resp.headers.get("content-type") or "")
    data = resp.json()
    assert isinstance(data.get("report"), str)
    assert isinstance(data.get("sources"), list)
    assert "claims" not in data
    assert isinstance(data.get("branch_results"), list)
    branch_result = (data.get("branch_results") or [None])[0] or {}
    assert branch_result.get("validation_status") == "passed"
    assert "utm_source" not in (branch_result.get("source_urls") or [""])[0]
    assert isinstance(data.get("quality"), dict)


@pytest.mark.asyncio
async def test_export_report_json_strips_deprecated_claim_artifacts(monkeypatch):
    state = {
        "final_report": "The company's revenue increased in 2024 according to the annual report.",
        "scraped_content": [],
        "deep_research_artifacts": {
            "claims": [{"claim": "The company's revenue increased in 2024.", "status": "verified"}],
            "answer_units": [{"id": "answer_1"}],
            "coverage_obligations": [{"id": "obligation_1"}],
            "quality_summary": {"summary_count": 1},
        },
    }

    checkpoint = SimpleNamespace(checkpoint={"channel_values": state})
    monkeypatch.setattr(
        main,
        "checkpointer",
        SimpleNamespace(get_tuple=lambda config: checkpoint),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/export/thread-2", params={"format": "json"})

    assert resp.status_code == 200
    data = resp.json() or {}
    assert "claims" not in data
    assert isinstance(data.get("quality"), dict)
