from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ExecutionMode(str, Enum):
    DIRECT_ANSWER = "direct_answer"
    TOOL_ASSISTED = "tool_assisted"
    DEEP_RESEARCH = "deep_research"


_PUBLIC_MODE_TO_EXECUTION: dict[str, ExecutionMode] = {
    "agent": ExecutionMode.TOOL_ASSISTED,
    "tool_assisted": ExecutionMode.TOOL_ASSISTED,
    "direct_answer": ExecutionMode.DIRECT_ANSWER,
    "deep": ExecutionMode.DEEP_RESEARCH,
    "deep_research": ExecutionMode.DEEP_RESEARCH,
}

_EXECUTION_TO_ROUTE: dict[ExecutionMode, str] = {
    ExecutionMode.DIRECT_ANSWER: "agent",
    ExecutionMode.TOOL_ASSISTED: "agent",
    ExecutionMode.DEEP_RESEARCH: "deep",
}


def execution_mode_from_public_mode(
    mode: str | None,
    *,
    default: ExecutionMode = ExecutionMode.TOOL_ASSISTED,
) -> ExecutionMode:
    normalized = str(mode or "").strip().lower()
    if not normalized:
        return default
    return _PUBLIC_MODE_TO_EXECUTION.get(normalized, default)


def route_name_for_mode(mode: ExecutionMode | str | None) -> str:
    normalized = execution_mode_from_public_mode(
        mode.value if isinstance(mode, ExecutionMode) else mode,
        default=ExecutionMode.TOOL_ASSISTED,
    )
    return _EXECUTION_TO_ROUTE[normalized]


def public_mode_for_execution(mode: ExecutionMode | str | None) -> str:
    return route_name_for_mode(mode)


@dataclass(frozen=True)
class AgentProfileConfig:
    id: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    prompt_pack: str = ""
    prompt_variant: str = "full"

    @classmethod
    def from_value(cls, value: Any) -> "AgentProfileConfig":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if not isinstance(value, Mapping):
            return cls()
        return cls(
            id=str(value.get("id") or "").strip(),
            system_prompt=str(value.get("system_prompt") or "").strip(),
            tools=[str(item).strip() for item in value.get("tools") or [] if str(item).strip()],
            blocked_tools=[
                str(item).strip() for item in value.get("blocked_tools") or [] if str(item).strip()
            ],
            metadata=dict(value.get("metadata") or {}),
            prompt_pack=str(value.get("prompt_pack") or "").strip(),
            prompt_variant=str(value.get("prompt_variant") or "full").strip() or "full",
        )


@dataclass(frozen=True)
class ExecutionRequest:
    input_text: str
    thread_id: str
    user_id: str
    mode: ExecutionMode = ExecutionMode.TOOL_ASSISTED
    images: list[dict[str, Any]] = field(default_factory=list)
    agent_profile: AgentProfileConfig = field(default_factory=AgentProfileConfig)
    resume_from_checkpoint: bool = False
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewDecision:
    verdict: str
    feedback: str = ""
    dimensions: dict[str, float] = field(default_factory=dict)
    missing_topics: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionResult:
    mode: ExecutionMode
    final_report: str = ""
    draft_report: str = ""
    is_complete: bool = False
    errors: list[str] = field(default_factory=list)
    messages: list[Any] = field(default_factory=list)
    review: ReviewDecision | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
