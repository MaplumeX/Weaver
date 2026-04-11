import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import agent.deep_research.agents.supervisor as supervisor_module
import agent.deep_research.engine.graph as multi_agent_runtime
from agent.deep_research.entrypoints import run_deep_research
from agent.foundation.state import build_deep_runtime_snapshot


class _DummyEmitter:
    def __init__(self):
        self.emitted = []

    def emit_sync(self, event_type, data):
        name = event_type.value if hasattr(event_type, "value") else str(event_type)
        self.emitted.append((name, data))


class _FakeToolCallingAgent:
    def __init__(self, tools, tool_name, tool_payload):
        self.tools = {
            getattr(tool, "name", ""): tool
            for tool in tools
            if getattr(tool, "name", "")
        }
        self.tool_name = tool_name
        self.tool_payload = tool_payload

    def invoke(self, payload, config=None):
        del payload, config
        self.tools[self.tool_name]._run(**self.tool_payload)
        return {"messages": []}


class _FakeSupervisor:
    def __init__(self, _llm, _config=None):
        pass

    def create_outline_plan(self, topic, *, approved_scope=None):
        scope = approved_scope or {}
        questions = list(scope.get("core_questions") or [f"What matters most about {topic}?"])
        sections = []
        mapping = {}
        for index, question in enumerate(questions, 1):
            section_id = f"section_{index}"
            sections.append(
                {
                    "id": section_id,
                    "title": f"问题 {index}: {question}",
                    "objective": question,
                    "core_question": question,
                    "acceptance_checks": [question],
                    "source_requirements": ["至少 1 个可引用来源", "至少 1 段可定位 passage 支撑主结论"],
                    "freshness_policy": "default_advisory",
                    "section_order": index,
                    "status": "planned",
                }
            )
            mapping[question] = section_id
        return {
            "id": "outline_1",
            "topic": topic,
            "outline_version": 1,
            "sections": sections,
            "required_section_ids": [item["id"] for item in sections],
            "question_section_map": mapping,
            "status": "completed",
        }

    def decide_section_action(
        self,
        *,
        outline,
        section_status_map,
        budget_stop_reason="",
        aggregate_summary=None,
        reportable_section_count=0,
        pending_replans=None,
    ):
        aggregate = aggregate_summary or {}
        if budget_stop_reason and not reportable_section_count and not aggregate.get("report_ready"):
            return type("Decision", (), {"action": "stop", "reasoning": budget_stop_reason})()
        pending_replans = [item for item in (pending_replans or []) if isinstance(item, dict)]
        if pending_replans:
            task_specs = []
            for item in pending_replans:
                preferred_action = str(item.get("preferred_action") or "").strip()
                if preferred_action == "revise_section":
                    task_kind = "section_revision"
                    replan_kind = "revision"
                else:
                    task_kind = "section_research"
                    replan_kind = (
                        "counterevidence"
                        if bool(item.get("needs_counterevidence_query"))
                        else "follow_up_research"
                    )
                task_specs.append(
                    {
                        "section_id": str(item.get("section_id") or "").strip(),
                        "section_order": int(item.get("section_order", 0) or 0),
                        "task_kind": task_kind,
                        "replan_kind": replan_kind,
                        "reason": str(item.get("reason") or "").strip(),
                        "issue_ids": list(item.get("issue_ids") or []),
                        "follow_up_queries": list(item.get("follow_up_queries") or []),
                        "objective": str(item.get("objective") or "").strip(),
                        "core_question": str(item.get("core_question") or "").strip(),
                    }
                )
            return type(
                "Decision",
                (),
                {
                    "action": "replan",
                    "reasoning": "需要补充研究计划",
                    "task_specs": task_specs,
                },
            )()
        if reportable_section_count or aggregate.get("report_ready"):
            return type("Decision", (), {"action": "report", "reasoning": "已有可报告章节"})()
        required = list(outline.get("required_section_ids") or [])
        blocked = [section_id for section_id in required if section_status_map.get(section_id) == "blocked"]
        if blocked:
            return type("Decision", (), {"action": "stop", "reasoning": "存在阻塞章节"})()
        pending = [section_id for section_id in required if section_status_map.get(section_id) != "certified"]
        if pending:
            return type("Decision", (), {"action": "dispatch", "reasoning": "仍有未认证章节"})()
        return type("Decision", (), {"action": "report", "reasoning": "所有章节已认证"})()

    def create_plan(self, *args, **kwargs):
        return []

    def refine_plan(self, *args, **kwargs):
        return []


class _SingleTaskSupervisor(_FakeSupervisor):
    def create_outline_plan(self, topic, *, approved_scope=None):
        scope = approved_scope or {}
        questions = list(scope.get("core_questions") or [f"What matters most about {topic}?"])
        first_question = questions[0]
        return {
            "id": "outline_1",
            "topic": topic,
            "outline_version": 1,
            "sections": [
                {
                    "id": "section_1",
                    "title": f"问题 1: {first_question}",
                    "objective": first_question,
                    "core_question": first_question,
                    "acceptance_checks": [first_question],
                    "source_requirements": ["至少 1 个可引用来源", "至少 1 段可定位 passage 支撑主结论"],
                    "freshness_policy": "default_advisory",
                    "section_order": 1,
                    "status": "planned",
                }
            ],
            "required_section_ids": ["section_1"],
            "question_section_map": {first_question: "section_1"},
            "status": "completed",
        }


