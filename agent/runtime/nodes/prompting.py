from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.infrastructure.browser_context import build_browser_context_hint
from agent.runtime.config_utils import configurable_dict

_configurable = configurable_dict


def _profile_prompt(config: dict[str, Any] | Any) -> str:
    profile = _configurable(config).get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}
    return str(profile.get("system_prompt") or "").strip()


def _memory_block(state: dict[str, Any]) -> str:
    memory_context = state.get("memory_context") or {}
    if not isinstance(memory_context, dict):
        memory_context = {}

    stored = [str(item).strip() for item in (memory_context.get("stored") or []) if str(item).strip()]
    relevant = [
        str(item).strip() for item in (memory_context.get("relevant") or []) if str(item).strip()
    ]

    parts: list[str] = []
    if stored:
        parts.append("Stored memories:\n" + "\n".join(f"- {item}" for item in stored))
    if relevant:
        parts.append("Relevant past knowledge:\n" + "\n".join(f"- {item}" for item in relevant))

    return "\n\n".join(parts).strip()


def _short_term_block(state: dict[str, Any]) -> str:
    short_term_context = state.get("short_term_context") or {}
    if not isinstance(short_term_context, dict):
        short_term_context = {}

    rolling_summary = str(short_term_context.get("rolling_summary") or "").strip()
    pinned_items = [
        str(item).strip()
        for item in (short_term_context.get("pinned_items") or [])
        if str(item).strip()
    ]
    open_questions = [
        str(item).strip()
        for item in (short_term_context.get("open_questions") or [])
        if str(item).strip()
    ]
    recent_tools = [
        str(item).strip()
        for item in (short_term_context.get("recent_tools") or [])
        if str(item).strip()
    ]
    recent_sources = [
        str(item).strip()
        for item in (short_term_context.get("recent_sources") or [])
        if str(item).strip()
    ]

    parts: list[str] = []
    if rolling_summary:
        parts.append("Conversation summary:\n" + rolling_summary)
    if pinned_items:
        parts.append("Pinned constraints:\n" + "\n".join(f"- {item}" for item in pinned_items))
    if open_questions:
        parts.append("Open questions:\n" + "\n".join(f"- {item}" for item in open_questions))
    if recent_tools:
        parts.append("Recent tools:\n" + "\n".join(f"- {item}" for item in recent_tools))
    if recent_sources:
        parts.append("Recent sources:\n" + "\n".join(f"- {item}" for item in recent_sources))

    return "\n\n".join(parts).strip()


def build_chat_runtime_messages(
    state: dict[str, Any],
    config: dict[str, Any] | Any,
    *,
    include_browser_hint: bool = False,
) -> list[Any]:
    system_parts = [
        part
        for part in (_profile_prompt(config), _short_term_block(state), _memory_block(state))
        if part
    ]

    if include_browser_hint:
        thread_id = str(_configurable(config).get("thread_id") or "default")
        browser_hint = build_browser_context_hint(thread_id)
        if browser_hint:
            system_parts.append(browser_hint)

    messages: list[Any] = []
    if system_parts:
        messages.append(SystemMessage(content="\n\n".join(system_parts)))

    state_messages = list(state.get("messages") or [])
    messages.extend(state_messages)

    current_input = str(state.get("input") or "")
    last_message = state_messages[-1] if state_messages else None
    last_type = str(getattr(last_message, "type", "") or "").strip().lower()
    last_content = getattr(last_message, "content", "")
    if current_input and not (last_type == "human" and str(last_content) == current_input):
        messages.append(HumanMessage(content=current_input))
    return messages


__all__ = ["build_chat_runtime_messages"]
