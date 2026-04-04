from agent.application import build_execution_request, build_initial_agent_state
from agent.core.state import project_state_updates


def test_build_initial_agent_state_projects_structured_slices():
    request = build_execution_request(
        input_text="AI chips roadmap",
        thread_id="thread-1",
        user_id="user-1",
        mode_info={"mode": "deep"},
        agent_profile={
            "id": "researcher",
            "system_prompt": "You are a custom analyst.",
            "enabled_tools": {"web_search": True},
        },
        options={"max_revisions": 4, "tool_call_limit": 9},
    )

    state = build_initial_agent_state(
        request,
        stored_memories=["Remember to compare vendors"],
        relevant_memories=["Past note about AI accelerator demand"],
    )

    assert state["route"] == "deep"
    assert state["conversation_state"]["thread_id"] == "thread-1"
    assert state["execution_state"]["mode"] == "deep_research"
    assert state["execution_state"]["tool_call_limit"] == 9
    assert state["research_state"]["research_plan"] == []
    assert state["runtime_snapshot"]["deep_runtime"]["engine"]
    assert len(state["messages"]) == 3


def test_project_state_updates_keeps_structured_state_in_sync():
    request = build_execution_request(
        input_text="Latest AI chip prices",
        thread_id="thread-2",
        user_id="user-2",
        mode_info={"mode": "agent"},
        agent_profile={"id": "default", "enabled_tools": {"web_search": True}},
    )
    state = build_initial_agent_state(request)

    projected = project_state_updates(
        state,
        {
            "route": "clarify",
            "routing_confidence": 0.42,
            "clarification_question": "Which market do you care about?",
            "needs_clarification": True,
        },
    )

    assert projected["execution_state"]["route"] == "clarify"
    assert projected["execution_state"]["mode"] == "clarify"
    assert projected["execution_state"]["routing_confidence"] == 0.42
    assert projected["conversation_state"]["clarification_question"] == "Which market do you care about?"

