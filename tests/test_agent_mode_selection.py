import sys
from pathlib import Path

from langchain_core.messages import AIMessage

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.runtime.nodes.answer as answer_nodes
import agent.runtime.nodes.chat as chat_nodes


def test_chat_respond_node_marks_current_info_queries_for_web_search():
    result = chat_nodes.chat_respond_node(
        {
            "input": "Use current web search to verify today's price of Bitcoin.",
            "messages": [],
            "memory_context": {"stored": [], "relevant": []},
        },
        {"configurable": {}},
    )

    assert result["needs_tools"] is True
    assert result["required_capabilities"] == ["web_search"]
    assert "deterministic" in result["tool_reason"]


def test_tool_agent_node_uses_capability_based_toolset(monkeypatch):
    class FakeAgent:
        def invoke(self, payload, config=None):
            assert payload["messages"]
            return {"messages": [AIMessage(content="Structured comparison")]}

    captured = {}

    monkeypatch.setattr(
        answer_nodes,
        "build_tools_for_capabilities",
        lambda capabilities, _config: captured.setdefault("capabilities", list(capabilities)) or [],
    )
    monkeypatch.setattr(answer_nodes, "build_tool_agent", lambda **_kwargs: FakeAgent())

    result = answer_nodes.tool_agent_node(
        {
            "input": "Compare EV battery supply chain risks across the US and EU in 2025.",
            "messages": [],
            "memory_context": {"stored": [], "relevant": []},
            "required_capabilities": ["web_search"],
        },
        {"configurable": {}},
    )

    assert captured["capabilities"] == ["web_search"]
    assert result["assistant_draft"] == "Structured comparison"
