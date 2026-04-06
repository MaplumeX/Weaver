from langchain_core.messages import AIMessage, HumanMessage

from agent.runtime.nodes.prompting import build_chat_runtime_messages


def test_build_chat_runtime_messages_uses_real_history_and_turn_context():
    state = {
        "input": "继续讲一下依赖覆盖怎么测",
        "images": [],
        "messages": [
            HumanMessage(content="先解释一下 FastAPI 依赖注入"),
            AIMessage(content="它允许你把共享依赖声明为参数。"),
        ],
        "memory_context": {
            "stored": ["用户喜欢简洁回答"],
            "relevant": ["之前在问 FastAPI 测试"],
        },
    }
    config = {
        "configurable": {
            "agent_profile": {
                "system_prompt": "You are a concise assistant.",
            }
        }
    }

    messages = build_chat_runtime_messages(state, config)

    assert messages[0].type == "system"
    assert "You are a concise assistant." in messages[0].content
    assert "用户喜欢简洁回答" in messages[0].content
    assert "之前在问 FastAPI 测试" in messages[0].content
    assert messages[1].content == "先解释一下 FastAPI 依赖注入"
    assert messages[2].content == "它允许你把共享依赖声明为参数。"
    assert messages[-1].content == "继续讲一下依赖覆盖怎么测"