class _OutlinePlanningFailureSupervisor(_FakeSupervisor):
    def create_outline_plan(self, topic, *, approved_scope=None):
        del topic, approved_scope
        raise RuntimeError("tool-calling outline manager execution failed: planning unavailable")


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

    def research_branch(self, task, *, topic, existing_summary="", max_results_per_query=5):
        query = (list(task.query_hints or []) or [task.query])[0]
        url = f"https://example.com/{query.replace(' ', '-')}"
        return {
            "queries": [query],
            "search_results": [
                {
                    "title": f"{query} result",
                    "url": url,
                    "summary": f"{query} summary",
                    "raw_excerpt": f"{query} raw excerpt",
                    "provider": "fake",
                }
            ],
            "sources": [
                {
                    "title": f"{query} result",
                    "url": url,
                    "provider": "fake",
                    "authoritative": True,
                }
            ],
            "documents": [
                {
                    "id": f"document_{query.replace(' ', '_')}",
                    "url": url,
                    "raw_url": f"{url}?utm=test",
                    "title": f"{query} result",
                    "excerpt": f"{query} authoritative excerpt",
                    "content": f"# Overview\n\n{query} authoritative evidence",
                    "method": "direct_http",
                    "published_date": "2026-04-01",
                    "retrieved_at": "2026-04-04T00:00:00+00:00",
                    "http_status": 200,
                    "attempts": 1,
                    "authoritative": True,
                    "admissible": True,
                }
            ],
            "passages": [
                {
                    "id": f"passage_{query.replace(' ', '_')}",
                    "document_id": f"document_{query.replace(' ', '_')}",
                    "url": url,
                    "text": f"{query} authoritative evidence",
                    "quote": f"{query} authoritative evidence",
                    "source_title": f"{query} result",
                    "snippet_hash": f"hash_{query.replace(' ', '_')}",
                    "heading_path": ["Overview"],
                    "page_title": f"{query} result",
                    "retrieved_at": "2026-04-04T00:00:00+00:00",
                    "method": "direct_http",
                    "authoritative": True,
                    "admissible": True,
                }
            ],
            "summary": f"{topic} -> {query} result",
            "key_findings": [f"{query} authoritative evidence"],
            "open_questions": [],
            "confidence_note": "",
        }


class _FlakyResearchAgent(_FakeResearchAgent):
    def __init__(self, _llm, search_func, config=None):
        super().__init__(_llm, search_func, config=config)
        self.calls = {}

    def research_branch(self, task, *, topic, existing_summary="", max_results_per_query=5):
        query = (list(task.query_hints or []) or [task.query])[0]
        self.calls[query] = self.calls.get(query, 0) + 1
        if self.calls[query] == 1:
            return {
                "queries": [query],
                "search_results": [],
                "sources": [],
                "documents": [],
                "passages": [],
                "summary": "",
                "key_findings": [],
                "open_questions": [],
                "confidence_note": "",
            }
        return super().research_branch(
            task,
            topic=topic,
            existing_summary=existing_summary,
            max_results_per_query=max_results_per_query,
        )


class _WeakEvidenceResearchAgent(_FakeResearchAgent):
    def research_branch(self, task, *, topic, existing_summary="", max_results_per_query=5):
        result = super().research_branch(
            task,
            topic=topic,
            existing_summary=existing_summary,
            max_results_per_query=max_results_per_query,
        )
        result["passages"] = []
        return result


class _FakeReporter:
    def __init__(self, _llm, _config=None):
        pass

    def generate_report(self, topic_or_context, findings=None, sources=None):
        if hasattr(topic_or_context, "topic"):
            topic = topic_or_context.topic
            sections = []
            for section in topic_or_context.sections:
                lines = [section.summary]
                if section.findings:
                    lines.append("\n- " + "\n- ".join(section.findings))
                if section.branch_summaries:
                    lines.append("\n".join(section.branch_summaries))
                sections.append(f"## {section.title}\n\n" + "\n".join(item for item in lines if item))
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

    def generate_executive_summary(self, report, topic, *, report_context=None):
        return f"{topic} executive summary"


class _ContextCheckingReporter(_FakeReporter):
    def generate_report(self, topic_or_context, findings=None, sources=None):
        assert hasattr(topic_or_context, "sections")
        assert topic_or_context.sections
        assert topic_or_context.sources
        return super().generate_report(topic_or_context, findings=findings, sources=sources)


