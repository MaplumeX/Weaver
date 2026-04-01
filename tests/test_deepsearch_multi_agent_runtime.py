from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import agent.workflows.deepsearch_multi_agent as multi_agent_runtime
import agent.runtime.deep.multi_agent.graph as multi_agent_graph
from agent.workflows.agents.supervisor import SupervisorAction, SupervisorDecision
from agent.workflows.deepsearch_multi_agent import run_multi_agent_deepsearch


class _DummyEmitter:
    def __init__(self):
        self.emitted = []

    def emit_sync(self, event_type, data):
        name = event_type.value if hasattr(event_type, "value") else str(event_type)
        self.emitted.append((name, data))


def _default_plan(topic):
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


class _FakeSupervisor:
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
        return _default_plan(topic)

    def refine_plan(self, topic, gaps, existing_queries, num_queries=3, approved_scope=None):
        return []

    def decide_next_action(self, **kwargs):
        if kwargs.get("retry_task_ids"):
            return SupervisorDecision(
                action=SupervisorAction.RETRY_BRANCH,
                reasoning="retry branch",
                retry_task_ids=list(kwargs.get("retry_task_ids") or []),
                request_ids=list(kwargs.get("request_ids") or []),
            )
        if int(kwargs.get("ready_task_count") or 0) > 0:
            return SupervisorDecision(
                action=SupervisorAction.DISPATCH,
                reasoning="dispatch ready branches",
                request_ids=list(kwargs.get("request_ids") or []),
            )
        return SupervisorDecision(
            action=SupervisorAction.REPORT,
            reasoning="evidence is sufficient",
            request_ids=list(kwargs.get("request_ids") or []),
        )


class _FakeClarifyAgent:
    def __init__(self, _llm, _config=None):
        pass

    def assess_intake(self, topic, clarify_answers=None, clarify_history=None):
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

    def create_scope(
        self,
        topic,
        intake_summary=None,
        previous_scope=None,
        scope_feedback="",
        clarify_transcript=None,
    ):
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


class _FakeReporter:
    def __init__(self, _llm, _config=None):
        pass

    def generate_report(self, topic, findings, sources):
        lines = "\n".join(f"- {source}" for source in sources)
        return f"# {topic}\n\n" + "\n".join(findings) + f"\n\n参考来源\n{lines}"

    def generate_executive_summary(self, report, topic):
        return f"{topic} executive summary"


class _StrictReporter(_FakeReporter):
    def generate_report(self, topic, findings, sources):
        raise AssertionError(f"reporter fallback should not run for {topic}")

    def generate_executive_summary(self, report, topic):
        raise AssertionError(f"reporter fallback should not run for {topic}")


class _SingleTaskSupervisor(_FakeSupervisor):
    def create_plan(
        self,
        topic,
        num_queries=5,
        existing_knowledge="",
        existing_queries=None,
        approved_scope=None,
    ):
        return _default_plan(topic)[:1]


class _BudgetAwareSupervisor(_FakeSupervisor):
    def decide_next_action(self, **kwargs):
        if kwargs.get("budget_stop_reason"):
            return SupervisorDecision(
                action=SupervisorAction.REPORT,
                reasoning="stop after budget exhaustion",
                request_ids=list(kwargs.get("request_ids") or []),
            )
        return super().decide_next_action(**kwargs)


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
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
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
    assert len(artifact_store["coordination_requests"]) >= 1
    assert len(artifact_store["submissions"]) >= 4
    assert len(artifact_store["supervisor_decisions"]) >= 2
    assert len(artifact_store["report_section_drafts"]) == 2
    assert result["deepsearch_runtime_state"]["engine"] == "multi_agent"
    assert result["deepsearch_runtime_state"]["last_verification_summary"]["verified_branches"] == 2
    assert result["deepsearch_runtime_state"]["supervisor_phase"] == "loop_decision"
    assert {"clarify", "scope", "supervisor", "researcher", "verifier", "reporter"} <= agent_roles
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
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
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
    assert "supervisor_plan" in mermaid
    assert "dispatch" in mermaid
    assert "researcher" in mermaid
    assert "merge" in mermaid
    assert "verify" in mermaid
    assert "supervisor_decide" in mermaid
    assert "report" in mermaid
    assert "finalize" in mermaid


def test_multi_agent_graph_can_resume_from_checkpoint(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
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
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
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
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FlakyResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
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
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
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


def test_supervisor_plan_waits_for_scope_approval_before_dispatch(monkeypatch):
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: _DummyEmitter())

    runtime = multi_agent_runtime.MultiAgentDeepSearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_plan_gate", "deepsearch_engine": "multi_agent"}},
    )

    blocked = runtime._supervisor_plan_node(runtime.build_initial_graph_state())
    assert blocked["next_step"] == "scope_review"

    approved_state = runtime.build_initial_graph_state()
    approved_state["runtime_state"]["approved_scope_draft"] = {
        "id": "scope-1",
        "version": 1,
        "status": "approved",
        "research_goal": "Research AI chips",
    }
    dispatched = runtime._supervisor_plan_node(approved_state)

    assert dispatched["next_step"] == "dispatch"
    assert dispatched["task_queue"]["stats"]["ready"] == 1
    assert dispatched["runtime_state"]["supervisor_phase"] == "initial_plan"


