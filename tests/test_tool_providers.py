from __future__ import annotations

from langchain_core.tools import tool

from agent.infrastructure.tools.providers import (
    ProviderContext,
    StaticToolProvider,
    compose_provider_tools,
)


@tool
def alpha(query: str) -> str:
    """alpha"""
    return query


@tool
def beta(query: str) -> str:
    """beta"""
    return query


def test_compose_provider_tools_dedupes_by_tool_name() -> None:
    providers = [
        StaticToolProvider("primary", lambda _ctx: [alpha, beta]),
        StaticToolProvider("secondary", lambda _ctx: [alpha]),
    ]

    tools = compose_provider_tools(
        providers,
        ProviderContext(thread_id="t1", profile={}, configurable={}, e2b_ready=False),
    )

    assert [tool.name for tool in tools] == ["alpha", "beta"]


def test_compose_provider_tools_assigns_thread_id_when_supported() -> None:
    class _ThreadAware:
        name = "thread_aware"
        description = "thread-aware"
        thread_id = "default"

    provider = StaticToolProvider("threaded", lambda _ctx: [_ThreadAware()])
    [tool_obj] = compose_provider_tools(
        [provider],
        ProviderContext(thread_id="worker-7", profile={}, configurable={}, e2b_ready=False),
    )

    assert tool_obj.thread_id == "worker-7"
