"""
Finalize answer-generation nodes.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

import agent.execution.shared as _shared

_apply_output_contract = _shared._apply_output_contract
project_state_updates = _shared.project_state_updates


def finalize_answer_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    report = _apply_output_contract(state.get("input", ""), state.get("assistant_draft", ""))
    return project_state_updates(
        state,
        {
            "assistant_draft": report,
            "final_report": report,
            "draft_report": report,
            "messages": [AIMessage(content=report)],
            "is_complete": True,
        },
    )


__all__ = ["finalize_answer_node"]
