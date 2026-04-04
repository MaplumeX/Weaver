from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
import pytest

import agent.runtime.deep.orchestration.graph as multi_agent_graph
import agent.runtime.deep.orchestration.graph as multi_agent_runtime
from agent.core.state import build_deep_runtime_snapshot
from agent.runtime.deep.orchestration import run_multi_agent_deep_research
from agent.runtime.deep.roles.supervisor import SupervisorAction, SupervisorDecision
from agent.runtime.deep.support.tool_agents import (
    DeepResearchToolAgentSession,
    build_deep_research_fabric_tools,
)


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


class _StrictReporter(_FakeReporter):
    def generate_report(self, topic_or_context, findings=None, sources=None):
        topic = topic_or_context.topic if hasattr(topic_or_context, "topic") else topic_or_context
        raise AssertionError(f"reporter fallback should not run for {topic}")

    def generate_executive_summary(self, report, topic):
        raise AssertionError(f"reporter fallback should not run for {topic}")


class _ContextCheckingReporter(_FakeReporter):
    def generate_report(self, topic_or_context, findings=None, sources=None):
        assert hasattr(topic_or_context, "sections")
        assert topic_or_context.sections
        assert topic_or_context.sources
        return super().generate_report(topic_or_context, findings=findings, sources=sources)


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


_BRANCH_ARTIFACT_TYPES = {
    "branch_brief",
    "source_candidate",
    "fetched_document",
    "evidence_passage",
    "evidence_card",
    "branch_synthesis",
    "report_section_draft",
    "coordination_request",
    "research_submission",
    "verification_result",
    "verification_submission",
}

_LOOP_DECISION_TYPES = {
    "research",
    "retry_branch",
    "verification_retry_requested",
    "coverage_gap_detected",
    "verification_passed",
    "outline_gap_detected",
    "outline_ready",
    "synthesize",
    "complete",
    "budget_stop",
}


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


class _IncompleteResearchAgent(_FakeResearchAgent):
    def summarize_findings(self, topic, results, existing_summary=""):
        return f"{topic} -> partial notes only"


class _CompleteCriteriaResearchAgent(_FakeResearchAgent):
    def summarize_findings(self, topic, results, existing_summary=""):
        return f"Explain the current state of {topic} aspect 1"


class _DummyArtifactStore:
    def coordination_requests(self, status=None):
        return []


class _DummyToolSessionRuntime:
    def __init__(self):
        self.searches_used = 0
        self.tokens_used = 0
        self.max_searches = 0
        self.max_tokens = 0
        self.max_seconds = 0.0
        self.start_ts = 0.0
        self.artifact_store = _DummyArtifactStore()


@pytest.fixture(autouse=True)
def _disable_tool_agents_by_default(monkeypatch):
    monkeypatch.setattr(multi_agent_runtime.settings, "deep_research_use_tool_agents", False, raising=False)


def test_run_multi_agent_deep_research_merges_artifacts_and_emits_events(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

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

    queue_stats = result["deep_runtime"]["task_queue"]["stats"]
    artifact_store = result["deep_runtime"]["artifact_store"]
    event_types = [name for name, _ in emitter.emitted]
    agent_roles = {run["role"] for run in result["deep_runtime"]["agent_runs"]}

    assert result["deep_runtime"]["engine"] == "multi_agent"
    assert result["deep_runtime"]["engine"] == "multi_agent"
    assert result["is_complete"] is True
    assert result["deep_runtime"]["task_queue"]["stats"]["completed"] == queue_stats["completed"]
    assert queue_stats["completed"] == 2
    assert len(artifact_store["branch_briefs"]) >= 3
    assert len(artifact_store["source_candidates"]) == 2
    assert len(artifact_store["fetched_documents"]) == 2
    assert len(artifact_store["evidence_passages"]) == 2
    assert len(artifact_store["evidence_cards"]) == 2
    assert len(artifact_store["branch_syntheses"]) == 2
    assert len(artifact_store["answer_units"]) >= 2
    assert len(artifact_store["verification_results"]) == 4
    assert len(artifact_store["branch_validation_summaries"]) == 2
    assert artifact_store["research_brief"]["scope_id"]
    assert len(artifact_store["task_ledger"]["entries"]) == 2
    assert artifact_store["progress_ledger"]["outline_status"] == "ready"
    assert len(artifact_store["coverage_matrix"]["rows"]) >= 1
    assert len(artifact_store["contradiction_registry"]["entries"]) == 0
    assert len(artifact_store["missing_evidence_list"]["items"]) == 0
    assert artifact_store["outline"]["is_ready"] is True
    assert len(artifact_store["submissions"]) >= 4
    assert len(artifact_store["supervisor_decisions"]) >= 2
    assert len(artifact_store["report_section_drafts"]) == 2
    assert result["deep_runtime"]["runtime_state"]["engine"] == "multi_agent"
    assert result["deep_runtime"]["runtime_state"]["last_verification_summary"]["verified_branches"] == 2
    assert len(
        result["deep_runtime"]["runtime_state"]["last_verification_summary"]["branch_validation_summary_ids"]
    ) == 2
    assert result["deep_runtime"]["runtime_state"]["supervisor_phase"] == "loop_decision"
    assert result["deep_runtime"]["runtime_state"]["research_brief_id"]
    assert result["deep_runtime"]["runtime_state"]["outline_status"] == "ready"
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


def test_multi_agent_runtime_exposes_control_plane_handoffs_and_public_artifacts(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_control_plane",
                "deep_research_query_num": 1,
            }
        },
    )

    runtime_state = result["deep_runtime"]["runtime_state"]
    handoff_history = runtime_state["handoff_history"]
    control_plane = result["deep_research_artifacts"]["control_plane"]

    assert runtime_state["active_agent"] == "supervisor"
    assert len(handoff_history) >= 2
    assert any(
        item["from_agent"] == "clarify" and item["to_agent"] == "scope"
        for item in handoff_history
    )
    assert any(
        item["from_agent"] == "scope" and item["to_agent"] == "supervisor"
        for item in handoff_history
    )
    assert control_plane["active_agent"] == "supervisor"
    assert control_plane["latest_handoff"]["to_agent"] == "supervisor"
    assert len(control_plane["handoff_history"]) == len(handoff_history)


