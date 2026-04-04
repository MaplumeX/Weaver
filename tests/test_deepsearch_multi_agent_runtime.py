import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import agent.runtime.deep.orchestration.graph as multi_agent_runtime
from agent.core.state import build_deep_runtime_snapshot
from agent.runtime.deep.orchestration import run_multi_agent_deep_research


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


class _FakeClarifyAgent:
    def __init__(self, _llm, _config=None):
        pass

    def assess_intake(self, topic, clarify_answers=None, clarify_history=None):
        return {
            "status": "ready_for_scope",
            "follow_up_question": "",
            "blocking_slot": "none",
            "resolved_slots": {
                "goal": f"Research {topic}",
                "time_range": "",
                "source_preferences": [],
                "constraints": [],
                "exclusions": [],
                "deliverable_preferences": [],
            },
            "unresolved_slots": [],
            "asked_slots": [],
        }


class _FakeScopeAgent:
    def __init__(self, _llm, _config=None):
        pass

    def create_scope(
        self,
        topic,
        clarification_state=None,
        previous_scope=None,
        scope_feedback="",
        clarify_transcript=None,
    ):
        clarification_state = clarification_state or {}
        resolved_slots = clarification_state.get("resolved_slots") or {}
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
            "research_goal": resolved_slots.get("goal") or f"Research {topic}",
            "research_steps": [
                f"Collect the latest evidence about the current state of {topic}",
                f"Break down the most important questions and trade-offs in {topic}",
                "Synthesize the findings into a research-ready outline",
            ],
            "core_questions": [f"What is the current state of {topic}?", f"What are the key trade-offs in {topic}?"],
            "in_scope": [f"{topic} market and roadmap", f"{topic} ecosystem"],
            "out_of_scope": ["unrelated consumer gadgets"],
            "constraints": resolved_slots.get("constraints") or [],
            "source_preferences": resolved_slots.get("source_preferences") or [],
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


class _CompleteCriteriaResearchAgent(_FakeResearchAgent):
    def summarize_findings(self, topic, results, existing_summary=""):
        return f"Explain the current state of {topic} aspect 1"


class _IncompleteResearchAgent(_FakeResearchAgent):
    def summarize_findings(self, topic, results, existing_summary=""):
        return "Unrelated memo"


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


class _GapingVerifier:
    def __init__(self, _llm, _config=None):
        pass

    def analyze(self, topic, executed_queries, collected_knowledge):
        return multi_agent_runtime.GapAnalysisResult.from_dict(
            {
                "overall_coverage": 0.32,
                "confidence": 0.64,
                "gaps": [
                    {
                        "aspect": f"{topic} acceptance criteria",
                        "importance": "high",
                        "reason": "critical evidence is still missing",
                    }
                ],
                "suggested_queries": [f"{topic} follow-up evidence"],
                "covered_aspects": [],
                "analysis": "coverage is still incomplete",
            }
        )


class _EventuallyPassingVerifier:
    def __init__(self, _llm, _config=None):
        self.calls = {}

    def analyze(self, topic, executed_queries, collected_knowledge):
        self.calls[topic] = self.calls.get(topic, 0) + 1
        if self.calls[topic] == 1:
            return multi_agent_runtime.GapAnalysisResult.from_dict(
                {
                    "overall_coverage": 0.25,
                    "confidence": 0.52,
                    "gaps": [
                        {
                            "aspect": f"{topic} follow-up",
                            "importance": "high",
                            "reason": "needs another pass",
                        }
                    ],
                    "suggested_queries": [f"{topic} second pass"],
                    "covered_aspects": [],
                    "analysis": "first pass incomplete",
                }
            )
        return multi_agent_runtime.GapAnalysisResult.from_dict(
            {
                "overall_coverage": 0.91,
                "confidence": 0.86,
                "gaps": [],
                "suggested_queries": [],
                "covered_aspects": ["aspect 1"],
                "analysis": "retry closed the gap",
            }
        )