class _QualityCheckingReporter(_FakeReporter):
    def generate_report(self, topic_or_context, findings=None, sources=None):
        assert hasattr(topic_or_context, "sections")
        assert topic_or_context.sections
        first = topic_or_context.sections[0]
        assert getattr(first, "confidence_level", "")
        assert hasattr(first, "risk_highlights")
        assert hasattr(first, "manual_review_items")
        return super().generate_report(topic_or_context, findings=findings, sources=sources)


_LIGHTWEIGHT_ARTIFACT_TYPES = {
    "scope",
    "outline",
    "plan",
    "evidence_bundle",
    "section_draft",
    "section_review",
    "section_certification",
    "final_report",
}

_SECTION_ARTIFACT_TYPES = {"evidence_bundle", "section_draft", "section_review", "section_certification"}


def _patch_runtime_deps(
    monkeypatch,
    *,
    emitter,
    clarify=_FakeClarifyAgent,
    scope=_FakeScopeAgent,
    supervisor=_FakeSupervisor,
    researcher=_FakeResearchAgent,
    reporter=_FakeReporter,
):
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", clarify)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", scope)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", supervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", researcher)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", reporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)


@pytest.fixture(autouse=True)
def _disable_tool_agents_by_default(monkeypatch):
    monkeypatch.setattr(multi_agent_runtime.settings, "deep_research_use_tool_agents", False, raising=False)


def test_multi_agent_runtime_uses_default_max_epochs(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_default_max_epochs"}},
    )

    assert runtime.max_epochs == multi_agent_runtime.settings.deep_research_max_epochs


def test_run_deep_research_emits_section_artifacts_and_events(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, reporter=_ContextCheckingReporter)

    result = run_deep_research(
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
    assert runtime["runtime_state"]["tool_runtime_context"]["thread_id"] == "thread_test"
    assert runtime["runtime_state"]["tool_runtime_context"]["session_id"] == "thread_test"
    assert runtime["runtime_state"]["role_tool_policies"]["researcher"]["requested_tools"] == [
        "search",
        "read",
        "extract",
        "synthesize",
    ]
    assert result["is_complete"] is True
    assert queue_stats["completed"] == 2
    assert set(artifact_store) == {
        "branch_contradictions",
        "branch_coverages",
        "branch_decisions",
        "branch_groundings",
        "branch_qualities",
        "branch_query_rounds",
        "evidence_bundles",
        "scope",
        "outline",
        "plan",
        "section_drafts",
        "section_reviews",
        "section_certifications",
        "final_report",
    }
    assert len(artifact_store["section_drafts"]) == 2
    assert len(artifact_store["section_reviews"]) == 2
    assert len(artifact_store["section_certifications"]) == 2
    assert public_artifacts["outline"]["required_section_ids"] == ["section_1", "section_2"]
    assert len(public_artifacts["section_drafts"]) == 2
    assert len(public_artifacts["section_reviews"]) == 2
    assert len(public_artifacts["section_certifications"]) == 2
    assert "branch_query_rounds" in public_artifacts
    assert "branch_coverages" in public_artifacts
    assert "branch_qualities" in public_artifacts
    assert "branch_contradictions" in public_artifacts
    assert "branch_groundings" in public_artifacts
    assert "branch_decisions" in public_artifacts
    assert public_artifacts["outline_gate_summary"]["outline_ready"] is True
    assert public_artifacts["coverage_summary"]["ready"] is True
    researcher_runs = [run for run in runtime["agent_runs"] if run["role"] == "researcher"]
    assert researcher_runs
    assert researcher_runs[0]["requested_tools"] == ["search", "read", "extract", "synthesize"]
    assert "browser_search" in researcher_runs[0]["resolved_tools"]
    assert len(public_artifacts["branch_results"]) == 2
    assert public_artifacts["validation_summary"]["coverage_ready"] is True
    assert public_artifacts["final_report"] == result["final_report"]
    assert {"clarify", "scope", "supervisor", "researcher", "reviewer", "reporter"} <= agent_roles
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


def test_lightweight_artifact_store_does_not_restore_legacy_snapshot_keys():
    store = multi_agent_runtime.LightweightArtifactStore(
        {
            "branch_results": [
                {"id": "legacy-branch", "section_id": "section_1", "summary": "legacy"},
            ],
            "validation_summaries": [
                {"id": "legacy-review", "section_id": "section_1", "verdict": "passed"},
            ],
        }
    )

    assert store.section_drafts() == []
    assert store.section_reviews() == []


def test_multi_agent_graph_topology_exposes_section_role_nodes(monkeypatch):
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
    assert "outline_plan" in mermaid
    assert "dispatch" in mermaid
    assert "researcher" in mermaid
    assert "revisor" in mermaid
    assert "merge" in mermaid
    assert "reviewer" in mermaid
    assert "supervisor_decide" in mermaid
    assert "outline_gate" in mermaid
    assert "report" in mermaid
    assert "finalize" in mermaid


def test_multi_agent_section_events_include_iteration_metadata(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_SingleTaskSupervisor)

    run_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_iteration_metadata", "deep_research_query_num": 1}},
    )

    section_task_updates = [
        data
        for name, data in emitter.emitted
        if name == "research_task_update" and data.get("task_kind") in {"section_research", "section_revision"}
    ]
    section_artifact_updates = [
        data
        for name, data in emitter.emitted
        if (
            name == "research_artifact_update"
            and data.get("artifact_type") in _SECTION_ARTIFACT_TYPES
            and (data.get("section_id") or data.get("task_id"))
        )
    ]

    assert section_task_updates
    assert section_artifact_updates
    assert all(isinstance(item.get("iteration"), int) and item["iteration"] >= 1 for item in section_task_updates)
    assert all(isinstance(item.get("iteration"), int) and item["iteration"] >= 1 for item in section_artifact_updates)


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
    assert final_result["deep_runtime"]["runtime_state"]["outline_gate_summary"]["outline_ready"] is True
    assert final_result["final_report"].startswith("# AI chips")


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