def test_build_initial_graph_state_restores_control_plane_owner_from_checkpoint(monkeypatch):
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: _DummyEmitter())

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
            "handoff_envelope": {
                "id": "handoff-1",
                "from_agent": "clarify",
                "to_agent": "scope",
                "reason": "clarify completed",
                "context_refs": [],
                "scope_snapshot": {},
                "review_state": "ready_for_scope",
                "created_at": "2026-04-04T00:00:00",
                "created_by": "clarify",
                "metadata": {},
            },
            "handoff_history": [
                {
                    "id": "handoff-1",
                    "from_agent": "clarify",
                    "to_agent": "scope",
                    "reason": "clarify completed",
                    "context_refs": [],
                    "scope_snapshot": {},
                    "review_state": "ready_for_scope",
                    "created_at": "2026-04-04T00:00:00",
                    "created_by": "clarify",
                    "metadata": {},
                }
            ],
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
    assert initial_state["runtime_state"]["handoff_envelope"]["to_agent"] == "scope"
    assert initial_state["next_step"] == "scope_review"


def test_control_plane_handoff_tools_are_owner_gated():
    session = DeepResearchToolAgentSession(
        runtime=_DummyToolSessionRuntime(),
        role="scope",
        topic="AI chips",
        graph_run_id="graph-1",
        branch_id="branch-1",
        allowed_capabilities={"fabric"},
        active_agent="clarify",
    )
    tools = {tool.name: tool for tool in build_deep_research_fabric_tools(session)}

    assert "fabric_submit_handoff" in tools
    with pytest.raises(RuntimeError):
        tools["fabric_submit_handoff"].invoke({"to_agent": "supervisor", "reason": "scope ready"})

    session.active_agent = "scope"
    handoff = tools["fabric_submit_handoff"].invoke({"to_agent": "supervisor", "reason": "scope ready"})
    assert handoff["from_agent"] == "scope"
    assert handoff["to_agent"] == "supervisor"
    assert session.active_agent == "supervisor"

    researcher_session = DeepResearchToolAgentSession(
        runtime=_DummyToolSessionRuntime(),
        role="researcher",
        topic="AI chips",
        graph_run_id="graph-1",
        branch_id="branch-1",
        allowed_capabilities={"fabric", "search"},
        active_agent="supervisor",
    )
    researcher_tool_names = {
        tool.name
        for tool in build_deep_research_fabric_tools(researcher_session)
    }
    assert "fabric_submit_handoff" not in researcher_tool_names


def test_multi_agent_graph_topology_exposes_role_nodes(monkeypatch):
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: _DummyEmitter())

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