def test_multi_agent_runtime_uses_tool_agent_paths_when_enabled(monkeypatch):
    emitter = _DummyEmitter()
    bounded_roles = []

    def _fake_run_bounded_tool_agent(session, **_kwargs):
        bounded_roles.append((session.role, session.task.id if session.task else None))
        if session.role == "researcher":
            session.search_results.append(
                {
                    "title": "tool-agent result",
                    "url": "https://example.com/tool-agent",
                    "summary": "tool-agent summary",
                    "raw_excerpt": "tool-agent raw excerpt",
                    "provider": "fake",
                }
            )
            session._ensure_extracted_result(session.search_results[0])
            session.submit_research_bundle(
                summary="tool-agent branch summary",
                findings=["tool-agent finding"],
            )
        elif session.role == "verifier":
            validation_stage = "claim_check"
            if session.task and session.task.stage == "coverage_check":
                validation_stage = "coverage_check"
            session.submit_verification_bundle(
                validation_stage=validation_stage,
                outcome="passed",
                summary=f"{validation_stage} passed",
                recommended_action="report",
            )
        elif session.role == "reporter":
            session.submit_report_bundle(
                report_markdown="# AI chips\n\nTool-agent report",
                executive_summary="tool-agent summary",
                citation_urls=["https://example.com/tool-agent"],
            )
        return {"response": {}, "text": "", "tool_names": ["fabric_get_task"]}

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _StrictReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)
    monkeypatch.setattr(multi_agent_graph, "run_bounded_tool_agent", _fake_run_bounded_tool_agent)

    result = run_multi_agent_deepsearch(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_tool_agents",
                "deepsearch_engine": "multi_agent",
                "deepsearch_query_num": 1,
                "deepsearch_use_tool_agents": True,
            }
        },
    )

    assert result["deepsearch_artifact_store"]["final_report"]["executive_summary"] == "tool-agent summary"
    assert {role for role, _task_id in bounded_roles} >= {"researcher", "verifier", "reporter"}
    assert any(
        item["submission_kind"] == "report_bundle"
        for item in result["deepsearch_artifact_store"]["submissions"]
    )


def test_multi_agent_dispatch_stops_when_search_budget_is_exhausted(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _BudgetAwareSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    result = run_multi_agent_deepsearch(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_budget_stop",
                "deepsearch_engine": "multi_agent",
                "deepsearch_query_num": 2,
                "deepsearch_tree_max_searches": 1,
            }
        },
    )

    assert result["deepsearch_runtime_state"]["budget_stop_reason"] == "search_budget_exceeded"
    assert result["deepsearch_task_queue"]["stats"]["completed"] == 1
    assert result["deepsearch_task_queue"]["stats"]["ready"] == 1
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "dispatch" in decision_types
    assert "budget_stop" in decision_types


def test_multi_agent_runtime_honors_max_epochs_even_if_supervisor_wants_dispatch(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    result = run_multi_agent_deepsearch(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_max_epochs_stop",
                "deepsearch_engine": "multi_agent",
                "deepsearch_query_num": 2,
                "deepsearch_max_epochs": 1,
                "tree_parallel_branches": 1,
            }
        },
    )

    assert result["deepsearch_runtime_state"]["current_iteration"] == 1
    assert result["deepsearch_task_queue"]["stats"]["completed"] == 1
    assert result["deepsearch_task_queue"]["stats"]["ready"] == 1
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "research" in decision_types
    assert "report" in decision_types


def test_multi_agent_resume_preserves_clarify_history_into_scope(monkeypatch):
    emitter = _DummyEmitter()
    clarify_calls = []
    scope_calls = []

    class _ClarifyWithFollowUp:
        def __init__(self, _llm, _config=None):
            pass

        def assess_intake(self, topic, clarify_answers=None, clarify_history=None):
            clarify_calls.append(
                {
                    "topic": topic,
                    "clarify_answers": list(clarify_answers or []),
                    "clarify_history": list(clarify_history or []),
                }
            )
            if not clarify_answers:
                return {
                    "needs_clarification": True,
                    "question": "What time range should the research cover?",
                    "missing_information": ["time_range"],
                    "intake_summary": {
                        "research_goal": f"Research {topic}",
                        "background": f"Known context for {topic}",
                        "constraints": [],
                        "time_range": "",
                        "source_preferences": [],
                        "exclusions": [],
                    },
                }
            return {
                "needs_clarification": False,
                "question": "",
                "missing_information": [],
                "intake_summary": {
                    "research_goal": f"Research {topic}",
                    "background": f"Known context for {topic}",
                    "constraints": [],
                    "time_range": clarify_answers[-1],
                    "source_preferences": [],
                    "exclusions": [],
                },
            }

    class _ScopeCapture(_FakeScopeAgent):
        def create_scope(
            self,
            topic,
            intake_summary=None,
            previous_scope=None,
            scope_feedback="",
            clarify_transcript=None,
        ):
            scope_calls.append(list(clarify_transcript or []))
            return super().create_scope(
                topic,
                intake_summary=intake_summary,
                previous_scope=previous_scope,
                scope_feedback=scope_feedback,
                clarify_transcript=clarify_transcript,
            )

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _ClarifyWithFollowUp)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _ScopeCapture)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    config = {
        "configurable": {
            "thread_id": "thread_clarify_scope_context",
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
    assert first_prompt["checkpoint"] == "deepsearch_clarify"

    second = graph.invoke(
        Command(resume={"clarify_answer": "Only 2024 annual filings"}),
        config,
    )
    assert "__interrupt__" in second
    second_prompt = second["__interrupt__"][0].value
    assert second_prompt["checkpoint"] == "deepsearch_scope_review"

    assert len(clarify_calls) >= 3
    assert clarify_calls[0]["clarify_history"] == []
    assert clarify_calls[1]["clarify_history"] == []
    assert clarify_calls[-1]["clarify_history"] == [
        {
            "question": "What time range should the research cover?",
            "answer": "Only 2024 annual filings",
        }
    ]
    assert scope_calls == [
        [
            {
                "question": "What time range should the research cover?",
                "answer": "Only 2024 annual filings",
            }
        ]
    ]
