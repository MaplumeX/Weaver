from __future__ import annotations

import importlib


def test_agent_package_exports_public_symbols() -> None:
    agent = importlib.import_module("agent")
    removed_symbol = "initialize" + "_enhanced_tools"

    expected = [
        "AgentState",
        "ToolEvent",
        "build_execution_request",
        "build_initial_agent_state",
        "create_checkpointer",
        "create_research_graph",
        "event_stream_generator",
        "get_default_agent_prompt",
        "get_emitter",
        "remove_emitter",
    ]

    missing = [name for name in expected if not hasattr(agent, name)]
    assert missing == []
    assert not hasattr(agent, removed_symbol)