class _FakeReporter:
    def __init__(self, _llm, _config=None):
        pass

    def generate_report(self, topic_or_context, findings=None, sources=None):
        if hasattr(topic_or_context, "topic"):
            topic = topic_or_context.topic
            sections = []
            for section in topic_or_context.sections:
                section_body = section.summary
                if section.findings:
                    section_body = f"{section_body}\n\n- " + "\n- ".join(section.findings)
                sections.append(f"## {section.title}\n\n{section_body}")
            return f"# {topic}\n\n" + "\n\n".join(sections)
        topic = topic_or_context
        lines = "\n".join(f"- {source}" for source in sources or [])
        return f"# {topic}\n\n" + "\n".join(findings or []) + f"\n\n参考来源\n{lines}"

    def normalize_report(self, report, sources, title=None):
        urls = []
        for source in sources or []:
            if hasattr(source, "url") and source.url:
                urls.append(source.url)
        normalized = report
        if title and not report.lstrip().startswith("#"):
            normalized = f"# {title}\n\n{report}"
        if urls:
            normalized = normalized.rstrip() + "\n\n## 来源\n\n" + "\n".join(
                f"[{index}] {url}" for index, url in enumerate(urls, 1)
            )
        return normalized, urls

    def generate_executive_summary(self, report, topic):
        return f"{topic} executive summary"


class _ContextCheckingReporter(_FakeReporter):
    def generate_report(self, topic_or_context, findings=None, sources=None):
        assert hasattr(topic_or_context, "sections")
        assert topic_or_context.sections
        assert topic_or_context.sources
        return super().generate_report(topic_or_context, findings=findings, sources=sources)


_LIGHTWEIGHT_ARTIFACT_TYPES = {
    "scope",
    "plan",
    "evidence_bundle",
    "branch_result",
    "validation_summary",
    "final_report",
}

_BRANCH_ARTIFACT_TYPES = {"evidence_bundle", "branch_result", "validation_summary"}


def _patch_runtime_deps(
    monkeypatch,
    *,
    emitter,
    clarify=_FakeClarifyAgent,
    scope=_FakeScopeAgent,
    supervisor=_FakeSupervisor,
    researcher=_FakeResearchAgent,
    verifier=_FakeVerifier,
    reporter=_FakeReporter,
):
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", clarify)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", scope)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", supervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", researcher)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", verifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", reporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)


@pytest.fixture(autouse=True)
def _disable_tool_agents_by_default(monkeypatch):
    monkeypatch.setattr(multi_agent_runtime.settings, "deep_research_use_tool_agents", False, raising=False)


def test_run_multi_agent_deep_research_emits_lightweight_artifacts_and_events(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter)

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_test",
                "deep_research_query_num": 2,
                "deep_research_results_per_query": 2,
            }
        },
    )

    runtime = result["deep_runtime"]
    artifact_store = runtime["artifact_store"]
    public_artifacts = result["deep_research_artifacts"]
    queue_stats = runtime["task_queue"]["stats"]
    event_types = [name for name, _ in emitter.emitted]
    artifact_types = {
        data["artifact_type"]
        for name, data in emitter.emitted
        if name == "research_artifact_update"
    }
    agent_roles = {run["role"] for run in runtime["agent_runs"]}

    assert runtime["engine"] == "multi_agent"
    assert result["is_complete"] is True
    assert queue_stats["completed"] == 2
    assert set(artifact_store) == {
        "scope",
        "plan",
        "evidence_bundles",
        "branch_results",
        "validation_summaries",
        "final_report",
    }
    assert len(artifact_store["plan"]["tasks"]) == 2
    assert len(artifact_store["evidence_bundles"]) == 2
    assert len(artifact_store["branch_results"]) == 2
    assert len(artifact_store["validation_summaries"]) == 2
    assert artifact_store["final_report"]["executive_summary"] == "AI chips executive summary"
    assert public_artifacts["queries"] == ["AI chips aspect 1", "AI chips aspect 2"]
    assert len(public_artifacts["tasks"]) == 2
    assert len(public_artifacts["branch_results"]) == 2
    assert public_artifacts["validation_summary"]["passed_branch_count"] == 2
    assert public_artifacts["quality_summary"]["passed_branch_count"] == 2
    assert public_artifacts["control_plane"]["active_agent"] == "supervisor"
    assert public_artifacts["final_report"] == result["final_report"]
    assert len(result["research_topology"]["children"]) == 2
    assert {"clarify", "scope", "supervisor", "researcher", "verifier", "reporter"} <= agent_roles
    assert _LIGHTWEIGHT_ARTIFACT_TYPES <= artifact_types
    assert "research_agent_start" in event_types
    assert "research_task_update" in event_types
    assert "research_artifact_update" in event_types
    assert "research_decision" in event_types
    assert "research_node_complete" in event_types


