from agent.infrastructure.tools import build_agent_toolset
from common.config import settings


def _names(tools):
    return sorted([getattr(t, "name", "") for t in tools if getattr(t, "name", "")])


def test_agent_tools_includes_rag_search_when_enabled_and_configured():
    original = settings.rag_enabled
    settings.rag_enabled = True
    try:
        cfg = {"configurable": {"thread_id": "rag1", "agent_profile": {"tools": ["rag_search"]}}}
        names = _names(build_agent_toolset(cfg))
    finally:
        settings.rag_enabled = original

    assert "rag_search" in names
