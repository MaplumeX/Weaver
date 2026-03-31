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

    def create_plan(
        self,
        topic,
        num_queries=5,
        existing_knowledge="",
        existing_queries=None,
        approved_scope=None,
    ):
        return [
            {
                "title": f"{topic} branch 1",
                "objective": f"Understand the current state of {topic} aspect 1",
                "task_kind": "branch_research",
                "aspect": "aspect 1",
                "acceptance_criteria": [f"Explain the current state of {topic} aspect 1"],
                "allowed_tools": ["search", "read", "extract", "synthesize"],
                "query_hints": [f"{topic} aspect 1"],
                "priority": 1,
            },
            {
                "title": f"{topic} branch 2",
                "objective": f"Understand the current state of {topic} aspect 2",
                "task_kind": "branch_research",
                "aspect": "aspect 2",
                "acceptance_criteria": [f"Explain the current state of {topic} aspect 2"],
                "allowed_tools": ["search", "read", "extract", "synthesize"],
                "query_hints": [f"{topic} aspect 2"],
                "priority": 2,
            },
        ]

    def refine_plan(self, topic, gaps, existing_queries, num_queries=3, approved_scope=None):
        return []


class _FakeClarifyAgent:
    def __init__(self, _llm, _config=None):
        pass

    def assess_intake(self, topic, clarify_answers=None):
        return {
            "needs_clarification": False,
            "question": "",
            "missing_information": [],
            "intake_summary": {
                "research_goal": f"Research {topic}",
                "background": f"Known context for {topic}",
                "constraints": [],
                "time_range": "",
                "source_preferences": [],
                "exclusions": [],
            },
        }


class _FakeScopeAgent:
    def __init__(self, _llm, _config=None):
        pass

    def create_scope(self, topic, intake_summary=None, previous_scope=None, scope_feedback=""):
        previous_scope = previous_scope or {}
        if scope_feedback and previous_scope:
            base_questions = list(previous_scope.get("core_questions") or [])
            return {
                "research_goal": previous_scope.get("research_goal") or f"Research {topic}",
                "research_steps": [
                    f"Refocus the research around the revision request: {scope_feedback}",
                    f"Re-check the most important evidence about {topic}",
                    "Update the final research framing before planning",
                ],
                "core_questions": base_questions or [f"What matters most about {topic}?"],
                "in_scope": (previous_scope.get("in_scope") or [f"{topic} market and roadmap"]) + [scope_feedback],
                "out_of_scope": previous_scope.get("out_of_scope") or [],
                "constraints": previous_scope.get("constraints") or [],
                "source_preferences": previous_scope.get("source_preferences") or [],
                "deliverable_preferences": [],
                "assumptions": [scope_feedback],
            }
        return {
            "research_goal": intake_summary.get("research_goal") or f"Research {topic}",
            "research_steps": [
                f"Collect the latest evidence about the current state of {topic}",
                f"Break down the most important questions and trade-offs in {topic}",
                "Synthesize the findings into a research-ready outline",
            ],
            "core_questions": [f"What is the current state of {topic}?", f"What are the key trade-offs in {topic}?"],
            "in_scope": [f"{topic} market and roadmap", f"{topic} ecosystem"],
            "out_of_scope": ["unrelated consumer gadgets"],
            "constraints": intake_summary.get("constraints") or [],
            "source_preferences": intake_summary.get("source_preferences") or [],
            "deliverable_preferences": ["Comparative report"],
            "assumptions": [],
        }


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
    def create_plan(
        self,
        topic,
        num_queries=5,
        existing_knowledge="",
        existing_queries=None,
        approved_scope=None,
    ):
        return [
            {
                "title": f"{topic} branch 1",
                "objective": f"Understand the current state of {topic} aspect 1",
                "task_kind": "branch_research",
                "aspect": "aspect 1",
                "acceptance_criteria": [f"Explain the current state of {topic} aspect 1"],
                "allowed_tools": ["search", "read", "extract", "synthesize"],
                "query_hints": [f"{topic} aspect 1"],
                "priority": 1,
            }
        ]


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
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
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
    assert len(artifact_store["branch_briefs"]) >= 3
    assert len(artifact_store["source_candidates"]) == 2
    assert len(artifact_store["fetched_documents"]) == 2
    assert len(artifact_store["evidence_passages"]) == 2
    assert len(artifact_store["evidence_cards"]) == 2
    assert len(artifact_store["branch_syntheses"]) == 2
    assert len(artifact_store["verification_results"]) == 4
    assert len(artifact_store["report_section_drafts"]) == 2
    assert result["deepsearch_runtime_state"]["engine"] == "multi_agent"
    assert result["deepsearch_runtime_state"]["last_verification_summary"]["verified_branches"] == 2
    assert {"clarify", "scope", "planner", "researcher", "verifier", "coordinator", "reporter"} <= agent_roles
    assert "research_agent_start" in event_types
    assert "research_task_update" in event_types
    assert "research_artifact_update" in event_types
    assert "research_decision" in event_types
    assert "research_node_complete" in event_types

    task_updates = [data for name, data in emitter.emitted if name == "research_task_update"]
    assert any(update.get("task_kind") == "branch_research" for update in task_updates)
    assert any(update.get("stage") == "search" for update in task_updates)
    assert any(update.get("stage") == "synthesize" for update in task_updates)

    artifact_updates = [data for name, data in emitter.emitted if name == "research_artifact_update"]
    assert any(update.get("artifact_type") == "branch_synthesis" for update in artifact_updates)
    assert any(
        update.get("artifact_type") == "verification_result"
        and update.get("validation_stage") == "coverage_check"
        for update in artifact_updates
    )


