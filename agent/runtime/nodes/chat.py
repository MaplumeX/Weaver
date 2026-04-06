"""
Chat-first runtime node.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import agent.runtime.nodes._shared as _shared
from agent.runtime.nodes.prompting import build_chat_runtime_messages

_chat_model = _shared._chat_model
_model_for_task = _shared._model_for_task
project_state_updates = _shared.project_state_updates
check_cancellation = _shared.check_cancellation
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings


def _select_tools_for_input(
    user_input: str,
    *,
    available_tools: list[str] | None = None,
    blocked_tools: list[str] | None = None,
) -> list[str]:
    text = str(user_input or "").strip().lower()
    if not text:
        return []

    available = {str(name).strip() for name in (available_tools or []) if str(name).strip()}
    blocked = {str(name).strip() for name in (blocked_tools or []) if str(name).strip()}
    selected: list[str] = []

    if any(token in text for token in ("latest", "today", "current", "price", "news")):
        selected.extend(["browser_search", "crawl_url"])
    if any(token in text for token in ("open ", "website", "browse", "click", "login")):
        selected.extend(["browser_navigate", "browser_click"])
    if any(token in text for token in ("file", "read ", "write ", "save ", "download")):
        selected.extend(
            [
                "sandbox_read_file",
                "sandbox_create_file",
                "sandbox_update_file",
                "sandbox_str_replace",
            ]
        )
    if any(token in text for token in ("python", "script", "calculate", "chart", "plot")):
        selected.append("execute_python_code")

    if available:
        selected = [name for name in selected if name in available]
    if blocked:
        selected = [name for name in selected if name not in blocked]

    return sorted(set(selected))


def chat_respond_node(
    state: Dict[str, Any],
    config,
) -> Dict[str, Any]:
    """
    Default agent-mode node: answer like a normal chat assistant unless tools are required.
    """
    logger.info("Executing chat_respond node")
    try:
        check_cancellation(state)

        selected_tools = _select_tools_for_input(
            state.get("input", ""),
            available_tools=state.get("available_tools") or [],
            blocked_tools=state.get("blocked_tools") or [],
        )
        if selected_tools:
            return project_state_updates(
                state,
                {
                    "assistant_draft": "",
                    "needs_tools": True,
                    "tool_reason": "deterministic capability rules matched the user request",
                    "selected_tools": selected_tools,
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
                "tool_reason": "",
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
                "tool_reason": "",
                "selected_tools": [],
                "errors": [msg],
            },
        )


__all__ = ["chat_respond_node"]
