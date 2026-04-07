"""
Chat-first answer-generation graph nodes.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from langchain_core.messages import AIMessage

import agent.infrastructure.agents.factory as _agent_factory
import agent.infrastructure.tools as _tools
import agent.runtime.nodes._shared as _shared
from agent.runtime.nodes.prompting import build_chat_runtime_messages

project_state_updates = _shared.project_state_updates
check_cancellation = _shared.check_cancellation
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings
build_tool_agent = _agent_factory.build_tool_agent
build_tools_for_names = _tools.build_tools_for_names


def _needs_browser_hint(selected_tools: list[str] | None) -> bool:
    for name in (selected_tools or []):
        tool_name = str(name or "").strip()
        if tool_name.startswith(("browser_", "sb_browser_")):
            return True
        if tool_name in {"browser_use", "sandbox_web_search", "sandbox_search_and_click"}:
            return True
    return False


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


def tool_agent_node(
    state: dict[str, Any],
    config,
    *,
    _deps: Any = None,
) -> dict[str, Any]:
    """
    Escalated tool path that reuses the existing LangChain tool-calling agent.
    """
    deps = _resolve_deps(_deps)
    logger.info("Executing tool_agent node")
    try:
        deps.check_cancellation(state)

        tools = deps.build_tools_for_names(set(state.get("selected_tools") or []), config)
        agent = deps.build_tool_agent(
            model=deps._shared._model_for_task("research", config),
            tools=tools,
            temperature=0.7,
        )

        include_browser_hint = _needs_browser_hint(state.get("selected_tools") or [])
        messages = build_chat_runtime_messages(
            state,
            config,
            include_browser_hint=include_browser_hint,
        )
        response = agent.invoke({"messages": messages}, config=config)

        if isinstance(response, dict) and response.get("messages"):
            last = response["messages"][-1]
            text = getattr(last, "content", "") if hasattr(last, "content") else str(last)
        else:
            text = getattr(response, "content", None) or str(response)

        return deps.project_state_updates(
            state,
            {
                "assistant_draft": text,
                "tool_observations": [{"tool": getattr(tool, "name", "")} for tool in tools],
                "messages": [AIMessage(content=text)],
            },
        )
    except asyncio.CancelledError as e:
        return deps.handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"tool_agent node error: {e}", exc_info=settings.debug)
        msg = f"Agent tool path failed: {e}"
        return deps.project_state_updates(
            state,
            {
                "assistant_draft": msg,
                "errors": [msg],
            },
        )
__all__ = ["tool_agent_node"]
