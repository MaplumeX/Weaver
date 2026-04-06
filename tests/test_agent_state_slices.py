from agent.application import build_execution_request, build_initial_agent_state
from agent.core.state import project_state_updates


def test_build_initial_agent_state_keeps_agent_messages_clean_and_stores_memory_context():
    request = build_execution_request(
        input_text="帮我解释一下 FastAPI 的依赖注入",
        thread_id="thread-chat-1",
        user_id="user-1",
        mode_info={"mode": "agent"},
        agent_profile={
            "id": "default",
            "system_prompt": "You are a calm assistant.",
            "enabled_tools": {"web_search": True},
        },
    )

    state = build_initial_agent_state(
        request,
        stored_memories=["用户喜欢简洁回答"],
        relevant_memories=["上次问过 FastAPI 路由组织"],
    )

    assert state["messages"] == []
    assert state["memory_context"] == {
        "stored": ["用户喜欢简洁回答"],
        "relevant": ["上次问过 FastAPI 路由组织"],
    }
    assert state["research_state"]["memory_context"] == state["memory_context"]
    assert state["conversation_state"]["messages"] == []


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
        options={"tool_call_limit": 9},
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
    assert state["runtime_snapshot"]["deep_runtime"]["engine"]
    assert len(state["messages"]) == 1
    assert state["memory_context"] == {
        "stored": ["Remember to compare vendors"],
        "relevant": ["Past note about AI accelerator demand"],
    }
    assert state["research_state"]["memory_context"] == state["memory_context"]
    assert "research_plan" not in state
    assert "current_step" not in state
    assert "suggested_queries" not in state
    assert "needs_clarification" not in state
    assert "clarification_question" not in state
    assert "max_revisions" not in state
    assert "research_plan" not in state["research_state"]
    assert "clarification_question" not in state["conversation_state"]


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
            "route": "agent",
            "routing_confidence": 0.42,
        },
    )

    assert projected["execution_state"]["route"] == "agent"
    assert projected["execution_state"]["mode"] == "tool_assisted"
    assert projected["execution_state"]["routing_confidence"] == 0.42
    assert "clarification_question" not in projected["conversation_state"]
    assert "research_plan" not in projected["research_state"]
