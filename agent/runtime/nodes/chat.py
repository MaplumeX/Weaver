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


def _detect_required_capabilities(user_input: str) -> list[str]:
    text = str(user_input or "").strip().lower()
    if not text:
        return []

    capabilities: list[str] = []

    if any(token in text for token in ("latest", "today", "current", "price", "news")):
        capabilities.append("web_search")
    if any(token in text for token in ("open ", "website", "browse", "click", "login")):
        capabilities.append("browser")
    if any(token in text for token in ("file", "read ", "write ", "save ", "download")):
        capabilities.append("files")
    if any(token in text for token in ("python", "script", "calculate", "chart", "plot")):
        capabilities.append("python")

    return sorted(set(capabilities))


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

        required_capabilities = _detect_required_capabilities(state.get("input", ""))
        if required_capabilities:
            return project_state_updates(
                state,
                {
                    "assistant_draft": "",
                    "needs_tools": True,
                    "tool_reason": "deterministic capability rules matched the user request",
                    "required_capabilities": required_capabilities,
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
                "required_capabilities": [],
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
                "required_capabilities": [],
                "errors": [msg],
            },
        )


__all__ = ["chat_respond_node"]
