"""
Chat-first runtime node.
"""

from __future__ import annotations

import asyncio
from typing import Any

import agent.runtime.nodes._shared as _shared
from agent.infrastructure.tools import build_agent_toolset
from agent.runtime.nodes.prompting import build_chat_runtime_messages

_chat_model = _shared._chat_model
_model_for_task = _shared._model_for_task
_configurable = _shared._configurable
project_state_updates = _shared.project_state_updates
check_cancellation = _shared.check_cancellation
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings


def _resolve_effective_tool_names(
    state: dict[str, Any],
    config,
) -> list[str]:
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    has_profile_contract = any(
        profile.get(key)
        for key in ("tools", "blocked_tools", "roles", "capabilities", "blocked_capabilities")
    )
    if has_profile_contract:
        return sorted(
            {
                str(getattr(tool, "name", "")).strip()
                for tool in build_agent_toolset(config)
                if str(getattr(tool, "name", "")).strip()
            }
        )

    available = {
        str(name).strip() for name in (state.get("available_tools") or []) if str(name).strip()
    }
    blocked = {
        str(name).strip() for name in (state.get("blocked_tools") or []) if str(name).strip()
    }
    return sorted(name for name in available if name not in blocked)


def chat_respond_node(
    state: dict[str, Any],
    config,
) -> dict[str, Any]:
    """
    Default agent-mode node: answer like a normal chat assistant unless tools are required.
    """
    logger.info("Executing chat_respond node")
    try:
        check_cancellation(state)

        effective_tool_names = _resolve_effective_tool_names(state, config)
        if effective_tool_names:
            return project_state_updates(
                state,
                {
                    "assistant_draft": "",
                    "needs_tools": True,
                    "selected_tools": effective_tool_names,
                },
            )

        llm = _chat_model(_model_for_task("writing", config), temperature=0.2)
        messages = build_chat_runtime_messages(state, config)
        response = llm.invoke(messages, config=config)
        content = response.content if hasattr(response, "content") else str(response)

        return project_state_updates(
            state,
            {
                "assistant_draft": content,
                "needs_tools": False,
                "selected_tools": [],
            },
        )
    except asyncio.CancelledError as e:
        return handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"chat_respond node error: {e}", exc_info=settings.debug)
        msg = f"Chat mode failed: {e}"
        return project_state_updates(
            state,
            {
                "assistant_draft": msg,
                "needs_tools": False,
                "selected_tools": [],
                "errors": [msg],
            },
        )


__all__ = ["chat_respond_node"]
