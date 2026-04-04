import json
from types import SimpleNamespace

from agent.runtime.deep.roles.researcher import ResearchAgent
from agent.runtime.deep.schema import ResearchTask
from tools.research.models import FetchedPage


class _StubLLM:
    def __init__(self, payload):
        self.payload = payload

    def invoke(self, _messages, config=None):
        return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))


class _FakeFetcher:
    def __init__(self, pages):
        self.pages = pages

    def fetch_many(self, urls):
        return list(self.pages)


def _task():
    return ResearchTask(
        id="task_1",
        goal="Research AI chips",
        query="AI chips market share",
        priority=1,
        objective="Understand the current state of AI chips market share",
        query_hints=["AI chips market share"],
        acceptance_criteria=["Explain the current state of AI chips market share"],
        title="AI chips market share",
    )


def test_research_agent_builds_authoritative_documents_and_passages():
    def fake_search(payload, config=None):
        return [
            {
                "title": "Market Report",
                "url": "https://example.com/report",
                "summary": "Search summary",
                "raw_excerpt": "Search raw excerpt",
                "score": 0.82,
                "provider": "fake",
                "published_date": "2026-04-01",
            }
        ]

    fetcher = _FakeFetcher(
        [
            FetchedPage(
                url="https://example.com/report",
                raw_url="https://example.com/report?utm=test",
                method="direct_http",
                text="AI chips market share increased in cloud training workloads.",
                markdown="# Highlights\n\nAI chips market share increased in cloud training workloads.",
                title="Market Report",
                published_date="2026-04-01",
                retrieved_at="2026-04-04T00:00:00+00:00",
                http_status=200,
            )
        ]
    )
    llm = _StubLLM(
        {
            "summary": "Cloud training workloads continue to concentrate AI chip demand.",
            "key_findings": ["Cloud training demand remains concentrated."],
            "open_questions": ["Consumer edge share is still unclear."],
            "confidence_note": "Evidence is limited to one authoritative page.",
        }
    )

    agent = ResearchAgent(llm, fake_search, {}, fetcher=fetcher)
    outcome = agent.research_branch(_task(), topic="AI chips", max_results_per_query=3)

    assert outcome["documents"]
    assert outcome["documents"][0]["method"] == "direct_http"
    assert outcome["documents"][0]["authoritative"] is True
    assert outcome["passages"]
    assert outcome["passages"][0]["authoritative"] is True
    assert outcome["passages"][0]["heading_path"] == ["Highlights"]
    assert outcome["summary"] == "Cloud training workloads continue to concentrate AI chip demand."
    assert outcome["key_findings"] == ["Cloud training demand remains concentrated."]


def test_research_agent_falls_back_to_non_authoritative_search_snippets_when_fetch_fails():
    def fake_search(payload, config=None):
        return [
            {
                "title": "Search Result",
                "url": "https://example.com/snippet",
                "summary": "Snippet-only evidence about AI chips market share.",
                "raw_excerpt": "Snippet-only evidence about AI chips market share.",
                "score": 0.61,
                "provider": "fake",
            }
        ]

    llm = _StubLLM(
        {
            "summary": "Current branch evidence is snippet-only and still weak.",
            "key_findings": ["Only snippet-level evidence is available."],
            "open_questions": ["Need authoritative primary sources."],
            "confidence_note": "No fetched pages available.",
        }
    )
    agent = ResearchAgent(llm, fake_search, {}, fetcher=_FakeFetcher([]))

    outcome = agent.research_branch(_task(), topic="AI chips", max_results_per_query=3)

    assert outcome["documents"]
    assert outcome["documents"][0]["method"] == "search_result"
    assert outcome["documents"][0]["authoritative"] is False
    assert outcome["passages"]
    assert outcome["passages"][0]["authoritative"] is False
    assert outcome["passages"][0]["admissible"] is False