def test_build_initial_graph_state_restores_scope_review_from_checkpoint(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_SingleTaskSupervisor)

    checkpoint_state = build_deep_runtime_snapshot(
        engine="multi_agent",
        runtime_state={
            "active_agent": "scope",
            "intake_status": "awaiting_scope_review",
            "current_scope_draft": {
                "id": "scope-1",
                "version": 2,
                "topic": "AI chips",
                "research_goal": "Research AI chips",
                "status": "awaiting_review",
            },
        },
        task_queue={},
        artifact_store={},
        agent_runs=[],
    )
    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {
            "input": "AI chips",
            "sub_agent_contexts": {},
            "deep_runtime": checkpoint_state,
        },
        {"configurable": {"thread_id": "thread_resume_owner"}},
    )

    initial_state = runtime.build_initial_graph_state()

    assert initial_state["runtime_state"]["active_agent"] == "scope"
    assert initial_state["runtime_state"]["current_scope_draft"]["id"] == "scope-1"
    assert initial_state["next_step"] == "scope_review"


def test_multi_agent_graph_topology_exposes_lightweight_role_nodes(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_topology"}},
    )
    graph = runtime.build_graph()
    mermaid = graph.get_graph(xray=True).draw_mermaid()

    assert "bootstrap" in mermaid
    assert "clarify" in mermaid
    assert "scope" in mermaid
    assert "scope_review" in mermaid
    assert "research_brief" in mermaid
    assert "supervisor_plan" in mermaid
    assert "dispatch" in mermaid
    assert "researcher" in mermaid
    assert "merge" in mermaid
    assert "verify" in mermaid
    assert "supervisor_decide" in mermaid
    assert "outline_gate" in mermaid
    assert "report" in mermaid
    assert "finalize" in mermaid


def test_multi_agent_branch_events_include_iteration_metadata(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_SingleTaskSupervisor)

    run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_iteration_metadata", "deep_research_query_num": 1}},
    )

    branch_task_updates = [
        data
        for name, data in emitter.emitted
        if name == "research_task_update" and data.get("task_kind") == "branch_research"
    ]
    branch_artifact_updates = [
        data
        for name, data in emitter.emitted
        if (
            name == "research_artifact_update"
            and data.get("artifact_type") in _BRANCH_ARTIFACT_TYPES
            and (data.get("branch_id") or data.get("task_id"))
        )
    ]

    assert branch_task_updates
    assert branch_artifact_updates
    assert all(isinstance(item.get("iteration"), int) and item["iteration"] >= 1 for item in branch_task_updates)
    assert all(isinstance(item.get("iteration"), int) and item["iteration"] >= 1 for item in branch_artifact_updates)


def test_multi_agent_graph_can_resume_from_merge_checkpoint(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter)

    config = {
        "configurable": {
            "thread_id": "thread_resume",
            "deep_research_query_num": 2,
            "deep_research_pause_before_merge": True,
        }
    }
    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        config,
    )
    graph = runtime.build_graph(checkpointer=MemorySaver())

    interrupted = graph.invoke(runtime.build_initial_graph_state(), config)
    assert "__interrupt__" in interrupted
    interrupt_payload = interrupted["__interrupt__"][0].value
    assert interrupt_payload["checkpoint"] == "deep_research_merge"

    resumed = graph.invoke(
        Command(resume={"continue": True}),
        {"configurable": {**config["configurable"], "resumed_from_checkpoint": True}},
    )
    final_result = resumed["final_result"]

    assert final_result["deep_runtime"]["runtime_state"]["graph_run_id"] == interrupt_payload["graph_run_id"]
    assert final_result["deep_runtime"]["task_queue"]["stats"]["completed"] == 2
    assert final_result["deep_runtime"]["runtime_state"]["last_verification_summary"]["passed_branch_count"] == 2
    assert final_result["final_report"].startswith("# AI chips")


