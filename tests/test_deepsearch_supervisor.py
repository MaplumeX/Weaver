import pytest

import agent.deep_research.agents.supervisor as supervisor_module
from agent.deep_research.agents.supervisor import ResearchSupervisor, SupervisorAction


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
        tool = self.tools[self.tool_name]
        tool._run(**self.tool_payload)
        return {"messages": []}


def test_supervisor_outline_plan_propagates_branch_constraints(monkeypatch):
    monkeypatch.setattr(
        supervisor_module,
        "create_agent",
        lambda _llm, tools: _FakeToolCallingAgent(
            tools,
            "submit_outline_plan",
            {
                "reason": "按已批准问题拆成最小章节集",
                "sections": [
                    {
                        "title": "问题 1: 市场格局",
                        "objective": "What is the current AI chips market share landscape?",
                        "core_question": "What is the current AI chips market share landscape?",
                        "acceptance_checks": ["What is the current AI chips market share landscape?"],
                        "coverage_targets": ["What is the current AI chips market share landscape?"],
                    }
                ],
            },
        ),
    )
    supervisor = ResearchSupervisor(object(), {})

    outline = supervisor.create_outline_plan(
        "AI chips",
        approved_scope={
            "research_goal": "Research AI chips market share",
            "core_questions": ["What is the current AI chips market share landscape?"],
            "source_preferences": ["official filings", "company blogs"],
            "deliverable_preferences": ["comparative report"],
            "constraints": ["time range: 2025-2026", "prioritize primary sources"],
        },
    )

    assert outline["required_section_ids"]
    section = outline["sections"][0]

    assert section["coverage_targets"] == ["What is the current AI chips market share landscape?"]
    assert section["source_preferences"] == ["official filings", "company blogs"]
    assert section["authority_preferences"] == ["official filings", "company blogs"]
    assert section["follow_up_policy"] == "bounded"
    assert section["branch_stop_policy"] == "coverage_or_budget"
    assert section["time_boundary"] == "2025-2026"
    assert section["deliverable_constraints"] == ["comparative report"]


def test_supervisor_outline_plan_raises_when_manager_stops(monkeypatch):
    monkeypatch.setattr(
        supervisor_module,
        "create_agent",
        lambda _llm, tools: _FakeToolCallingAgent(
            tools,
            "stop_planning",
            {
                "reason": "approved scope is too incomplete to plan safely",
            },
        ),
    )
    supervisor = ResearchSupervisor(object(), {})

    with pytest.raises(RuntimeError, match="approved scope is too incomplete to plan safely"):
        supervisor.create_outline_plan(
            "AI chips",
            approved_scope={
                "research_goal": "Research AI chips market share",
            },
        )


def test_supervisor_tool_calling_manager_can_delegate_counterevidence(monkeypatch):
    monkeypatch.setattr(
        supervisor_module,
        "create_agent",
        lambda _llm, tools: _FakeToolCallingAgent(
            tools,
            "conduct_research",
            {
                "section_id": "section_1",
                "reason": "需要补充对比来源",
                "queries": ["AI chips opposing view official source"],
                "replan_kind": "counterevidence",
                "issue_ids": ["issue_1"],
            },
        ),
    )
    supervisor = ResearchSupervisor(object(), {})

    decision = supervisor.decide_section_action(
        outline={
            "required_section_ids": ["section_1"],
            "sections": [
                {
                    "id": "section_1",
                    "section_order": 1,
                    "objective": "Assess AI chips market share",
                    "core_question": "What is the current AI chips market share landscape?",
                }
            ],
        },
        section_status_map={"section_1": "research_retry"},
        pending_replans=[
            {
                "section_id": "section_1",
                "section_order": 1,
                "preferred_action": "request_research",
                "reason": "需要补充对比来源",
                "issue_ids": ["issue_1"],
                "issue_types": ["limited_source_diversity"],
                "follow_up_queries": ["Which sources disagree?"],
                "objective": "Assess AI chips market share",
                "core_question": "What is the current AI chips market share landscape?",
            }
        ],
        aggregate_summary={},
        reportable_section_count=0,
    )

    assert decision.action == SupervisorAction.REPLAN
    assert decision.task_specs[0]["task_kind"] == "section_research"
    assert decision.task_specs[0]["replan_kind"] == "counterevidence"
    assert decision.task_specs[0]["follow_up_queries"][0] == "AI chips opposing view official source"


def test_supervisor_tool_calling_manager_can_delegate_revision(monkeypatch):
    monkeypatch.setattr(
        supervisor_module,
        "create_agent",
        lambda _llm, tools: _FakeToolCallingAgent(
            tools,
            "revise_section",
            {
                "section_id": "section_1",
                "reason": "需要收紧表述并保留限制说明",
                "target_issue_ids": ["issue_1"],
            },
        ),
    )
    supervisor = ResearchSupervisor(object(), {})

    decision = supervisor.decide_section_action(
        outline={
            "required_section_ids": ["section_1"],
            "sections": [
                {
                    "id": "section_1",
                    "section_order": 1,
                    "objective": "Assess AI chips market share",
                    "core_question": "What is the current AI chips market share landscape?",
                }
            ],
        },
        section_status_map={"section_1": "revising"},
        pending_replans=[
            {
                "section_id": "section_1",
                "section_order": 1,
                "preferred_action": "revise_section",
                "reason": "需要收紧表述并保留限制说明",
                "issue_ids": ["issue_1"],
                "issue_types": ["secondary_claim_ungrounded"],
                "follow_up_queries": [],
                "objective": "Assess AI chips market share",
                "core_question": "What is the current AI chips market share landscape?",
                "reportability": "medium",
                "quality_band": "usable_with_limitations",
            }
        ],
        aggregate_summary={},
        reportable_section_count=0,
    )

    assert decision.action == SupervisorAction.REPLAN
    assert decision.task_specs[0]["task_kind"] == "section_revision"
    assert decision.task_specs[0]["replan_kind"] == "revision"
    assert decision.task_specs[0]["issue_ids"] == ["issue_1"]


def test_supervisor_tool_calling_manager_stops_on_failure(monkeypatch):
    monkeypatch.setattr(
        supervisor_module,
        "create_agent",
        lambda _llm, _tools: (_ for _ in ()).throw(RuntimeError("tool calling unavailable")),
    )
    supervisor = ResearchSupervisor(object(), {})

    decision = supervisor.decide_section_action(
        outline={"required_section_ids": ["section_1"]},
        section_status_map={"section_1": "research_retry"},
        pending_replans=[
            {
                "section_id": "section_1",
                "section_order": 1,
                "preferred_action": "request_research",
                "reason": "需要补充研究",
                "issue_ids": ["issue_1"],
                "follow_up_queries": ["AI chips official data"],
                "objective": "Assess AI chips market share",
                "core_question": "What is the current AI chips market share landscape?",
            }
        ],
        aggregate_summary={},
        reportable_section_count=0,
    )

    assert decision.action == SupervisorAction.STOP
    assert "tool-calling manager execution failed" in decision.reasoning
