from agent.deep_research.agents.supervisor import ResearchSupervisor, SupervisorAction


def test_supervisor_outline_plan_propagates_branch_constraints():
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


def test_supervisor_replan_prefers_counterevidence_research_tasks():
    supervisor = ResearchSupervisor(object(), {})

    decision = supervisor.decide_section_action(
        outline={"required_section_ids": ["section_1"]},
        section_status_map={"section_1": "research_retry"},
        pending_replans=[
            {
                "section_id": "section_1",
                "section_order": 1,
                "preferred_action": "request_research",
                "reason": "需要补充对比来源",
                "issue_ids": ["issue_1"],
                "follow_up_queries": ["AI chips opposing view official source"],
                "missing_topics": ["market share by vendor"],
                "open_questions": ["Which sources disagree?"],
                "needs_counterevidence_query": True,
                "objective": "Assess AI chips market share",
                "core_question": "What is the current AI chips market share landscape?",
            }
        ],
        aggregate_summary={},
        reportable_section_count=0,
    )

    assert decision.action == SupervisorAction.REPLAN
    assert decision.task_specs
    task_spec = decision.task_specs[0]
    assert task_spec["task_kind"] == "section_research"
    assert task_spec["replan_kind"] == "counterevidence"
    assert task_spec["follow_up_queries"][0] == "AI chips opposing view official source"


def test_supervisor_replan_creates_revision_task_specs():
    supervisor = ResearchSupervisor(object(), {})

    decision = supervisor.decide_section_action(
        outline={"required_section_ids": ["section_1"]},
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
    task_spec = decision.task_specs[0]
    assert task_spec["task_kind"] == "section_revision"
    assert task_spec["replan_kind"] == "revision"
    assert task_spec["issue_types"] == ["secondary_claim_ungrounded"]
