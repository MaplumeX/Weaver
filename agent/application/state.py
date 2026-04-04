from __future__ import annotations

from typing import Any, Iterable

from langchain_core.messages import SystemMessage

from agent.domain import (
    AgentProfileConfig,
    ExecutionRequest,
    build_deep_runtime_snapshot,
    build_state_slices,
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
) -> dict[str, Any]:
    route = route_name_for_mode(request.mode)
    deep_runtime_engine = (
        SUPPORTED_DEEP_RESEARCH_RUNTIME if route == "deep" else ""
    )
    initial_state: dict[str, Any] = {
        "input": request.input_text,
        "images": list(request.images),
        "final_report": "",
        "draft_report": "",
        "user_id": request.user_id,
        "thread_id": request.thread_id,
        "agent_id": request.agent_profile.id,
        "messages": [],
        "research_plan": [],
        "current_step": 0,
        "status": "pending",
        "is_complete": False,
        "route": route,
        "routing_reasoning": "",
        "routing_confidence": 0.0,
        "suggested_queries": [],
        "needs_clarification": False,
        "clarification_question": "",
        "scraped_content": [],
        "code_results": [],
        "summary_notes": [],
        "sources": [],
        "evaluation": "",
        "verdict": "",
        "eval_dimensions": {},
        "missing_topics": [],
        "revision_count": 0,
        "max_revisions": int(request.options.get("max_revisions") or settings.max_revisions),
        "tool_approved": False,
        "pending_tool_calls": [],
        "tool_call_count": 0,
        "tool_call_limit": int(request.options.get("tool_call_limit") or settings.tool_call_limit),
        "enabled_tools": dict(request.agent_profile.enabled_tools),
        "cancel_token_id": request.thread_id,
        "is_cancelled": False,
        "errors": [],
        "last_error": "",
        "research_topology": {},
        "compressed_knowledge": {},
        "domain": "",
        "domain_config": {},
        "sub_agent_contexts": {},
        "deep_runtime": build_deep_runtime_snapshot(
            engine=deep_runtime_engine,
        ),
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    messages: list[Any] = []
    if route == "agent" and request.agent_profile.system_prompt:
        messages.append(SystemMessage(content=request.agent_profile.system_prompt))
    if route == "deep":
        messages.append(SystemMessage(content=get_deep_agent_prompt()))

    store_items = [str(item).strip() for item in (stored_memories or []) if str(item).strip()]
    if store_items:
        store_text = "\n".join(f"- {item}" for item in store_items)
        messages.append(SystemMessage(content=f"Stored memories:\n{store_text}"))

    memory_items = [str(item).strip() for item in (relevant_memories or []) if str(item).strip()]
    if memory_items:
        memory_text = "\n".join(f"- {item}" for item in memory_items)
        messages.append(SystemMessage(content=f"Relevant past knowledge:\n{memory_text}"))

    if messages:
        initial_state["messages"] = messages

    initial_state.update(build_state_slices(initial_state))
    return initial_state

