from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import agent.foundation.state as state_module
from agent.execution import build_execution_request, build_initial_agent_state
from agent.foundation.state import project_state_updates


def test_build_initial_agent_state_seeds_agent_history_and_current_input():
    request = build_execution_request(
        input_text="帮我解释一下 FastAPI 的依赖注入",
        thread_id="thread-chat-1",
        user_id="user-1",
        mode_info={"mode": "agent"},
        agent_profile={
            "id": "default",
            "system_prompt": "You are a calm assistant.",
            "tools": ["browser_search", "crawl_url"],
        },
    )

    state = build_initial_agent_state(
        request,
        stored_memories=["用户喜欢简洁回答"],
        relevant_memories=["上次问过 FastAPI 路由组织"],
        short_term_context={
            "rolling_summary": "已经解释过 APIRouter。",
            "pinned_items": ["请用中文回答"],
        },
        history_messages=[
            HumanMessage(content="先解释一下 FastAPI 路由"),
            AIMessage(content="可以，先从 APIRouter 开始。"),
        ],
    )

    assert [message.content for message in state["messages"]] == [
        "先解释一下 FastAPI 路由",
        "可以，先从 APIRouter 开始。",
        "帮我解释一下 FastAPI 的依赖注入",
    ]
    assert state["memory_context"] == {
        "stored": ["用户喜欢简洁回答"],
        "relevant": ["上次问过 FastAPI 路由组织"],
    }
    assert state["short_term_context"]["rolling_summary"] == "已经解释过 APIRouter。"
    assert state["short_term_context"]["pinned_items"] == ["请用中文回答"]
    assert "conversation_state" not in state
    assert "research_state" not in state
    assert "runtime_snapshot" not in state


def test_build_initial_agent_state_uses_concrete_tools_contract():
    request = build_execution_request(
        input_text="帮我打开 OpenAI 首页并总结要点",
        thread_id="tool-state-1",
        user_id="user-1",
        mode_info={"mode": "agent"},
        agent_profile={
            "id": "default",
            "tools": ["browser_search", "browser_navigate", "crawl_url"],
            "blocked_tools": ["browser_click"],
        },
    )

    state = build_initial_agent_state(request)

    assert state["selected_tools"] == []
    assert state["roles"] == []
    assert state["available_capabilities"] == []
    assert state["blocked_capabilities"] == []
    assert state["available_tools"] == ["browser_search", "browser_navigate", "crawl_url"]
    assert state["blocked_tools"] == ["browser_click"]
    assert "tool_call_limit" not in state
    assert "tool_call_count" not in state


def test_build_initial_agent_state_projects_role_and_capability_contracts():
    request = build_execution_request(
        input_text="帮我汇总 AI 芯片路线图",
        thread_id="cap-state-1",
        user_id="user-1",
        mode_info={"mode": "agent"},
        agent_profile={
            "id": "reporter",
            "roles": ["reporter"],
            "capabilities": ["python", "planning"],
            "blocked_capabilities": ["browser"],
            "tools": ["execute_python_code"],
        },
    )

    state = build_initial_agent_state(request)

    assert state["roles"] == ["reporter"]
    assert state["available_capabilities"] == ["python", "planning"]
    assert state["blocked_capabilities"] == ["browser"]
    assert state["available_tools"] == ["execute_python_code"]


def test_build_initial_agent_state_keeps_runtime_state_minimal():
    request = build_execution_request(
        input_text="AI chips roadmap",
        thread_id="thread-1",
        user_id="user-1",
        mode_info={"mode": "deep"},
        agent_profile={
            "id": "researcher",
            "system_prompt": "You are a custom analyst.",
            "tools": ["browser_search", "crawl_url"],
        },
        options={"tool_call_limit": 9},
    )

    state = build_initial_agent_state(
        request,
        stored_memories=["Remember to compare vendors"],
        relevant_memories=["Past note about AI accelerator demand"],
    )

    assert state["route"] == "deep"
    assert len(state["messages"]) == 1
    assert state["deep_runtime"]["engine"]
    assert state["memory_context"] == {
        "stored": ["Remember to compare vendors"],
        "relevant": ["Past note about AI accelerator demand"],
    }
    assert "conversation_state" not in state
    assert "execution_state" not in state
    assert "research_state" not in state
    assert "runtime_snapshot" not in state
    assert "routing_reasoning" not in state
    assert "routing_confidence" not in state
    assert "tool_reason" not in state
    assert "code_results" not in state
    assert "tool_observations" not in state
    assert "tool_call_limit" not in state
    assert "research_plan" not in state
    assert "current_step" not in state
    assert "suggested_queries" not in state
    assert "needs_clarification" not in state
    assert "clarification_question" not in state
    assert "max_revisions" not in state


def test_prepare_seed_messages_applies_trim_policy_to_seeded_history(monkeypatch):
    monkeypatch.setattr(state_module.settings, "trim_messages", True)
    monkeypatch.setattr(state_module.settings, "trim_messages_keep_first", 1)
    monkeypatch.setattr(state_module.settings, "trim_messages_keep_last", 2)
    monkeypatch.setattr(state_module.settings, "summary_messages", False)

    prepared = state_module.prepare_seed_messages(
        [
            SystemMessage(content="system"),
            HumanMessage(content="u1"),
            AIMessage(content="a1"),
            HumanMessage(content="u2"),
            AIMessage(content="a2"),
        ]
    )

    assert [message.content for message in prepared] == ["system", "u2", "a2"]


def test_prepare_seed_messages_can_summarize_without_plain_trim(monkeypatch):
    monkeypatch.setattr(state_module.settings, "trim_messages", False)
    monkeypatch.setattr(state_module.settings, "trim_messages_keep_first", 1)
    monkeypatch.setattr(state_module.settings, "trim_messages_keep_last", 2)
    monkeypatch.setattr(state_module.settings, "summary_messages", True)
    monkeypatch.setattr(state_module.settings, "summary_messages_trigger", 4)
    monkeypatch.setattr(state_module.settings, "summary_messages_keep_last", 1)
    monkeypatch.setattr(
        state_module,
        "summarize_messages",
        lambda middle: SystemMessage(
            content="Conversation summary:\n" + " | ".join(message.content for message in middle)
        ),
    )

    prepared = state_module.prepare_seed_messages(
        [
            SystemMessage(content="system"),
            HumanMessage(content="u1"),
            AIMessage(content="a1"),
            HumanMessage(content="u2"),
            AIMessage(content="a2"),
        ]
    )

    assert [message.content for message in prepared] == [
        "system",
        "Conversation summary:\nu1 | a1 | u2",
        "a2",
    ]


def test_project_state_updates_returns_explicit_updates_only():
    request = build_execution_request(
        input_text="Latest AI chip prices",
        thread_id="thread-2",
        user_id="user-2",
        mode_info={"mode": "agent"},
        agent_profile={"id": "default", "tools": ["browser_search"]},
    )
    state = build_initial_agent_state(request)

    projected = project_state_updates(
        state,
        {
            "route": "agent",
            "domain": "general",
        },
    )

    assert projected == {"route": "agent", "domain": "general"}