def test_multi_agent_branch_events_include_stable_iteration_metadata(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_iteration_metadata",
                "deep_research_query_num": 1,
            }
        },
    )

    branch_task_updates = [
        data
        for name, data in emitter.emitted
        if name == "research_task_update" and data.get("task_kind") == "branch_research"
    ]
    assert branch_task_updates
    assert all(isinstance(item.get("iteration"), int) and item["iteration"] >= 1 for item in branch_task_updates)

    branch_artifact_updates = [
        data
        for name, data in emitter.emitted
        if (
            name == "research_artifact_update"
            and data.get("artifact_type") in _BRANCH_ARTIFACT_TYPES
            and (data.get("branch_id") or data.get("task_id"))
        )
    ]
    assert branch_artifact_updates
    assert all(
        isinstance(item.get("iteration"), int) and item["iteration"] >= 1
        for item in branch_artifact_updates
    )


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

    resume_config = {
        "configurable": {
            **config["configurable"],
            "resumed_from_checkpoint": True,
        }
    }
    resumed = graph.invoke(Command(resume={"continue": True}), resume_config)
    final_result = resumed["final_result"]

    assert final_result["deep_runtime"]["runtime_state"]["graph_run_id"] == interrupt_payload["graph_run_id"]
    assert final_result["deep_runtime"]["task_queue"]["stats"]["completed"] == 2
    assert final_result["deep_runtime"]["runtime_state"]["last_verification_summary"]["verified_branches"] == 2


def test_multi_agent_completed_snapshot_resumes_via_finalize_without_replanning(monkeypatch):
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
            "thread_id": "thread_resume_completed",
            "deep_research_query_num": 1,
        }
    }
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

        def decide_next_action(self, **kwargs):
            raise AssertionError("completed snapshot should not re-enter supervisor_decide")

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

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _FakeVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

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

    assert research_events
    assert all(event.get("resumed_from_checkpoint") is True for event in research_events)

    resumed_loop_events = [
        data
        for name, data in emitter.emitted
        if (
            name in {"research_agent_start", "research_agent_complete"}
            and data.get("role") in {"researcher", "verifier", "reporter"}
        )
        or (name == "research_task_update" and data.get("task_kind") == "branch_research")
        or (
            name == "research_artifact_update"
            and data.get("artifact_type") in _BRANCH_ARTIFACT_TYPES
            and (data.get("branch_id") or data.get("task_id"))
        )
        or (name == "research_decision" and data.get("decision_type") in _LOOP_DECISION_TYPES)
    ]

    assert resumed_loop_events
    assert all(event.get("graph_run_id") for event in resumed_loop_events)
    assert all(isinstance(event.get("attempt"), int) and event["attempt"] >= 0 for event in resumed_loop_events)
    assert all(isinstance(event.get("iteration"), int) and event["iteration"] >= 1 for event in resumed_loop_events)


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

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_retry",
                                "deep_research_query_num": 1,
                "deep_research_task_retry_limit": 2,
                "deep_research_max_epochs": 3,
            }
        },
    )

    tasks = result["deep_runtime"]["task_queue"]["tasks"]
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
    assert "1. Collect the latest evidence about the current state of AI chips" in first_prompt["content"]
    assert "## Core Questions" not in first_prompt["content"]

    second = graph.invoke(
        Command(resume={"action": "revise_scope", "scope_feedback": "Focus on supply chain resilience"}),
        config,
    )
    assert "__interrupt__" in second
    second_prompt = second["__interrupt__"][0].value
    assert second_prompt["checkpoint"] == "deep_research_scope_review"
    assert second_prompt["scope_version"] == 2
    assert second_prompt["graph_run_id"] == first_prompt["graph_run_id"]
    assert "1. Refocus the research around the revision request: Focus on supply chain resilience" in second_prompt["content"]

    resumed = graph.invoke(Command(resume={"action": "approve_scope"}), config)
    final_result = resumed["final_result"]
    runtime_state = final_result["deep_runtime"]["runtime_state"]

    assert runtime_state["scope_revision_count"] == 1
    assert runtime_state["approved_scope_draft"]["version"] == 2
    assert runtime_state["approved_scope_draft"]["status"] == "approved"
    assert final_result["deep_runtime"]["task_queue"]["stats"]["completed"] == 1

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
            claim_ids = [item.id for item in session.claim_units]
            obligation_ids = [
                str(item.get("id") or "").strip()
                for item in session.related_artifacts.get("coverage_obligations", [])
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            ]
            session.submit_verification_bundle(
                validation_stage=validation_stage,
                outcome="passed",
                summary=f"{validation_stage} passed",
                recommended_action="report",
                claim_ids=claim_ids if validation_stage == "claim_check" else None,
                obligation_ids=obligation_ids if validation_stage == "coverage_check" else None,
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

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_tool_agents",
                                "deep_research_query_num": 1,
                "deep_research_use_tool_agents": True,
            }
        },
    )

    assert result["deep_runtime"]["artifact_store"]["final_report"]["executive_summary"] == "tool-agent summary"
    assert "## 来源" in result["deep_runtime"]["artifact_store"]["final_report"]["report_markdown"]
    assert {role for role, _task_id in bounded_roles} >= {
        "clarify",
        "scope",
        "supervisor",
        "researcher",
        "verifier",
        "reporter",
    }
    assert any(
        item["submission_kind"] == "report_bundle"
        for item in result["deep_runtime"]["artifact_store"]["submissions"]
    )