def test_multi_agent_completed_snapshot_resumes_via_finalize_without_replanning(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_SingleTaskSupervisor)

    config = {"configurable": {"thread_id": "thread_resume_completed", "deep_research_query_num": 1}}
    initial_result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        config,
    )

    class _FailingSupervisor:
        def __init__(self, _llm, _config=None):
            pass

        def create_plan(self, *args, **kwargs):
            raise AssertionError("completed snapshot should not re-enter supervisor_plan")

        def refine_plan(self, *args, **kwargs):
            raise AssertionError("completed snapshot should not re-enter supervisor_plan")

    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FailingSupervisor)

    resumed_runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {
            "input": "AI chips",
            "sub_agent_contexts": {},
            "deep_runtime": initial_result["deep_runtime"],
        },
        config,
    )
    resumed = resumed_runtime.build_graph().invoke(resumed_runtime.build_initial_graph_state(), config)
    final_result = resumed["final_result"]

    assert final_result["is_complete"] is True
    assert final_result["final_report"] == initial_result["final_report"]
    assert final_result["deep_runtime"]["task_queue"]["stats"]["completed"] == 1
    assert final_result["deep_runtime"]["runtime_state"]["next_step"] == "completed"


def test_multi_agent_events_include_resume_flag_when_configured(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_SingleTaskSupervisor)

    run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_resume_flag",
                "deep_research_query_num": 1,
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
    agent_events = [
        data
        for name, data in emitter.emitted
        if name in {"research_agent_start", "research_agent_complete"}
        and data.get("role") in {"researcher", "verifier", "reporter"}
    ]
    iterated_events = [event for event in research_events if "iteration" in event]

    assert research_events
    assert all(event.get("resumed_from_checkpoint") is True for event in research_events)
    assert all(event.get("graph_run_id") for event in research_events)
    assert all(isinstance(event.get("attempt"), int) and event["attempt"] >= 1 for event in agent_events)
    assert all(isinstance(event.get("iteration"), int) and event["iteration"] >= 1 for event in iterated_events)


def test_multi_agent_runtime_retries_failed_task_without_new_task_id(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(
        monkeypatch,
        emitter=emitter,
        supervisor=_SingleTaskSupervisor,
        researcher=_FlakyResearchAgent,
    )

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_retry_failure",
                "deep_research_query_num": 1,
                "deep_research_task_retry_limit": 2,
                "deep_research_max_epochs": 3,
            }
        },
    )

    tasks = result["deep_runtime"]["task_queue"]["tasks"]
    task_updates = [
        data
        for name, data in emitter.emitted
        if name == "research_task_update" and data.get("task_id") == tasks[0]["id"]
    ]
    statuses = [item["status"] for item in task_updates]
    dispatch_updates = [
        item
        for item in task_updates
        if item["status"] == "in_progress" and item.get("stage") == "dispatch"
    ]

    assert len(tasks) == 1
    assert tasks[0]["status"] == "completed"
    assert tasks[0]["attempts"] == 2
    assert result["deep_runtime"]["artifact_store"]["validation_summaries"][0]["status"] == "passed"
    assert "failed" in statuses
    assert statuses.count("ready") >= 2
    assert {item["attempt"] for item in dispatch_updates} == {1, 2}


def test_multi_agent_scope_review_supports_revision_then_approval(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_SingleTaskSupervisor)

    config = {
        "configurable": {
            "thread_id": "thread_scope_review",
            "allow_interrupts": True,
            "deep_research_query_num": 1,
        }
    }
    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        config,
    )
    graph = runtime.build_graph(checkpointer=MemorySaver())

    first = graph.invoke(runtime.build_initial_graph_state(), config)
    assert "__interrupt__" in first
    first_prompt = first["__interrupt__"][0].value
    assert first_prompt["checkpoint"] == "deep_research_scope_review"
    assert first_prompt["scope_version"] == 1
    assert "current state of AI chips" in first_prompt["content"]

    second = graph.invoke(
        Command(resume={"action": "revise_scope", "scope_feedback": "Focus on supply chain resilience"}),
        config,
    )
    assert "__interrupt__" in second
    second_prompt = second["__interrupt__"][0].value
    assert second_prompt["checkpoint"] == "deep_research_scope_review"
    assert second_prompt["scope_version"] == 2
    assert second_prompt["graph_run_id"] == first_prompt["graph_run_id"]
    assert "Focus on supply chain resilience" in second_prompt["content"]

    resumed = graph.invoke(Command(resume={"action": "approve_scope"}), config)
    final_result = resumed["final_result"]
    runtime_state = final_result["deep_runtime"]["runtime_state"]
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]

    assert runtime_state["scope_revision_count"] == 1
    assert runtime_state["approved_scope_draft"]["version"] == 2
    assert runtime_state["approved_scope_draft"]["status"] == "approved"
    assert final_result["deep_runtime"]["task_queue"]["stats"]["completed"] == 1
    assert "scope_revision_requested" in decision_types
    assert "scope_approved" in decision_types


