import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain.agents.middleware.todo import (
    WRITE_TODOS_SYSTEM_PROMPT,
    WRITE_TODOS_TOOL_DESCRIPTION,
)

import agent.tooling.agents.factory as agent_factory
from common.config import Settings


def test_build_middlewares_include_retry_and_limit_by_default(monkeypatch):
    settings_with_defaults = Settings(_env_file=None)
    monkeypatch.setattr(agent_factory, "settings", settings_with_defaults)

    middlewares = agent_factory._build_middlewares()
    names = {type(middleware).__name__ for middleware in middlewares}

    assert "ProviderSafeToolSelectorMiddleware" in names
    assert "ToolRetryMiddleware" in names
    assert "ToolCallLimitMiddleware" in names
    assert "TodoListMiddleware" in names

    selector = next(
        middleware
        for middleware in middlewares
        if type(middleware).__name__ == "ProviderSafeToolSelectorMiddleware"
    )
    assert "write_todos" in selector.always_include


def test_build_middlewares_keep_todo_defaults_when_settings_blank(monkeypatch):
    settings_with_defaults = Settings(
        _env_file=None,
        enable_todo_middleware=True,
        todo_system_prompt="",
        todo_tool_description="",
    )
    monkeypatch.setattr(agent_factory, "settings", settings_with_defaults)

    middlewares = agent_factory._build_middlewares()
    todo_middleware = next(
        middleware
        for middleware in middlewares
        if type(middleware).__name__ == "TodoListMiddleware"
    )

    assert todo_middleware.system_prompt == WRITE_TODOS_SYSTEM_PROMPT
    assert todo_middleware.tool_description == WRITE_TODOS_TOOL_DESCRIPTION


def test_non_openai_selector_prefers_json_mode(monkeypatch):
    settings_with_defaults = Settings(
        _env_file=None,
        openai_base_url="https://api.deepseek.com/v1",
    )
    monkeypatch.setattr(agent_factory, "settings", settings_with_defaults)

    assert agent_factory._tool_selector_methods() == (
        "json_mode",
        "function_calling",
        "json_schema",
    )

def test_resolve_deep_research_role_tool_names_respects_supervisor_policy():
    allowed = agent_factory.resolve_deep_research_role_tool_names(
        "supervisor",
        enable_supervisor_world_tools=False,
    )
    assert allowed == {"fabric"}

    widened = agent_factory.resolve_deep_research_role_tool_names(
        "supervisor",
        enable_supervisor_world_tools=True,
    )
    assert {"fabric", "browser_navigate", "browser_search"} <= widened


def test_resolve_deep_research_role_tool_names_respects_reporter_python_policy():
    allowed = agent_factory.resolve_deep_research_role_tool_names(
        "reporter",
        enable_reporter_python_tools=True,
    )
    assert "execute_python_code" in allowed

    restricted = agent_factory.resolve_deep_research_role_tool_names(
        "reporter",
        enable_reporter_python_tools=False,
    )
    assert "execute_python_code" not in restricted


def test_resolve_deep_research_role_tool_names_expands_allowed_tool_aliases():
    allowed = agent_factory.resolve_deep_research_role_tool_names(
        "researcher",
        allowed_tools=["search", "extract"],
    )

    assert {
        "web_search",
        "browser_search",
        "crawl_url",
        "browser_extract_text",
        "sb_browser_extract_text",
        "sandbox_extract_search_results",
    } <= allowed


def test_researcher_role_keeps_legacy_search_read_extract_coverage():
    allowed = agent_factory.resolve_deep_research_role_tool_names("researcher")

    assert {
        "fabric",
        "web_search",
        "browser_search",
        "sandbox_web_search",
        "sandbox_search_and_click",
        "sandbox_extract_search_results",
        "browser_navigate",
        "browser_click",
        "crawl_url",
        "crawl_urls",
        "sb_browser_navigate",
        "sb_browser_click",
        "sb_browser_type",
        "sb_browser_press",
        "sb_browser_scroll",
        "sb_browser_extract_text",
        "sb_browser_screenshot",
    } <= allowed
