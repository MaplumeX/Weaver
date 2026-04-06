import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.tools import tool  # noqa: E402

from agent.domain import ToolCapability  # noqa: E402
from agent.infrastructure.tools import (  # noqa: E402
    StaticToolProvider,
    build_agent_toolset,
    build_tools_for_capabilities,
)
from agent.infrastructure.tools.assembly import build_tool_inventory  # noqa: E402
from agent.infrastructure.tools.capabilities import resolve_tool_names_for_capabilities  # noqa: E402
from common.config import settings  # noqa: E402


def _names(tools):
    return sorted([getattr(t, "name", "") for t in tools if getattr(t, "name", "")])


@tool
def gamma(query: str) -> str:
    """gamma"""
    return query


def test_build_tool_inventory_returns_unfiltered_provider_union(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_default_tool_providers",
        lambda: [StaticToolProvider("custom", lambda _ctx: [gamma])],
    )

    tools = build_tool_inventory({"configurable": {"thread_id": "inv-1", "agent_profile": {}}})

    assert [tool.name for tool in tools] == ["gamma"]


def test_agent_tools_lightweight_browser_selected_by_default():
    cfg = {
        "configurable": {"thread_id": "t1", "agent_profile": {"enabled_tools": {"browser": True}}}
    }
    names = _names(build_agent_toolset(cfg))
    assert "browser_navigate" in names
    assert "sb_browser_navigate" not in names


def test_agent_tools_sandbox_browser_selected_when_enabled():
    # Sandbox tools require a configured E2B API key.
    original_key = settings.e2b_api_key
    settings.e2b_api_key = "e2b_test_key"
    try:
        cfg = {
            "configurable": {
                "thread_id": "t2",
                "agent_profile": {"enabled_tools": {"sandbox_browser": True}},
            }
        }
        names = _names(build_agent_toolset(cfg))
    finally:
        settings.e2b_api_key = original_key
    assert "sb_browser_navigate" in names
    assert "browser_navigate" not in names


def test_agent_tools_web_dev_tools_when_enabled():
    # Sandbox tools require a configured E2B API key.
    original_key = settings.e2b_api_key
    settings.e2b_api_key = "e2b_test_key"
    try:
        cfg = {
            "configurable": {
                "thread_id": "t3",
                "agent_profile": {
                    "enabled_tools": {
                        "sandbox_web_dev": True,
                    }
                },
            }
        }
        names = _names(build_agent_toolset(cfg))
    finally:
        settings.e2b_api_key = original_key
    assert "sandbox_scaffold_web_project" in names
    assert "sandbox_deploy_web_project" in names


def test_agent_tools_prefer_api_search_over_sandbox_search_when_web_search_enabled():
    original_key = settings.e2b_api_key
    original_search_engines = settings.search_engines
    original_mode = settings.sandbox_mode
    settings.e2b_api_key = "e2b_test_key"
    settings.search_engines = "tavily,serper"
    settings.sandbox_mode = "local"
    try:
        cfg = {
            "configurable": {
                "thread_id": "t4",
                "agent_profile": {
                    "enabled_tools": {
                        "web_search": True,
                        "sandbox_web_search": True,
                    }
                },
            }
        }
        names = _names(build_agent_toolset(cfg))
    finally:
        settings.e2b_api_key = original_key
        settings.search_engines = original_search_engines
        settings.sandbox_mode = original_mode
    assert "fallback_search" in names
    assert "sandbox_web_search" not in names
    assert "sandbox_search_and_click" not in names
    assert "sandbox_extract_search_results" not in names


def test_agent_tools_include_sandbox_search_when_api_search_disabled():
    original_key = settings.e2b_api_key
    original_search_engines = settings.search_engines
    original_mode = settings.sandbox_mode
    settings.e2b_api_key = "e2b_test_key"
    settings.search_engines = "tavily,serper"
    settings.sandbox_mode = "local"
    try:
        cfg = {
            "configurable": {
                "thread_id": "t5",
                "agent_profile": {
                    "enabled_tools": {
                        "web_search": False,
                        "sandbox_web_search": True,
                    }
                },
            }
        }
        names = _names(build_agent_toolset(cfg))
    finally:
        settings.e2b_api_key = original_key
        settings.search_engines = original_search_engines
        settings.sandbox_mode = original_mode
    assert "fallback_search" not in names
    assert "sandbox_web_search" in names


def test_agent_tools_include_task_list_tools_by_default():
    cfg = {
        "configurable": {
            "thread_id": "t_default_tasks",
            "agent_profile": {"enabled_tools": {}},
        }
    }
    names = _names(build_agent_toolset(cfg))
    assert "create_tasks" in names
    assert "view_tasks" in names
    assert "update_task" in names
    assert "get_next_task" in names
    assert "plan_steps" in names


def test_build_agent_toolset_applies_whitelist_after_inventory():
    cfg = {
        "configurable": {
            "thread_id": "t-white",
            "agent_profile": {
                "tool_whitelist": ["browser_navigate"],
                "enabled_tools": {"browser": True},
            },
        }
    }
    names = _names(build_agent_toolset(cfg))
    assert names == ["browser_navigate"]


def test_search_capability_aliases_only_include_exposed_search_tools():
    names = resolve_tool_names_for_capabilities([ToolCapability.SEARCH.value])

    assert "fallback_search" in names
    assert "tavily_search" in names
    assert "multi_search" not in names


def test_build_tools_for_capabilities_limits_tools_to_search_family():
    cfg = {
        "configurable": {
            "thread_id": "cap-1",
            "agent_profile": {"enabled_tools": {"web_search": True, "browser": True}},
        }
    }

    names = _names(build_tools_for_capabilities(["web_search"], cfg))

    assert "fallback_search" in names
    assert "browser_navigate" not in names


def test_build_tools_for_capabilities_returns_empty_list_for_empty_request():
    cfg = {"configurable": {"thread_id": "cap-2", "agent_profile": {"enabled_tools": {}}}}

    assert build_tools_for_capabilities([], cfg) == []