def test_supervisor_plan_waits_for_scope_approval_before_dispatch(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_SingleTaskSupervisor)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_plan_gate"}},
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
    gated = runtime._supervisor_plan_node(approved_state)
    assert gated["next_step"] == "research_brief"

    brief_state = runtime._research_brief_node(approved_state)
    dispatched = runtime._supervisor_plan_node(brief_state)

    assert dispatched["next_step"] == "dispatch"
    assert dispatched["task_queue"]["stats"]["ready"] == 1
    assert dispatched["runtime_state"]["supervisor_phase"] == "initial_plan"


def test_multi_agent_runtime_retries_validation_until_branch_passes(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(
        monkeypatch,
        emitter=emitter,
        supervisor=_SingleTaskSupervisor,
        researcher=_IncompleteResearchAgent,
        verifier=_EventuallyPassingVerifier,
    )

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_validation_retry",
                "deep_research_query_num": 1,
                "deep_research_task_retry_limit": 3,
                "deep_research_max_epochs": 3,
            }
        },
    )

    runtime = result["deep_runtime"]
    tasks = runtime["task_queue"]["tasks"]
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]

    assert tasks[0]["status"] == "completed"
    assert tasks[0]["attempts"] == 2
    assert runtime["artifact_store"]["validation_summaries"][0]["status"] == "passed"
    assert runtime["runtime_state"]["last_verification_summary"]["passed_branch_count"] == 1
    assert runtime["runtime_state"]["last_verification_summary"]["retry_branch_count"] == 0
    assert "retry_branch" in decision_types


def test_multi_agent_runtime_allows_advisory_gaps_without_blocking_report(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(
        monkeypatch,
        emitter=emitter,
        supervisor=_SingleTaskSupervisor,
        researcher=_CompleteCriteriaResearchAgent,
        verifier=_GapingVerifier,
        reporter=_ContextCheckingReporter,
    )

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_advisory_gaps_non_blocking",
                "deep_research_query_num": 1,
                "deep_research_max_epochs": 1,
                "deep_research_parallel_workers": 1,
            }
        },
    )

    runtime = result["deep_runtime"]
    validation = runtime["artifact_store"]["validation_summaries"][0]
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]

    assert result["is_complete"] is True
    assert validation["status"] == "passed"
    assert validation["status_reason"] == "advisory_only"
    assert runtime["runtime_state"]["last_verification_summary"]["advisory_gap_count"] == 1
    assert "## 来源" in runtime["artifact_store"]["final_report"]["report_markdown"]
    assert "[1]" in runtime["artifact_store"]["final_report"]["report_markdown"]
    assert "verification_passed" in decision_types
    assert "report" in decision_types


def test_multi_agent_dispatch_records_budget_stop_reason_when_search_budget_exhausted(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter)

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_budget_stop",
                "deep_research_query_num": 2,
                "deep_research_parallel_workers": 1,
                "deep_research_max_searches": 1,
            }
        },
    )

    runtime = result["deep_runtime"]
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]

    assert runtime["runtime_state"]["budget_stop_reason"] == "search_budget_exceeded"
    assert runtime["task_queue"]["stats"]["completed"] == 1
    assert runtime["task_queue"]["stats"]["ready"] == 1
    assert result["deep_research_artifacts"]["quality_summary"]["budget_stop_reason"] == "search_budget_exceeded"
    assert "budget_stop" in decision_types
    assert "report" in decision_types


