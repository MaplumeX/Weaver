import sys
from pathlib import Path

from langchain_core.messages import AIMessage

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.runtime.nodes.answer as answer_nodes
import agent.runtime.nodes.chat as chat_nodes


def test_chat_respond_node_routes_to_tool_agent_when_profile_has_effective_tools(monkeypatch):
    monkeypatch.setattr(
        chat_nodes,
        "build_agent_toolset",
        lambda _config: [
            type("Tool", (), {"name": "browser_search"})(),
            type("Tool", (), {"name": "crawl_url"})(),
        ],
    )

    result = chat_nodes.chat_respond_node(
        {
            "input": "Use current web search to verify today's price of Bitcoin.",
            "messages": [],
            "memory_context": {"stored": [], "relevant": []},
            "available_tools": [],
            "blocked_tools": [],
        },
        {"configurable": {"agent_profile": {"capabilities": ["search"]}}},
    )

    assert result["needs_tools"] is True
    assert result["selected_tools"] == ["browser_search", "crawl_url"]


def test_tool_agent_node_uses_selected_tools(monkeypatch):
    class FakeAgent:
        def invoke(self, payload, config=None):
            assert payload["messages"]
            return {"messages": [AIMessage(content="Structured comparison")]}

    captured = {}

    monkeypatch.setattr(
        answer_nodes,
        "build_tools_for_names",
        lambda names, _config=None: [
            captured.setdefault("names", sorted(names))
        ]
        and [],
    )
    monkeypatch.setattr(answer_nodes, "build_tool_agent", lambda **_kwargs: FakeAgent())

    result = answer_nodes.tool_agent_node(
        {
            "input": "Compare EV battery supply chain risks across the US and EU in 2025.",
            "messages": [],
            "memory_context": {"stored": [], "relevant": []},
            "selected_tools": ["browser_search", "crawl_url"],
        },
        {"configurable": {}},
    )

    assert captured["names"] == ["browser_search", "crawl_url"]
    assert result["assistant_draft"] == "Structured comparison"


def test_tool_agent_node_falls_back_to_full_agent_toolset_when_not_preselected(monkeypatch):
    class FakeAgent:
        def invoke(self, payload, config=None):
            assert payload["messages"]
            return {"messages": [AIMessage(content="Direct answer without preselection")]}

    captured = {}

    monkeypatch.setattr(
        answer_nodes,
        "build_agent_toolset",
        lambda _config: [
            captured.setdefault("tool_names", ["browser_search", "crawl_url"])
        ]
        and [
            type("Tool", (), {"name": "browser_search"})(),
            type("Tool", (), {"name": "crawl_url"})(),
        ],
    )
    monkeypatch.setattr(answer_nodes, "build_tool_agent", lambda **_kwargs: FakeAgent())

    result = answer_nodes.tool_agent_node(
        {
            "input": "Summarize the latest EV battery market dynamics.",
            "messages": [],
            "memory_context": {"stored": [], "relevant": []},
            "selected_tools": [],
        },
        {"configurable": {"agent_profile": {"capabilities": ["search"]}}},
    )

    assert captured["tool_names"] == ["browser_search", "crawl_url"]
    assert result["assistant_draft"] == "Direct answer without preselection"