def test_outline_plan_waits_for_scope_approval_before_dispatch(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_SingleTaskSupervisor)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_plan_gate"}},
    )

    blocked = runtime._outline_plan_node(runtime.build_initial_graph_state())
    assert blocked["next_step"] == "scope_review"

    approved_state = runtime.build_initial_graph_state()
    approved_state["runtime_state"]["approved_scope_draft"] = {
        "id": "scope-1",
        "version": 1,
        "status": "approved",
        "research_goal": "Research AI chips",
        "core_questions": ["What matters most about AI chips?"],
    }
    gated = runtime._outline_plan_node(approved_state)
    assert gated["next_step"] == "research_brief"

    brief_state = runtime._research_brief_node(approved_state)
    dispatched = runtime._outline_plan_node(brief_state)

    assert dispatched["next_step"] == "dispatch"
    assert dispatched["task_queue"]["stats"]["ready"] == 1
    assert dispatched["runtime_state"]["supervisor_phase"] == "outline_plan"


def test_outline_plan_finalizes_when_manager_fails(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, supervisor=_OutlinePlanningFailureSupervisor)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_plan_failure"}},
    )

    approved_state = runtime.build_initial_graph_state()
    approved_state["runtime_state"]["approved_scope_draft"] = {
        "id": "scope-1",
        "version": 1,
        "status": "approved",
        "research_goal": "Research AI chips",
        "core_questions": ["What matters most about AI chips?"],
    }
    brief_state = runtime._research_brief_node(approved_state)

    failed = runtime._outline_plan_node(brief_state)

    assert failed["next_step"] == "finalize"
    assert failed["runtime_state"]["terminal_status"] == "blocked"
    assert "tool-calling outline manager execution failed" in failed["runtime_state"]["terminal_reason"]


