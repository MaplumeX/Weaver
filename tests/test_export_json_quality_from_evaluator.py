from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import main
import agent.compat.nodes as nodes
from agent.workflows.quality_assessor import QualityReport


class _FakeEvalLLM:
    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages, config=None):
        return SimpleNamespace(
            verdict="pass",
            dimensions=SimpleNamespace(
                coverage=0.9,
                accuracy=0.9,
                freshness=0.9,
                coherence=0.9,
            ),
            feedback="good",
            missing_topics=[],
            suggested_queries=[],
        )


@pytest.mark.asyncio
async def test_export_json_includes_citation_coverage_after_evaluator_persists_summary(monkeypatch):
    class FakeAssessor:
        def __init__(self, llm, config=None):
            pass

        def assess(self, report, scraped_content, sources=None):
            return QualityReport(
                claim_support_score=0.9,
                source_diversity_score=0.9,
                contradiction_free_score=1.0,
                citation_accuracy_score=0.9,
                citation_coverage_score=0.92,
                overall_score=0.9,
                recommendations=[],
            )

    monkeypatch.setattr(nodes, "_chat_model", lambda *args, **kwargs: _FakeEvalLLM())
    monkeypatch.setattr("agent.workflows.quality_assessor.QualityAssessor", FakeAssessor)

    state = {
        "input": "Summarize AI chip market trends",
        "final_report": "According to the annual report, the company's revenue increased in 2024.",
        "scraped_content": [],
        "sources": [],
        "deepsearch_artifacts": {
            "mode": "linear",
            "quality_summary": {"query_coverage_score": 0.75},
        },
    }

    updates = nodes.evaluator_node(state, config={})
    state.update(updates)

    checkpoint = SimpleNamespace(checkpoint={"channel_values": state})
    monkeypatch.setattr(main, "checkpointer", SimpleNamespace(get_tuple=lambda config: checkpoint))

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/export/thread-quality", params={"format": "json"})

    assert resp.status_code == 200
    payload = resp.json() or {}
    quality = payload.get("quality") or {}
    assert quality.get("query_coverage_score") == 0.75
    assert quality.get("citation_coverage") == pytest.approx(0.92)
