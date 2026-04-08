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


class _RoutingLLM:
    def __init__(self):
        self.refine_calls = 0

    def invoke(self, messages, config=None):
        prompt = str(messages[0].content if messages else "")
        if "研究查询优化员" in prompt:
            self.refine_calls += 1
            payload = (
                {
                    "queries": ["AI chips production inference serving expansion official"],
                    "reasoning": "补齐 production inference serving expansion 相关证据",
                }
                if self.refine_calls == 1
                else {"queries": [], "reasoning": "当前已覆盖主要缺口"}
            )
            return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        if "证据优先的研究员" in prompt:
            payload = {
                "summary": "Cloud training 与 inference deployment 两类场景都在推动 AI chips 市场份额变化。",
                "key_findings": [
                    "Cloud training 仍是当前市场份额的重要来源。",
                    "Inference deployment 的市场份额正在扩大。",
                ],
                "open_questions": [],
                "confidence_note": "结论基于两份权威页面。",
            }
            return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        if "证据绑定分析员" in prompt:
            return SimpleNamespace(content=json.dumps({"claims": []}, ensure_ascii=False))
        return SimpleNamespace(content="{}")


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
    assert outcome["coverage_summary"]["coverage_ready"] is True
    assert outcome["quality_summary"]["quality_ready"] is True
    assert outcome["grounding_summary"]["grounding_ready"] is True
    assert outcome["branch_artifacts"]["coverage"]["coverage_ready"] is True
    assert outcome["branch_artifacts"]["quality"]["quality_ready"] is True
    assert outcome["branch_artifacts"]["query_rounds"]
    assert outcome["research_decisions"][-1]["action"] == "synthesize"


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


def test_research_agent_runs_bounded_multi_round_loop_until_coverage_is_met():
    def fake_search(payload, config=None):
        query = payload["query"]
        if query == "AI chips market share":
            return [
                {
                    "title": "Cloud Training Share",
                    "url": "https://cloud.example.com/report",
                    "summary": "Cloud training workload concentration keeps rising.",
                    "raw_excerpt": "Cloud training workload concentration keeps rising.",
                    "score": 0.88,
                    "provider": "fake",
                    "published_date": "2026-04-01",
                }
            ]
        if query == "AI chips production inference serving expansion official":
            return [
                {
                    "title": "Inference Deployment Share",
                    "url": "https://deployment.example.org/report",
                    "summary": "Production inference serving expansion keeps accelerating.",
                    "raw_excerpt": "Production inference serving expansion keeps accelerating.",
                    "score": 0.84,
                    "provider": "fake",
                    "published_date": "2026-04-02",
                }
            ]
        return []

    fetcher = _FakeFetcher(
        [
            FetchedPage(
                url="https://cloud.example.com/report",
                raw_url="https://cloud.example.com/report",
                method="direct_http",
                text="Cloud training workload concentration remains the dominant driver for AI chips demand.",
                markdown="# Cloud\n\nCloud training workload concentration remains the dominant driver for AI chips demand.",
                title="Cloud Training Share",
                published_date="2026-04-01",
                retrieved_at="2026-04-04T00:00:00+00:00",
                http_status=200,
            ),
            FetchedPage(
                url="https://deployment.example.org/report",
                raw_url="https://deployment.example.org/report",
                method="direct_http",
                text="Production inference serving expansion is accelerating as deployment volumes grow.",
                markdown="# Deployment\n\nProduction inference serving expansion is accelerating as deployment volumes grow.",
                title="Inference Deployment Share",
                published_date="2026-04-02",
                retrieved_at="2026-04-04T00:00:00+00:00",
                http_status=200,
            ),
        ]
    )
    task = ResearchTask(
        id="task_multi_round",
        goal="Research AI chips",
        query="AI chips market share",
        priority=1,
        objective="Compare cloud training and inference deployment market share",
        query_hints=["AI chips market share"],
        acceptance_criteria=[
            "Cloud training workload concentration",
            "Production inference serving expansion",
        ],
        coverage_targets=[
            "Cloud training workload concentration",
            "Production inference serving expansion",
        ],
        title="AI chips market share comparison",
    )

    agent = ResearchAgent(_RoutingLLM(), fake_search, {"configurable": {"deep_research_branch_max_rounds": 3}}, fetcher=fetcher)
    outcome = agent.research_branch(task, topic="AI chips", max_results_per_query=1)

    assert outcome["coverage_summary"]["coverage_ready"] is True
    assert outcome["coverage_summary"]["covered_count"] == 2
    assert outcome["quality_summary"]["quality_ready"] is True
    assert len(outcome["branch_artifacts"]["query_rounds"]) == 2
    assert outcome["queries"][:2] == [
        "AI chips market share",
        "AI chips Compare cloud training and inference deployment market share",
    ]
    assert "AI chips production inference serving expansion official" in outcome["queries"]
    assert outcome["research_decisions"][-1]["action"] == "synthesize"
    assert outcome["branch_artifacts"]["coverage"]["missing_count"] == 0