def test_multi_agent_runtime_retries_failed_task_without_new_task_id(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(
        monkeypatch,
        emitter=emitter,
        supervisor=_SingleTaskSupervisor,
        researcher=_FlakyResearchAgent,
    )

    result = run_deep_research(
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
    assert "failed" in statuses
    assert statuses.count("ready") >= 2
    assert {item["attempt"] for item in dispatch_updates} == {1, 2}


def test_multi_agent_dispatch_records_budget_stop_reason_when_search_budget_exhausted(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter)

    result = run_deep_research(
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
    assert result["deep_research_artifacts"]["quality_summary"]["budget_stop_reason"] == "search_budget_exceeded"
    assert result["deep_research_artifacts"]["quality_summary"]["coverage_ready"] is False
    assert result["terminal_status"] == ""
    assert result["final_report"]
    assert "budget_stop" in decision_types
    assert "report_partial" in decision_types
    assert "outline_partial" in decision_types
    assert "stop" not in decision_types


def test_low_confidence_sections_do_not_generate_report(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(
        monkeypatch,
        emitter=emitter,
        supervisor=_SingleTaskSupervisor,
        researcher=_WeakEvidenceResearchAgent,
        reporter=_QualityCheckingReporter,
    )

    result = run_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_low_confidence_report",
                "deep_research_query_num": 1,
                "deep_research_task_retry_limit": 0,
            }
        },
    )

    public_artifacts = result["deep_research_artifacts"]
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    review = public_artifacts["section_reviews"][0]

    assert result["is_complete"] is True
    assert result["final_report"] == "Deep Research 未能完成：required sections remain blocked"
    assert result["terminal_status"] == "blocked"
    assert review["reportability"] == "low"
    assert review["needs_manual_review"] is True
    assert public_artifacts["validation_summary"]["report_ready"] is False
    assert public_artifacts["quality_summary"]["report_ready"] is False
    assert "report_partial" not in decision_types
    assert "outline_partial" not in decision_types


def test_build_report_sections_skips_non_admitted_sections_and_truncates_medium_findings(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_report_section_filter"}},
    )
    store = multi_agent_runtime.LightweightArtifactStore()

    store.set_section_draft(
        {
            "id": "draft-1",
            "task_id": "task-1",
            "section_id": "section_1",
            "title": "Admitted section",
            "summary": "stable summary",
            "key_findings": ["f1", "f2", "f3"],
            "source_urls": ["https://example.com/a"],
            "contradiction_summary": {},
            "section_order": 1,
        }
    )
    store.set_section_review(
        {
            "id": "review-1",
            "task_id": "task-1",
            "section_id": "section_1",
            "reportability": "medium",
            "needs_manual_review": False,
            "advisory_issues": [],
            "blocking_issues": [],
        }
    )
    store.set_section_certification(
        {
            "id": "cert-1",
            "section_id": "section_1",
            "certified": True,
            "reportability": "medium",
        }
    )

    store.set_section_draft(
        {
            "id": "draft-2",
            "task_id": "task-2",
            "section_id": "section_2",
            "title": "Conflicting section",
            "summary": "should be omitted",
            "key_findings": ["g1", "g2"],
            "source_urls": ["https://example.com/b"],
            "contradiction_summary": {"has_material_conflict": True},
            "section_order": 2,
        }
    )
    store.set_section_review(
        {
            "id": "review-2",
            "task_id": "task-2",
            "section_id": "section_2",
            "reportability": "medium",
            "needs_manual_review": False,
            "advisory_issues": [],
            "blocking_issues": [],
        }
    )
    store.set_section_certification(
        {
            "id": "cert-2",
            "section_id": "section_2",
            "certified": True,
            "reportability": "medium",
        }
    )

    sections = runtime._build_report_sections(store)

    assert [section.title for section in sections] == ["Admitted section"]
    assert sections[0].findings == ["f1", "f2"]
    assert sections[0].citation_urls == ["https://example.com/a"]


def test_medium_section_report_uses_admitted_content_only(monkeypatch):
    emitter = _DummyEmitter()
    _patch_runtime_deps(monkeypatch, emitter=emitter, reporter=_ContextCheckingReporter)

    result = run_deep_research(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {
            "configurable": {
                "thread_id": "thread_admitted_report",
                "deep_research_query_num": 1,
            }
        },
    )

    assert result["final_report"]
    assert result["terminal_status"] == ""
    assert result["deep_research_artifacts"]["quality_summary"]["report_ready"] is True

def test_supervisor_decide_accepts_enum_report_action(monkeypatch):
    emitter = _DummyEmitter()
    monkeypatch.setattr(
        supervisor_module,
        "create_agent",
        lambda _llm, tools: _FakeToolCallingAgent(
            tools,
            "complete_report",
            {"reason": "所有章节已认证，可以进入最终报告生成"},
        ),
    )
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_enum_report"}},
    )
    state = runtime.build_initial_graph_state()
    state["artifact_store"] = {
        "scope": {"id": "scope-1"},
        "outline": {
            "id": "outline-1",
            "required_section_ids": ["section_1"],
            "sections": [
                {
                    "id": "section_1",
                    "title": "问题 1",
                    "objective": "What matters most about AI chips?",
                    "core_question": "What matters most about AI chips?",
                    "section_order": 1,
                }
            ],
        },
        "plan": {},
        "evidence_bundles": [],
        "section_drafts": [],
        "section_reviews": [],
        "section_certifications": [{"id": "cert-1", "section_id": "section_1", "certified": True}],
        "final_report": {},
    }
    state["task_queue"] = {
        "tasks": [],
        "stats": {"total": 0, "ready": 0, "in_progress": 0, "completed": 0, "failed": 0, "blocked": 0},
    }
    state["runtime_state"]["section_status_map"] = {"section_1": "certified"}

    result = runtime._supervisor_decide_node(state)

    assert result["next_step"] == "outline_gate"