def test_multi_agent_graph_topology_exposes_role_nodes(monkeypatch):
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
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
    assert "clarify" in mermaid
    assert "scope" in mermaid
    assert "scope_review" in mermaid
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
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
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

    resume_config = {
        "configurable": {
            **config["configurable"],
            "resumed_from_checkpoint": True,
        }
    }
    resumed = graph.invoke(Command(resume={"continue": True}), resume_config)
    final_result = resumed["final_result"]

    assert final_result["deepsearch_runtime_state"]["graph_run_id"] == interrupt_payload["graph_run_id"]
    assert final_result["deepsearch_task_queue"]["stats"]["completed"] == 2
    assert final_result["deepsearch_runtime_state"]["last_verification_summary"]["verified_branches"] == 2


def test_multi_agent_events_include_resume_flag_when_configured(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchPlanner", _SingleTaskPlanner)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchCoordinator", _FakeCoordinator)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    run_multi_agent_deepsearch(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_resume_flag",
                "deepsearch_engine": "multi_agent",
                "deepsearch_query_num": 1,
                "resumed_from_checkpoint": True,
            }
        },
    )

    research_events = [
        data
        for name, data in emitter.emitted
        if name
        in {
            "research_agent_start",
            "research_agent_complete",
            "research_task_update",
            "research_artifact_update",
            "research_decision",
        }
    ]

    assert research_events
    assert all(event.get("resumed_from_checkpoint") is True for event in research_events)


def test_multi_agent_runtime_retries_failed_task_without_new_task_id(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
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
    dispatch_updates = [
        item
        for item in task_updates
        if item["status"] == "in_progress" and item.get("stage") == "dispatch"
    ]
    assert len(dispatch_updates) == 2


def test_multi_agent_scope_review_supports_revision_then_approval(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchPlanner", _SingleTaskPlanner)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchCoordinator", _FakeCoordinator)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    config = {
        "configurable": {
            "thread_id": "thread_scope_review",
            "deepsearch_engine": "multi_agent",
            "allow_interrupts": True,
            "deepsearch_query_num": 1,
        }
    }
    runtime = multi_agent_runtime.MultiAgentDeepSearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        config,
    )
    graph = runtime.build_graph(checkpointer=MemorySaver())

    first = graph.invoke(runtime.build_initial_graph_state(), config)
    assert "__interrupt__" in first
    first_prompt = first["__interrupt__"][0].value
    assert first_prompt["checkpoint"] == "deepsearch_scope_review"
    assert first_prompt["scope_version"] == 1
    assert "1. Collect the latest evidence about the current state of AI chips" in first_prompt["content"]
    assert "## Core Questions" not in first_prompt["content"]

    second = graph.invoke(
        Command(resume={"action": "revise_scope", "scope_feedback": "Focus on supply chain resilience"}),
        config,
    )
    assert "__interrupt__" in second
    second_prompt = second["__interrupt__"][0].value
    assert second_prompt["checkpoint"] == "deepsearch_scope_review"
    assert second_prompt["scope_version"] == 2
    assert second_prompt["graph_run_id"] == first_prompt["graph_run_id"]
    assert "1. Refocus the research around the revision request: Focus on supply chain resilience" in second_prompt["content"]

    resumed = graph.invoke(Command(resume={"action": "approve_scope"}), config)
    final_result = resumed["final_result"]
    runtime_state = final_result["deepsearch_runtime_state"]

    assert runtime_state["scope_revision_count"] == 1
    assert runtime_state["approved_scope_draft"]["version"] == 2
    assert runtime_state["approved_scope_draft"]["status"] == "approved"
    assert final_result["deepsearch_task_queue"]["stats"]["completed"] == 1

    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "scope_revision_requested" in decision_types
    assert "scope_approved" in decision_types