def test_multi_agent_runtime_honors_max_epochs_even_with_ready_tasks(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter)

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_max_epochs_stop",
                "deep_research_query_num": 2,
                "deep_research_max_epochs": 1,
                "deep_research_parallel_workers": 1,
            }
        },
    )

    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]

    assert result["deep_runtime"]["runtime_state"]["current_iteration"] == 1
    assert result["deep_runtime"]["task_queue"]["stats"]["completed"] == 1
    assert result["deep_runtime"]["task_queue"]["stats"]["ready"] == 1
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
                    "status": "needs_user_input",
                    "follow_up_question": "What time range should the research cover?",
                    "blocking_slot": "time_range",
                    "resolved_slots": {
                        "goal": f"Research {topic}",
                        "time_range": "",
                        "source_preferences": [],
                        "constraints": [],
                        "exclusions": [],
                        "deliverable_preferences": [],
                    },
                    "unresolved_slots": ["time_range"],
                    "asked_slots": ["time_range"],
                }
            return {
                "status": "ready_for_scope",
                "follow_up_question": "",
                "blocking_slot": "none",
                "resolved_slots": {
                    "goal": f"Research {topic}",
                    "time_range": clarify_answers[-1],
                    "source_preferences": [],
                    "constraints": [],
                    "exclusions": [],
                    "deliverable_preferences": [],
                },
                "unresolved_slots": [],
                "asked_slots": ["time_range"],
            }

    class _ScopeCapture(_FakeScopeAgent):
        def create_scope(
            self,
            topic,
            clarification_state=None,
            previous_scope=None,
            scope_feedback="",
            clarify_transcript=None,
        ):
            scope_calls.append(list(clarify_transcript or []))
            return super().create_scope(
                topic,
                clarification_state=clarification_state,
                previous_scope=previous_scope,
                scope_feedback=scope_feedback,
                clarify_transcript=clarify_transcript,
            )

    _patch_runtime_deps(
        monkeypatch,
        emitter=emitter,
        clarify=_ClarifyWithFollowUp,
        scope=_ScopeCapture,
        supervisor=_SingleTaskSupervisor,
    )

    config = {
        "configurable": {
            "thread_id": "thread_clarify_scope_context",
            "allow_interrupts": True,
            "deep_research_query_num": 1,
        }
    }
    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        config,
    )
    graph = runtime.build_graph(checkpointer=MemorySaver())

    first = graph.invoke(runtime.build_initial_graph_state(), config)
    assert "__interrupt__" in first
    assert first["__interrupt__"][0].value["checkpoint"] == "deep_research_clarify"

    second = graph.invoke(Command(resume={"clarify_answer": "Only 2024 annual filings"}), config)
    assert "__interrupt__" in second
    assert second["__interrupt__"][0].value["checkpoint"] == "deep_research_scope_review"

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


def test_multi_agent_clarify_forces_scope_after_single_user_answer(monkeypatch):
    emitter = _DummyEmitter()

    class _ClarifyAsksTwice:
        def __init__(self, _llm, _config=None):
            pass

        def assess_intake(self, topic, clarify_answers=None, clarify_history=None):
            answer = str((clarify_answers or [""])[-1] or "").strip()
            return {
                "status": "needs_user_input",
                "follow_up_question": "Which sources should the research prioritize?",
                "blocking_slot": "source_preferences",
                "resolved_slots": {
                    "goal": f"Research {topic}",
                    "time_range": "",
                    "source_preferences": [answer] if answer else [],
                    "constraints": [],
                    "exclusions": [],
                    "deliverable_preferences": [],
                },
                "unresolved_slots": ["source_preferences"],
                "asked_slots": ["source_preferences"],
            }

    _patch_runtime_deps(
        monkeypatch,
        emitter=emitter,
        clarify=_ClarifyAsksTwice,
        supervisor=_SingleTaskSupervisor,
    )

    config = {
        "configurable": {
            "thread_id": "thread_single_clarify_round",
            "allow_interrupts": True,
            "deep_research_query_num": 1,
        }
    }
    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        config,
    )
    graph = runtime.build_graph(checkpointer=MemorySaver())

    first = graph.invoke(runtime.build_initial_graph_state(), config)
    assert "__interrupt__" in first
    assert first["__interrupt__"][0].value["checkpoint"] == "deep_research_clarify"

    second = graph.invoke(Command(resume={"clarify_answer": "Use official filings"}), config)
    assert "__interrupt__" in second
    assert second["__interrupt__"][0].value["checkpoint"] == "deep_research_scope_review"
