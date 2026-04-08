from agent.runtime.deep.roles.supervisor import ResearchSupervisor


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