def test_reviewer_hands_replans_to_supervisor_before_enqueue(monkeypatch):
    emitter = _DummyEmitter()
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_supervisor_replan"}},
    )
    state = runtime.build_initial_graph_state()
    state["artifact_store"] = {
        "scope": {"id": "scope-1"},
        "outline": {
            "id": "outline-1",
            "required_section_ids": ["section_1"],
            "sections": [
                {
                    "id": "section_1",
                    "title": "问题 1",
                    "objective": "What matters most about AI chips?",
                    "core_question": "What matters most about AI chips?",
                    "section_order": 1,
                }
            ],
        },
        "plan": {},
        "evidence_bundles": [
            {
                "id": "bundle-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "sources": [],
                "documents": [],
                "passages": [],
            }
        ],
        "section_drafts": [
            {
                "id": "draft-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "branch_id": "root",
                "title": "问题 1",
                "objective": "What matters most about AI chips?",
                "core_question": "What matters most about AI chips?",
                "summary": "AI chips matter.",
                "key_findings": ["AI chips matter."],
                "open_questions": ["Which sources disagree?"],
                "source_urls": [],
                "claim_units": [
                    {
                        "id": "claim-1",
                        "text": "AI chips matter.",
                        "importance": "primary",
                        "grounded": False,
                    }
                ],
                "coverage_summary": {"missing_topics": ["market share by vendor"]},
                "quality_summary": {},
                "contradiction_summary": {"needs_counterevidence_query": True},
                "grounding_summary": {"primary_grounding_ratio": 0.0},
                "section_order": 1,
            }
        ],
        "section_reviews": [],
        "section_certifications": [],
        "final_report": {},
    }
    state["task_queue"] = {
        "tasks": [],
        "stats": {"total": 0, "ready": 0, "in_progress": 0, "completed": 0, "failed": 0, "blocked": 0},
    }
    state["runtime_state"]["section_status_map"] = {"section_1": "drafted"}

    reviewed = runtime._reviewer_node(state)

    assert reviewed["task_queue"]["stats"]["ready"] == 0
    assert reviewed["runtime_state"]["pending_replans"]

    supervised = runtime._supervisor_decide_node(reviewed)

    assert supervised["next_step"] == "dispatch"
    assert supervised["task_queue"]["stats"]["ready"] == 1
    queued_task = supervised["task_queue"]["tasks"][0]
    assert queued_task["task_kind"] == "section_research"
    assert queued_task["query"] == "market share by vendor"
    assert queued_task["query_hints"][0] == "market share by vendor"
    assert queued_task["aspect"] == "counterevidence"
    assert supervised["runtime_state"]["pending_replans"] == []
    assert supervised["runtime_state"]["section_research_retry_counts"]["section_1"] == 1
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "coverage_gap_detected" in decision_types
    assert "supervisor_replan" in decision_types


def test_tool_calling_supervisor_replan_creates_counterevidence_task(monkeypatch):
    emitter = _DummyEmitter()
    monkeypatch.setattr(
        supervisor_module,
        "create_agent",
        lambda _llm, tools: _FakeToolCallingAgent(
            tools,
            "conduct_research",
            {
                "section_id": "section_1",
                "reason": "需要补充对比来源",
                "queries": ["market share by vendor"],
                "replan_kind": "counterevidence",
                "issue_ids": ["issue-1"],
            },
        ),
    )
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", supervisor_module.ResearchSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_tool_calling_replan"}},
    )
    state = runtime.build_initial_graph_state()
    state["artifact_store"] = {
        "scope": {"id": "scope-1"},
        "outline": {
            "id": "outline-1",
            "required_section_ids": ["section_1"],
            "sections": [
                {
                    "id": "section_1",
                    "title": "问题 1",
                    "objective": "What matters most about AI chips?",
                    "core_question": "What matters most about AI chips?",
                    "section_order": 1,
                }
            ],
        },
        "plan": {},
        "evidence_bundles": [
            {
                "id": "bundle-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "sources": [],
                "documents": [],
                "passages": [],
            }
        ],
        "section_drafts": [
            {
                "id": "draft-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "branch_id": "root",
                "title": "问题 1",
                "objective": "What matters most about AI chips?",
                "core_question": "What matters most about AI chips?",
                "summary": "AI chips matter.",
                "key_findings": ["AI chips matter."],
                "open_questions": ["Which sources disagree?"],
                "source_urls": [],
                "claim_units": [
                    {
                        "id": "claim-1",
                        "text": "AI chips matter.",
                        "importance": "primary",
                        "grounded": False,
                    }
                ],
                "coverage_summary": {"missing_topics": ["market share by vendor"]},
                "quality_summary": {},
                "contradiction_summary": {"needs_counterevidence_query": True},
                "grounding_summary": {"primary_grounding_ratio": 0.0},
                "section_order": 1,
            }
        ],
        "section_reviews": [],
        "section_certifications": [],
        "final_report": {},
    }
    state["task_queue"] = {
        "tasks": [],
        "stats": {"total": 0, "ready": 0, "in_progress": 0, "completed": 0, "failed": 0, "blocked": 0},
    }
    state["runtime_state"]["section_status_map"] = {"section_1": "drafted"}

    reviewed = runtime._reviewer_node(state)
    supervised = runtime._supervisor_decide_node(reviewed)

    assert supervised["next_step"] == "dispatch"
    assert supervised["task_queue"]["stats"]["ready"] == 1
    queued_task = supervised["task_queue"]["tasks"][0]
    assert queued_task["task_kind"] == "section_research"
    assert queued_task["query"] == "market share by vendor"
    assert queued_task["aspect"] == "counterevidence"
    assert queued_task["title"].startswith("补充对比研究:")


