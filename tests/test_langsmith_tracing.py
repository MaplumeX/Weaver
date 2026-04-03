import importlib
import os
import sys


def test_sync_langsmith_env_sets_and_clears(monkeypatch):
    from common.langsmith import sync_langsmith_env

    monkeypatch.setenv("LANGSMITH_API_KEY", "stale-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "stale-project")

    sync_langsmith_env(
        tracing=True,
        api_key="test-key",
        project="weaver-test",
        endpoint="https://api.smith.langchain.com",
        workspace_id="ws_123",
    )

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "test-key"
    assert os.environ["LANGSMITH_PROJECT"] == "weaver-test"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://api.smith.langchain.com"
    assert os.environ["LANGSMITH_WORKSPACE_ID"] == "ws_123"

    sync_langsmith_env(
        tracing=False,
        api_key="",
        project="",
        endpoint="",
        workspace_id="",
    )

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert "LANGSMITH_API_KEY" not in os.environ
    assert "LANGSMITH_PROJECT" not in os.environ
    assert "LANGSMITH_ENDPOINT" not in os.environ
    assert "LANGSMITH_WORKSPACE_ID" not in os.environ


def test_build_agent_graph_config_includes_langsmith_context():
    main = sys.modules.get("main") or importlib.import_module("main")

    config = main._build_agent_graph_config(
        thread_id="thread_123",
        model="gpt-4o-mini",
        mode_info={"mode": "deep"},
        agent_profile=None,
        user_id="user_123",
        stream=True,
    )

    assert config["run_name"] == "weaver-chat-deep"
    assert config["tags"] == ["weaver", "surface:chat", "mode:deep", "stream"]
    assert config["metadata"]["thread_id"] == "thread_123"
    assert config["metadata"]["user_id"] == "user_123"
    assert config["metadata"]["model"] == "gpt-4o-mini"
    assert config["metadata"]["surface"] == "chat"
    assert config["metadata"]["mode"] == "deep"
    assert config["metadata"]["agent_id"] == "default"
    assert config["metadata"]["resumed_from_checkpoint"] is False


def test_build_agent_graph_config_marks_resume_runs():
    main = sys.modules.get("main") or importlib.import_module("main")

    config = main._build_agent_graph_config(
        thread_id="thread_resume",
        model="gpt-4o-mini",
        mode_info={"mode": "agent"},
        agent_profile=None,
        user_id="user_resume",
        resumed_from_checkpoint=True,
        stream=False,
    )

    assert config["run_name"] == "weaver-chat-agent"
    assert config["tags"] == ["weaver", "surface:chat", "mode:agent", "sync", "resume"]
    assert config["metadata"]["resumed_from_checkpoint"] is True
