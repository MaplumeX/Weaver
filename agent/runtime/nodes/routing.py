"""
Routing-related graph nodes.
"""

from __future__ import annotations

import sys
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

import agent.runtime.nodes._shared as _shared
from agent.prompts import render_prompt

_build_user_content = _shared._build_user_content
_chat_model = _shared._chat_model
_configurable = _shared._configurable
_log_usage = _shared._log_usage
_model_for_task = _shared._model_for_task
project_state_updates = _shared.project_state_updates
logger = _shared.logger
settings = _shared.settings


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


def route_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Route execution using SmartRouter (LLM-based intelligent routing).

    Priority:
    1. Config override (search_mode.mode) - for explicit user control
    2. SmartRouter LLM decision - intelligent query classification
    3. Low confidence fallback - route to clarify if confidence < threshold

    Returns state updates with routing decision and metadata.
    """
    from agent.core.smart_router import smart_route

    deps = _resolve_deps(_deps)
    configurable = deps._configurable(config)
    mode_info = configurable.get("search_mode", {}) or {}
    override_mode = mode_info.get("mode")
    max_revisions = configurable.get("max_revisions", state.get("max_revisions", 0))
    confidence_threshold = float(configurable.get("routing_confidence_threshold", 0.6))

    result = smart_route(
        query=state.get("input", ""),
        images=state.get("images"),
        config=config,
        override_mode=override_mode if override_mode else None,
    )

    route = result.get("route", "agent")
    confidence = result.get("routing_confidence", 1.0)

    if not override_mode and confidence < confidence_threshold:
        logger.info(
            f"Low confidence ({confidence:.2f} < {confidence_threshold}), routing to clarify"
        )
        route = "clarify"
        result["route"] = "clarify"
        result["needs_clarification"] = True

    logger.info(f"[route_node] Routing decision: {route} (confidence: {confidence:.2f})")
    logger.info(f"[route_node] search_mode from config: {mode_info}")
    logger.info(f"[route_node] override_mode: {override_mode}")
    logger.info(f"[route_node] Returning result with route='{route}'")

    result["max_revisions"] = max_revisions

    if getattr(settings, "domain_routing_enabled", False) and route == "deep":
        try:
            from agent.research.domain_router import DomainClassifier

            domain_llm = deps._chat_model(deps._model_for_task("routing", config), temperature=0.3)
            classifier = DomainClassifier(domain_llm, config)

            classification = classifier.classify(state.get("input", ""))

            result["domain"] = classification.domain.value
            result["domain_config"] = classification.to_dict()

            logger.info(
                f"[route_node] Domain classified: {classification.domain.value} "
                f"(confidence: {classification.confidence:.2f})"
            )

        except Exception as e:
            logger.warning(f"[route_node] Domain classification failed: {e}")
            result["domain"] = "general"
            result["domain_config"] = {}

    return deps.project_state_updates(state, result)


def clarify_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Light-weight guardrail to decide if the query needs clarification before planning.
    Uses structured output with retry for robustness.
    """
    deps = _resolve_deps(_deps)
    logger.info("Executing clarify node")
    llm = deps._chat_model(deps._model_for_task("routing", config), temperature=0.3)

    class ClarifyResponse(BaseModel):
        need_clarification: bool = Field(
            description="Whether the user request is ambiguous or incomplete."
        )
        question: str = Field(default="", description="A concise clarifying question.")
        verification: str = Field(
            default="", description="A brief confirmation to proceed when clear."
        )

    system_msg = SystemMessage(
        content=render_prompt("routing.clarify")
    )
    human_msg = HumanMessage(
        content=deps._build_user_content(state.get("input", ""), state.get("images"))
    )

    try:
        response = (
            llm.with_structured_output(ClarifyResponse)
            .with_retry(stop_after_attempt=2)
            .invoke([system_msg, human_msg], config=config)
        )
        deps._log_usage(response, "clarify")
    except Exception as e:
        logger.warning(f"Clarify step failed, proceeding without clarification: {e}")
        return deps.project_state_updates(state, {"needs_clarification": False})

    needs_clarification = bool(getattr(response, "need_clarification", False))
    question = getattr(response, "question", "") or "Could you clarify your request?"
    verification = getattr(response, "verification", "") or "Understood. Proceeding."

    if needs_clarification:
        logger.info("Clarification required; returning question to user.")
        return deps.project_state_updates(
            state,
            {
                "needs_clarification": True,
                "clarification_question": question,
                "final_report": question,
                "messages": [AIMessage(content=question)],
                "is_complete": True,
            },
        )

    logger.info("No clarification needed; proceeding to planning.")
    return deps.project_state_updates(
        state,
        {"needs_clarification": False, "messages": [AIMessage(content=verification)]},
    )


__all__ = ["clarify_node", "route_node"]
