import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.tools import tool

from agent.infrastructure.tools import StaticToolProvider, ToolSpec, build_agent_toolset
from agent.infrastructure.tools.assembly import build_tool_inventory


def _names(tools):
    return sorted([getattr(t, "name", "") for t in tools if getattr(t, "name", "")])


@tool
def alpha(query: str) -> str:
    """alpha"""
    return query


@tool
def beta(query: str) -> str:
    """beta"""
    return query


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


def test_build_agent_toolset_filters_inventory_by_concrete_profile_tools(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_tool_inventory",
        lambda _config: [alpha, beta, gamma],
    )

    cfg = {
        "configurable": {
            "thread_id": "tools-1",
            "agent_profile": {
                "tools": ["alpha", "gamma"],
                "blocked_tools": ["beta"],
                "emit_tool_events": False,
            },
        }
    }

    names = _names(build_agent_toolset(cfg))

    assert names == ["alpha", "gamma"]


def test_build_agent_toolset_applies_blocked_tools_after_allowlist(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_tool_inventory",
        lambda _config: [alpha, beta, gamma],
    )

    cfg = {
        "configurable": {
            "thread_id": "tools-2",
            "agent_profile": {
                "tools": ["alpha", "beta"],
                "blocked_tools": ["beta"],
                "emit_tool_events": False,
            },
        }
    }

    names = _names(build_agent_toolset(cfg))

    assert names == ["alpha"]


def test_build_agent_toolset_keeps_live_mcp_tools_for_protected_profiles(monkeypatch):
    class _Tool:
        def __init__(self, name: str):
            self.name = name
            self.description = name

    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_tool_inventory",
        lambda _config: [_Tool("alpha"), _Tool("mcp_fetch")],
    )
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.get_live_mcp_tools",
        lambda: [_Tool("mcp_fetch")],
    )

    cfg = {
        "configurable": {
            "thread_id": "tools-3",
            "agent_profile": {
                "tools": ["alpha"],
                "blocked_tools": [],
                "emit_tool_events": False,
                "metadata": {"protected": True},
            },
        }
    }

    names = _names(build_agent_toolset(cfg))

    assert names == ["alpha", "mcp_fetch"]


def test_build_agent_toolset_resolves_capabilities_to_concrete_tools(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_tool_inventory",
        lambda _config: [alpha, beta, gamma],
    )
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_tool_registry",
        lambda _config: {
            "alpha": ToolSpec(tool_id="alpha", tool_name="alpha", capabilities=("search",)),
            "beta": ToolSpec(tool_id="beta", tool_name="beta", capabilities=("browser",)),
            "gamma": ToolSpec(tool_id="gamma", tool_name="gamma", capabilities=("python",)),
        },
    )

    cfg = {
        "configurable": {
            "thread_id": "tools-4",
            "agent_profile": {
                "capabilities": ["browser"],
                "emit_tool_events": False,
            },
        }
    }

    names = _names(build_agent_toolset(cfg))

    assert names == ["beta"]


def test_build_agent_toolset_blocks_tools_via_blocked_capabilities(monkeypatch):
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_tool_inventory",
        lambda _config: [alpha, beta, gamma],
    )
    monkeypatch.setattr(
        "agent.infrastructure.tools.assembly.build_tool_registry",
        lambda _config: {
            "alpha": ToolSpec(tool_id="alpha", tool_name="alpha", capabilities=("search",)),
            "beta": ToolSpec(tool_id="beta", tool_name="beta", capabilities=("browser",)),
            "gamma": ToolSpec(tool_id="gamma", tool_name="gamma", capabilities=("python",)),
        },
    )

    cfg = {
        "configurable": {
            "thread_id": "tools-5",
            "agent_profile": {
                "tools": ["alpha", "beta", "gamma"],
                "blocked_capabilities": ["python", "browser"],
                "emit_tool_events": False,
            },
        }
    }

    names = _names(build_agent_toolset(cfg))

    assert names == ["alpha"]