def test_tool_calling_supervisor_failure_stops_without_fallback_dispatch(monkeypatch):
    emitter = _DummyEmitter()
    monkeypatch.setattr(
        supervisor_module,
        "create_agent",
        lambda _llm, _tools: (_ for _ in ()).throw(RuntimeError("manager unavailable")),
    )
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", supervisor_module.ResearchSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_tool_calling_stop"}},
    )
    state = runtime.build_initial_graph_state()
    state["artifact_store"] = {
        "scope": {"id": "scope-1"},
        "outline": {
            "id": "outline-1",
            "required_section_ids": ["section_1"],
            "sections": [
                {
                    "id": "section_1",
                    "title": "问题 1",
                    "objective": "What matters most about AI chips?",
                    "core_question": "What matters most about AI chips?",
                    "section_order": 1,
                }
            ],
        },
        "plan": {},
        "evidence_bundles": [
            {
                "id": "bundle-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "sources": [],
                "documents": [],
                "passages": [],
            }
        ],
        "section_drafts": [
            {
                "id": "draft-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "branch_id": "root",
                "title": "问题 1",
                "objective": "What matters most about AI chips?",
                "core_question": "What matters most about AI chips?",
                "summary": "AI chips matter.",
                "key_findings": ["AI chips matter."],
                "open_questions": [],
                "source_urls": [],
                "claim_units": [
                    {
                        "id": "claim-1",
                        "text": "AI chips matter.",
                        "importance": "primary",
                        "grounded": False,
                    }
                ],
                "coverage_summary": {"missing_topics": ["market share by vendor"]},
                "quality_summary": {},
                "contradiction_summary": {"needs_counterevidence_query": True},
                "grounding_summary": {"primary_grounding_ratio": 0.0},
                "section_order": 1,
            }
        ],
        "section_reviews": [],
        "section_certifications": [],
        "final_report": {},
    }
    state["task_queue"] = {
        "tasks": [],
        "stats": {"total": 0, "ready": 0, "in_progress": 0, "completed": 0, "failed": 0, "blocked": 0},
    }
    state["runtime_state"]["section_status_map"] = {"section_1": "drafted"}

    reviewed = runtime._reviewer_node(state)
    supervised = runtime._supervisor_decide_node(reviewed)

    assert supervised["next_step"] == "finalize"
    assert supervised["task_queue"]["stats"]["ready"] == 0
    assert supervised["runtime_state"]["terminal_status"] == "blocked"
    assert "tool-calling manager execution failed" in supervised["runtime_state"]["terminal_reason"]


def test_supervisor_replan_creates_revision_task(monkeypatch):
    emitter = _DummyEmitter()
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_revision_replan"}},
    )
    state = runtime.build_initial_graph_state()
    state["artifact_store"] = {
        "scope": {"id": "scope-1"},
        "outline": {
            "id": "outline-1",
            "required_section_ids": ["section_1"],
            "sections": [
                {
                    "id": "section_1",
                    "title": "问题 1",
                    "objective": "What matters most about AI chips?",
                    "core_question": "What matters most about AI chips?",
                    "section_order": 1,
                }
            ],
        },
        "plan": {},
        "evidence_bundles": [
            {
                "id": "bundle-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "sources": [{"url": "https://example.com/a"}],
                "documents": [{"id": "doc-1"}],
                "passages": [{"id": "passage-1"}],
            }
        ],
        "section_drafts": [
            {
                "id": "draft-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "branch_id": "root",
                "title": "问题 1",
                "objective": "What matters most about AI chips?",
                "core_question": "What matters most about AI chips?",
                "summary": "AI chips matter.",
                "key_findings": ["AI chips matter."],
                "open_questions": [],
                "source_urls": ["https://example.com/a"],
                "claim_units": [
                    {
                        "id": "claim-1",
                        "text": "AI chips matter.",
                        "importance": "primary",
                        "grounded": True,
                    }
                ],
                "coverage_summary": {"coverage_ready": True},
                "quality_summary": {"quality_ready": True},
                "contradiction_summary": {"needs_counterevidence_query": False},
                "grounding_summary": {"primary_grounding_ratio": 0.8},
                "section_order": 1,
            }
        ],
        "section_reviews": [
            {
                "id": "review-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "verdict": "revise_section",
                "reportability": "medium",
                "quality_band": "usable_with_limitations",
                "blocking_issues": [],
                "advisory_issues": [
                    {"id": "issue-1", "issue_type": "secondary_claim_ungrounded", "message": "tighten wording"}
                ],
                "follow_up_queries": [],
                "notes": "tighten wording",
            }
        ],
        "section_certifications": [],
        "final_report": {},
    }
    state["task_queue"] = {
        "tasks": [],
        "stats": {"total": 0, "ready": 0, "in_progress": 0, "completed": 0, "failed": 0, "blocked": 0},
    }
    state["runtime_state"]["pending_replans"] = [
        {
            "section_id": "section_1",
            "section_order": 1,
            "preferred_action": "revise_section",
            "reason": "tighten wording",
            "issue_ids": ["issue-1"],
            "issue_types": ["secondary_claim_ungrounded"],
            "follow_up_queries": [],
            "objective": "What matters most about AI chips?",
            "core_question": "What matters most about AI chips?",
            "reportability": "medium",
            "quality_band": "usable_with_limitations",
        }
    ]
    state["runtime_state"]["section_status_map"] = {"section_1": "revising"}

    supervised = runtime._supervisor_decide_node(state)

    queued_task = supervised["task_queue"]["tasks"][0]
    assert supervised["next_step"] == "dispatch"
    assert queued_task["task_kind"] == "section_revision"
    assert queued_task["revision_kind"] == "revision"
    assert queued_task["target_issue_ids"] == ["issue-1"]
    assert supervised["runtime_state"]["section_revision_counts"]["section_1"] == 1


