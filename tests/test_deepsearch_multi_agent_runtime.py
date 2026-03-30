import agent.workflows.deepsearch_multi_agent as multi_agent_runtime
from agent.workflows.agents.coordinator import CoordinatorAction, CoordinatorDecision
from agent.workflows.deepsearch_multi_agent import run_multi_agent_deepsearch


class _DummyEmitter:
    def __init__(self):
        self.emitted = []

    def emit_sync(self, event_type, data):
        name = event_type.value if hasattr(event_type, "value") else str(event_type)
        self.emitted.append((name, data))


class _FakePlanner:
    def __init__(self, _llm, _config=None):
        pass

    def create_plan(self, topic, num_queries=5, existing_knowledge="", existing_queries=None):
        return [
            {"query": f"{topic} aspect 1", "aspect": "aspect 1", "priority": 1},
            {"query": f"{topic} aspect 2", "aspect": "aspect 2", "priority": 2},
        ]

    def refine_plan(self, topic, gaps, existing_queries, num_queries=3):
        return []


class _FakeResearchAgent:
    def __init__(self, _llm, search_func, config=None):
        self.search_func = search_func

    def execute_queries(self, queries, max_results_per_query=5):
        results = []
        for query in queries:
            results.append(
                {
                    "title": f"{query} result",
                    "url": f"https://example.com/{query.replace(' ', '-')}",
                    "summary": f"{query} summary",
                    "raw_excerpt": f"{query} raw excerpt",
                    "provider": "fake",
                }
            )
        return results

    def summarize_findings(self, topic, results, existing_summary=""):
        return f"{topic} -> {results[0]['title']}"


class _FakeVerifier:
    def __init__(self, _llm, _config=None):
        pass

    def analyze(self, topic, executed_queries, collected_knowledge):
        return multi_agent_runtime.GapAnalysisResult.from_dict(
            {
                "overall_coverage": 0.92,
                "confidence": 0.88,
                "gaps": [],
                "suggested_queries": [],
                "covered_aspects": ["aspect 1", "aspect 2"],
                "analysis": "coverage is sufficient",
            }
        )


class _FakeCoordinator:
    def __init__(self, _llm, config=None):
        pass

    def decide_next_action(self, **kwargs):
        return CoordinatorDecision(
            action=CoordinatorAction.COMPLETE,
            reasoning="evidence is sufficient",
            priority_topics=[],
        )


class _FakeReporter:
    def __init__(self, _llm, _config=None):
        pass

    def generate_report(self, topic, findings, sources):
        lines = "\n".join(f"- {source}" for source in sources)
        return f"# {topic}\n\n" + "\n".join(findings) + f"\n\n参考来源\n{lines}"

    def generate_executive_summary(self, report, topic):
        return f"{topic} executive summary"


def test_run_multi_agent_deepsearch_merges_artifacts_and_emits_events(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "ResearchPlanner", _FakePlanner)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchCoordinator", _FakeCoordinator)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    result = run_multi_agent_deepsearch(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_test",
                "deepsearch_engine": "multi_agent",
                "deepsearch_query_num": 2,
                "deepsearch_results_per_query": 2,
            }
        },
    )

    queue_stats = result["deepsearch_task_queue"]["stats"]
    artifact_store = result["deepsearch_artifact_store"]
    event_types = [name for name, _ in emitter.emitted]
    agent_roles = {run["role"] for run in result["deepsearch_agent_runs"]}

    assert result["deepsearch_engine"] == "multi_agent"
    assert queue_stats["completed"] == 2
    assert len(artifact_store["evidence_cards"]) == 2
    assert len(artifact_store["report_section_drafts"]) == 2
    assert result["deepsearch_runtime_state"]["engine"] == "multi_agent"
    assert {"planner", "researcher", "verifier", "coordinator", "reporter"} <= agent_roles
    assert "research_agent_start" in event_types
    assert "research_task_update" in event_types
    assert "research_artifact_update" in event_types
    assert "research_decision" in event_types
    assert "research_node_complete" in event_types
