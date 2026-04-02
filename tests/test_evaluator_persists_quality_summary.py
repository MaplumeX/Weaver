from types import SimpleNamespace

import agent.runtime.nodes.review as nodes
from agent.research.quality_assessor import QualityReport


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


def test_evaluator_persists_citation_coverage_into_deepsearch_artifacts(monkeypatch):
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
    monkeypatch.setattr("agent.research.quality_assessor.QualityAssessor", FakeAssessor)

    state = {
        "input": "Summarize AI chip market trends",
        "draft_report": "According to the annual report, the company's revenue increased in 2024.",
        "scraped_content": [],
        "sources": [],
        "deepsearch_artifacts": {
            "mode": "linear",
            "quality_summary": {"query_coverage_score": 0.75},
        },
    }

    result = nodes.evaluator_node(state, config={})

    artifacts = result.get("deepsearch_artifacts")
    assert isinstance(artifacts, dict), "expected evaluator to return updated deepsearch_artifacts"
    quality = artifacts.get("quality_summary")
    assert isinstance(quality, dict), "expected evaluator to persist quality_summary"
    assert quality.get("query_coverage_score") == 0.75
    assert quality.get("citation_coverage") == 0.92
