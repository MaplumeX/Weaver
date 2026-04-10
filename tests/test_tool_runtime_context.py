from agent.tooling.runtime_context import build_tool_runtime_context


def test_build_tool_runtime_context_reads_profile_contracts():
    context = build_tool_runtime_context(
        {
            "configurable": {
                "thread_id": "thread-ctx-1",
                "user_id": "user-ctx-1",
                "session_id": "session-ctx-1",
                "run_id": "run-ctx-1",
                "agent_profile": {
                    "id": "reporter",
                    "roles": ["reporter"],
                    "capabilities": ["python", "planning"],
                    "blocked_capabilities": ["browser"],
                },
            }
        },
        e2b_ready=True,
    )

    assert context.thread_id == "thread-ctx-1"
    assert context.user_id == "user-ctx-1"
    assert context.session_id == "session-ctx-1"
    assert context.agent_id == "reporter"
    assert context.run_id == "run-ctx-1"
    assert context.roles == ("reporter",)
    assert context.capabilities == ("python", "planning")
    assert context.blocked_capabilities == ("browser",)
    assert context.e2b_ready is True