def test_budget_stop_prevents_supervisor_replan_and_reports_partial(monkeypatch):
    emitter = _DummyEmitter()
    monkeypatch.setattr(multi_agent_runtime, "create_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchClarifyAgent", _FakeClarifyAgent)
    monkeypatch.setattr(multi_agent_runtime, "DeepResearchScopeAgent", _FakeScopeAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchSupervisor", _FakeSupervisor)
    monkeypatch.setattr(multi_agent_runtime, "ResearchAgent", _FakeResearchAgent)
    monkeypatch.setattr(multi_agent_runtime, "ResearchReporter", _FakeReporter)
    monkeypatch.setattr(multi_agent_runtime, "get_emitter_sync", lambda _thread_id: emitter)

    runtime = multi_agent_runtime.MultiAgentDeepResearchRuntime(
        {"input": "AI chips", "sub_agent_contexts": {}},
        {"configurable": {"thread_id": "thread_budget_report_partial", "deep_research_max_epochs": 1}},
    )
    state = runtime.build_initial_graph_state()
    state["current_iteration"] = 1
    state["artifact_store"] = {
        "scope": {"id": "scope-1"},
        "outline": {
            "id": "outline-1",
            "required_section_ids": ["section_1", "section_2"],
            "sections": [
                {
                    "id": "section_1",
                    "title": "问题 1",
                    "objective": "Question one",
                    "core_question": "Question one",
                    "section_order": 1,
                },
                {
                    "id": "section_2",
                    "title": "问题 2",
                    "objective": "Question two",
                    "core_question": "Question two",
                    "section_order": 2,
                },
            ],
        },
        "plan": {},
        "evidence_bundles": [],
        "section_drafts": [
            {
                "id": "draft-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "title": "问题 1",
                "summary": "Supported section",
                "key_findings": ["Supported finding"],
                "source_urls": ["https://example.com/a"],
                "certified": True,
                "section_order": 1,
            }
        ],
        "section_reviews": [
            {
                "id": "review-1",
                "task_id": "task_1",
                "section_id": "section_1",
                "verdict": "accept_section",
                "reportability": "high",
                "quality_band": "strong",
                "blocking_issues": [],
                "advisory_issues": [],
                "follow_up_queries": [],
                "notes": "",
            }
        ],
        "section_certifications": [
            {
                "id": "cert-1",
                "section_id": "section_1",
                "certified": True,
                "reportability": "high",
                "quality_band": "strong",
            }
        ],
        "final_report": {},
    }
    state["task_queue"] = {
        "tasks": [],
        "stats": {"total": 0, "ready": 0, "in_progress": 0, "completed": 0, "failed": 0, "blocked": 0},
    }
    state["runtime_state"]["current_iteration"] = 1
    state["runtime_state"]["section_status_map"] = {"section_1": "certified", "section_2": "research_retry"}
    state["runtime_state"]["pending_replans"] = [
        {
            "section_id": "section_2",
            "section_order": 2,
            "preferred_action": "request_research",
            "reason": "need more evidence",
            "issue_ids": ["issue-2"],
            "issue_types": ["insufficient_sources"],
            "follow_up_queries": ["Question two official data"],
            "objective": "Question two",
            "core_question": "Question two",
            "reportability": "low",
            "quality_band": "needs_follow_up",
        }
    ]

    supervised = runtime._supervisor_decide_node(state)

    assert supervised["next_step"] == "outline_gate"
    assert supervised["task_queue"]["stats"]["ready"] == 0
    decision_types = [data["decision_type"] for name, data in emitter.emitted if name == "research_decision"]
    assert "supervisor_replan" not in decision_types
    assert "report_partial" in decision_types


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
            "thread_id": "thread_resume_clarify_scope",
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

    second = graph.invoke(
        Command(resume={"clarify_answer": "Focus on 2024 through 2026"}),
        config,
    )
    assert "__interrupt__" in second
    assert second["__interrupt__"][0].value["checkpoint"] == "deep_research_scope_review"

    graph.invoke(Command(resume={"action": "approve_scope"}), config)

    assert len(clarify_calls) >= 2
    assert scope_calls
    joined_scope_transcript = "\n".join(str(item) for item in scope_calls[-1])
    assert "time range" in joined_scope_transcript.lower()
    assert "Focus on 2024 through 2026" in joined_scope_transcript


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
            "thread_id": "thread_clarify_single_answer",
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

    second = graph.invoke(
        Command(resume={"clarify_answer": "Prioritize company filings and earnings calls"}),
        config,
    )
    assert "__interrupt__" in second
    assert second["__interrupt__"][0].value["checkpoint"] == "deep_research_scope_review"
