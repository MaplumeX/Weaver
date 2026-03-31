from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

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


class _SingleTaskPlanner(_FakePlanner):
    def create_plan(self, topic, num_queries=5, existing_knowledge="", existing_queries=None):
        return [{"query": f"{topic} aspect 1", "aspect": "aspect 1", "priority": 1}]


class _FlakyResearchAgent(_FakeResearchAgent):
    def __init__(self, _llm, search_func, config=None):
        super().__init__(_llm, search_func, config=config)
        self.calls = {}

    def execute_queries(self, queries, max_results_per_query=5):
        query = queries[0]
        self.calls[query] = self.calls.get(query, 0) + 1
        if self.calls[query] == 1:
            return []
        return super().execute_queries(queries, max_results_per_query=max_results_per_query)

    def summarize_findings(self, topic, results, existing_summary=""):
        if not results:
            return f"{topic} -> no results yet"
        return super().summarize_findings(topic, results, existing_summary=existing_summary)


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
    assert result["deep_runtime"]["engine"] == "multi_agent"
    assert result["deep_runtime"]["task_queue"]["stats"]["completed"] == queue_stats["completed"]
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


def test_multi_agent_graph_topology_exposes_role_nodes(monkeypatch):
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "ResearchPlanner", _FakePlanner)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchCoordinator", _FakeCoordinator)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: _DummyEmitter())

    runtime = multi_agent_runtime.MultiAgentDeepSearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_topology", "deepsearch_engine": "multi_agent"}},
    )
    graph = runtime.build_graph()
    mermaid = graph.get_graph(xray=True).draw_mermaid()

    assert "bootstrap" in mermaid
    assert "plan" in mermaid
    assert "dispatch" in mermaid
    assert "researcher" in mermaid
    assert "merge" in mermaid
    assert "verify" in mermaid
    assert "coordinate" in mermaid
    assert "report" in mermaid
    assert "finalize" in mermaid


def test_multi_agent_graph_can_resume_from_checkpoint(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "ResearchPlanner", _FakePlanner)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchCoordinator", _FakeCoordinator)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    config = {
        "configurable": {
            "thread_id": "thread_resume",
            "deepsearch_engine": "multi_agent",
            "deepsearch_pause_before_merge": True,
        }
    }
    runtime = multi_agent_runtime.MultiAgentDeepSearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        config,
    )
    graph = runtime.build_graph(checkpointer=MemorySaver())

    interrupted = graph.invoke(runtime.build_initial_graph_state(), config)
    assert "__interrupt__" in interrupted
    interrupt_payload = interrupted["__interrupt__"][0].value
    assert interrupt_payload["checkpoint"] == "deepsearch_merge"

    resumed = graph.invoke(Command(resume={"continue": True}), config)
    final_result = resumed["final_result"]

    assert final_result["deepsearch_runtime_state"]["graph_run_id"] == interrupt_payload["graph_run_id"]
    assert final_result["deepsearch_task_queue"]["stats"]["completed"] == 2


def test_multi_agent_runtime_retries_failed_task_without_new_task_id(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "ResearchPlanner", _SingleTaskPlanner)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FlakyResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchCoordinator", _FakeCoordinator)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    result = run_multi_agent_deepsearch(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_retry",
                "deepsearch_engine": "multi_agent",
                "deepsearch_query_num": 1,
                "deepsearch_task_retry_limit": 2,
                "deepsearch_max_epochs": 3,
            }
        },
    )

    tasks = result["deepsearch_task_queue"]["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["status"] == "completed"
    assert tasks[0]["attempts"] == 2

    task_updates = [
        data
        for name, data in emitter.emitted
        if name == "research_task_update" and data.get("task_id") == tasks[0]["id"]
    ]
    statuses = [item["status"] for item in task_updates]
    assert "failed" in statuses
    assert statuses.count("ready") >= 2
    assert statuses.count("in_progress") == 2
