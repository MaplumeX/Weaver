import agent.runtime.nodes.answer as answer_nodes
import agent.runtime.nodes.chat as chat_nodes


def test_chat_respond_node_returns_plain_answer_without_tools(monkeypatch):
    class _FakeLLM:
        def invoke(self, _messages, config=None):
            return "当然可以，我先用一个简单例子说明。"

    monkeypatch.setattr(chat_nodes, "_chat_model", lambda *_args, **_kwargs: _FakeLLM())
    monkeypatch.setattr(chat_nodes, "_model_for_task", lambda *_args, **_kwargs: "gpt-4o-mini")

    result = chat_nodes.chat_respond_node(
        {
            "input": "解释一下 FastAPI 依赖注入",
            "messages": [],
            "memory_context": {"stored": [], "relevant": []},
        },
        {"configurable": {}},
    )

    assert result["assistant_draft"].startswith("当然可以")
    assert result["needs_tools"] is False
    assert result["required_capabilities"] == []