def test_multi_agent_runtime_allows_advisory_gaps_without_blocking_report(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _CompleteCriteriaResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _GapingVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _ContextCheckingReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

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

    artifact_store = result["deep_runtime"]["artifact_store"]
    runtime_state = result["deep_runtime"]["runtime_state"]

    assert result["is_complete"] is True
    assert artifact_store["outline"]["is_ready"] is True
    assert artifact_store["missing_evidence_list"]["items"] == []
    assert len(artifact_store["knowledge_gaps"]) == 1
    assert artifact_store["knowledge_gaps"][0]["advisory"] is True
    assert runtime_state["last_verification_summary"]["blocking_verification_debt_count"] == 0
    assert runtime_state["last_verification_summary"]["advisory_gap_count"] == 1
    assert "## 来源" in artifact_store["final_report"]["report_markdown"]
    assert "[1]" in artifact_store["final_report"]["report_markdown"]

    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "verification_passed" in decision_types
    assert "report" in decision_types


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

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_budget_stop",
                                "deep_research_query_num": 2,
                "deep_research_max_searches": 1,
            }
        },
    )

    assert result["deep_runtime"]["runtime_state"]["budget_stop_reason"] == "search_budget_exceeded"
    assert result["deep_runtime"]["task_queue"]["stats"]["completed"] == 1
    assert result["deep_runtime"]["task_queue"]["stats"]["ready"] == 1
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

    assert result["deep_runtime"]["runtime_state"]["current_iteration"] == 1
    assert result["deep_runtime"]["task_queue"]["stats"]["completed"] == 1
    assert result["deep_runtime"]["task_queue"]["stats"]["ready"] == 1
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "research" in decision_types
    assert "report" in decision_types


def test_multi_agent_runtime_stops_when_replan_produces_no_new_tasks(monkeypatch):
    emitter = _DummyEmitter()

    class _ReplanWithoutTasksSupervisor(_SingleTaskSupervisor):
        def decide_next_action(self, **kwargs):
            if int(kwargs.get("ready_task_count") or 0) > 0:
                return SupervisorDecision(
                    action=SupervisorAction.DISPATCH,
                    reasoning="dispatch ready branches",
                    request_ids=list(kwargs.get("request_ids") or []),
                )
            return SupervisorDecision(
                action=SupervisorAction.REPLAN,
                reasoning="coverage still incomplete, replan instead",
                request_ids=list(kwargs.get("request_ids") or []),
            )

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _ReplanWithoutTasksSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _IncompleteResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _GapingVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
            {
                "configurable": {
                    "thread_id": "thread_replan_empty",
                    "deep_research_query_num": 1,
                    "deep_research_max_epochs": 3,
                }
            },
        )

    runtime_state = result["deep_runtime"]["runtime_state"]
    assert runtime_state["terminal_status"] == "blocked"
    assert "重规划未生成新的 branch 研究任务" in runtime_state["terminal_reason"]
    assert "Deep Research 未能完成" in result["final_report"]
    assert result["deep_runtime"]["artifact_store"]["final_report"] is None

    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "stop" in decision_types


def test_multi_agent_runtime_allows_advisory_outline_progress_after_report_decision(monkeypatch):
    emitter = _DummyEmitter()

    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _SingleTaskSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _IncompleteResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "KnowledgeGapAnalyzer", _GapingVerifier)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    result = run_multi_agent_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_outline_blocked_report",
                "deep_research_query_num": 1,
                "deep_research_max_epochs": 1,
                "deep_research_parallel_workers": 1,
            }
        },
    )

    runtime_state = result["deep_runtime"]["runtime_state"]
    assert runtime_state["terminal_status"] == ""
    assert result["deep_runtime"]["artifact_store"]["outline"]["is_ready"] is True
    assert result["deep_runtime"]["artifact_store"]["final_report"] is not None

    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "report" in decision_types
    assert "outline_ready" in decision_types


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
    assert first_prompt["checkpoint"] == "deep_research_clarify"

    second = graph.invoke(
        Command(resume={"clarify_answer": "Only 2024 annual filings"}),
        config,
    )
    assert "__interrupt__" in second
    second_prompt = second["__interrupt__"][0].value
    assert second_prompt["checkpoint"] == "deep_research_scope_review"

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
