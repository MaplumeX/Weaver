"""
Routing-related graph nodes.
"""

from __future__ import annotations

import sys
from typing import Any

from langchain_core.runnables import RunnableConfig

import agent.runtime.nodes._shared as _shared

_configurable = _shared._configurable
_chat_model = _shared._chat_model
_model_for_task = _shared._model_for_task
project_state_updates = _shared.project_state_updates
logger = _shared.logger
settings = _shared.settings


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


def route_node(
    state: dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> dict[str, Any]:
    """
    Route execution using SmartRouter (LLM-based intelligent routing).

    Priority:
    1. Config override (search_mode.mode) - for explicit user control
    2. SmartRouter LLM decision - intelligent query classification
    3. Low confidence fallback - route to agent if confidence < threshold

    Returns state updates with routing decision and metadata.
    """
    from agent.core.smart_router import smart_route

    deps = _resolve_deps(_deps)
    configurable = deps._configurable(config)
    mode_info = configurable.get("search_mode", {}) or {}
    override_mode = mode_info.get("mode")
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
            f"Low confidence ({confidence:.2f} < {confidence_threshold}), routing to agent"
        )
        route = "agent"

    if route not in {"agent", "deep"}:
        route = "agent"

    logger.info(f"[route_node] Routing decision: {route} (confidence: {confidence:.2f})")
    logger.info(f"[route_node] search_mode from config: {mode_info}")
    logger.info(f"[route_node] override_mode: {override_mode}")
    logger.info(f"[route_node] Returning result with route='{route}'")
    updates: dict[str, Any] = {"route": route}

    if getattr(settings, "domain_routing_enabled", False) and route == "deep":
        try:
            from agent.research.domain_router import DomainClassifier

            domain_llm = deps._chat_model(deps._model_for_task("routing", config), temperature=0.3)
            classifier = DomainClassifier(domain_llm, config)

            classification = classifier.classify(state.get("input", ""))

            updates["domain"] = classification.domain.value
            updates["domain_config"] = classification.to_dict()

            logger.info(
                f"[route_node] Domain classified: {classification.domain.value} "
                f"(confidence: {classification.confidence:.2f})"
            )

        except Exception as e:
            logger.warning(f"[route_node] Domain classification failed: {e}")
            updates["domain"] = "general"
            updates["domain_config"] = {}

    return deps.project_state_updates(state, updates)


__all__ = ["route_node"]
