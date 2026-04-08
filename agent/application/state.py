from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.core.state import prepare_seed_messages
from agent.domain import (
    AgentProfileConfig,
    ExecutionRequest,
    build_deep_runtime_snapshot,
    execution_mode_from_public_mode,
    route_name_for_mode,
)
from agent.prompts import get_deep_agent_prompt
from agent.runtime.deep.config import SUPPORTED_DEEP_RESEARCH_RUNTIME
from common.config import settings


def build_execution_request(
    *,
    input_text: str,
    thread_id: str,
    user_id: str,
    mode_info: dict[str, Any] | None,
    images: list[dict[str, Any]] | None = None,
    agent_profile: Any = None,
    resume_from_checkpoint: bool = False,
    options: dict[str, Any] | None = None,
) -> ExecutionRequest:
    mode = execution_mode_from_public_mode((mode_info or {}).get("mode"))
    return ExecutionRequest(
        input_text=str(input_text or ""),
        thread_id=str(thread_id or ""),
        user_id=str(user_id or settings.memory_user_id),
        mode=mode,
        images=list(images or []),
        agent_profile=AgentProfileConfig.from_value(agent_profile),
        resume_from_checkpoint=resume_from_checkpoint,
        options=dict(options or {}),
    )


def build_initial_agent_state(
    request: ExecutionRequest,
    *,
    stored_memories: Iterable[str] | None = None,
    relevant_memories: Iterable[str] | None = None,
    history_messages: Iterable[BaseMessage] | None = None,
) -> dict[str, Any]:
    route = route_name_for_mode(request.mode)
    deep_runtime_engine = SUPPORTED_DEEP_RESEARCH_RUNTIME if route == "deep" else ""
    store_items = [str(item).strip() for item in (stored_memories or []) if str(item).strip()]
    memory_items = [str(item).strip() for item in (relevant_memories or []) if str(item).strip()]
    initial_state: dict[str, Any] = {
        "input": request.input_text,
        "images": list(request.images),
        "final_report": "",
        "draft_report": "",
        "assistant_draft": "",
        "user_id": request.user_id,
        "thread_id": request.thread_id,
        "agent_id": request.agent_profile.id,
        "messages": [],
        "status": "pending",
        "is_complete": False,
        "route": route,
        "needs_tools": False,
        "scraped_content": [],
        "summary_notes": [],
        "sources": [],
        "memory_context": {
            "stored": store_items,
            "relevant": memory_items,
        },
        "roles": list(request.agent_profile.roles),
        "available_capabilities": list(request.agent_profile.capabilities),
        "blocked_capabilities": list(request.agent_profile.blocked_capabilities),
        "available_tools": list(request.agent_profile.tools),
        "blocked_tools": list(request.agent_profile.blocked_tools),
        "selected_tools": [],
        "cancel_token_id": request.thread_id,
        "is_cancelled": False,
        "errors": [],
        "research_topology": {},
        "domain": "",
        "domain_config": {},
        "sub_agent_contexts": {},
        "deep_runtime": build_deep_runtime_snapshot(
            engine=deep_runtime_engine,
        ),
    }

    messages: list[BaseMessage] = [
        message
        for message in (history_messages or [])
        if isinstance(message, BaseMessage)
    ]
    if route == "agent" and request.input_text.strip():
        messages.append(HumanMessage(content=request.input_text))
    if route == "deep":
        messages = [SystemMessage(content=get_deep_agent_prompt())]

    if messages:
        initial_state["messages"] = prepare_seed_messages(messages)
    return initial_state
