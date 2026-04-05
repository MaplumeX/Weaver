"""
Review graph nodes.
"""

from __future__ import annotations

import sys
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

import agent.runtime.nodes._shared as _shared

_apply_output_contract = _shared._apply_output_contract
project_state_updates = _shared.project_state_updates
logger = _shared.logger
settings = _shared.settings


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


def _hitl_checkpoints_enabled() -> set[str]:
    raw = (getattr(settings, "hitl_checkpoints", "") or "").strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def human_review_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """Optional human review step using LangGraph interrupt."""
    deps = _resolve_deps(_deps)
    logger.info("Executing human review node")
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    allow_interrupts = bool(configurable.get("allow_interrupts"))
    force_final_checkpoint = "final" in _hitl_checkpoints_enabled()
    require_review = bool(configurable.get("human_review")) or force_final_checkpoint

    report = state.get("final_report") or state.get("draft_report", "")

    if not (allow_interrupts and require_review):
        report = deps._apply_output_contract(state.get("input", ""), report)
        return deps.project_state_updates(
            state,
            {
                "final_report": report,
                "is_complete": True,
                "messages": [AIMessage(content=report)],
            },
        )

    updated = interrupt(
        {
            "checkpoint": "final",
            "instruction": "Review and edit the report if needed. Return the updated content or approve as-is.",
            "content": report,
        }
    )

    if isinstance(updated, dict):
        if updated.get("content"):
            report = updated["content"]
    elif isinstance(updated, str) and updated.strip():
        report = updated

    report = deps._apply_output_contract(state.get("input", ""), report)

    return deps.project_state_updates(
        state,
        {"final_report": report, "is_complete": True, "messages": [AIMessage(content=report)]},
    )


__all__ = ["human_review_node"]
