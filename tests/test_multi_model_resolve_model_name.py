from agent.foundation import multi_model


def test_resolve_model_name_prefers_runtime_model_override():
    assert (
        multi_model.resolve_model_name(
            "writing",
            {"configurable": {"model": "gpt-runtime-write"}},
        )
        == "gpt-runtime-write"
    )


def test_resolve_model_name_prefers_reasoning_override_for_reasoning_tasks():
    assert (
        multi_model.resolve_model_name(
            "planning",
            {"configurable": {"reasoning_model": "gpt-runtime-plan", "model": "gpt-runtime-write"}},
        )
        == "gpt-runtime-plan"
    )


def test_resolve_model_name_falls_back_for_unknown_task_names():
    assert (
        multi_model.resolve_model_name(
            "legacy_unknown_task",
            {"configurable": {"model": "gpt-runtime-fallback"}},
        )
        == "gpt-runtime-fallback"
    )
