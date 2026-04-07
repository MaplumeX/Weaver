from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from agent.prompts.agent_prompts import get_default_agent_prompt
from agent.prompts.runtime_templates import RUNTIME_PROMPT_TEMPLATES
from agent.prompts.system_prompts import (
    get_agent_prompt as get_enhanced_agent_prompt,
)
from agent.prompts.system_prompts import (
    get_deep_research_prompt as get_enhanced_deep_research_prompt,
)
from agent.prompts.system_prompts import (
    get_writer_prompt as get_enhanced_writer_prompt,
)

PromptRenderer = Callable[[dict[str, Any]], str]


def _static_renderer(content: str) -> PromptRenderer:
    def _render(_context: dict[str, Any]) -> str:
        return content

    return _render


def _simple_writer_prompt() -> str:
    return (
        "You are an expert research analyst. Write a concise, well-structured report "
        "with markdown headings, inline source tags like [S1-1], and a Sources section at the end."
    )


def _simple_planner_prompt() -> str:
    return "You are a research planner. Generate 3-7 targeted search queries and reasoning."


@dataclass(frozen=True)
class PromptDefinition:
    prompt_id: str
    renderer: PromptRenderer


class PromptRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, PromptDefinition] = {}
        self._overrides: dict[str, str] = {}

    def register(self, prompt_id: str, renderer: PromptRenderer) -> None:
        key = str(prompt_id or "").strip()
        if not key:
            raise ValueError("prompt_id is required")
        self._definitions[key] = PromptDefinition(prompt_id=key, renderer=renderer)

    def set_override(self, prompt_id: str, content: str) -> None:
        self._overrides[str(prompt_id or "").strip()] = str(content or "")

    def render(self, prompt_id: str, context: Mapping[str, Any] | None = None) -> str:
        key = str(prompt_id or "").strip()
        if key in self._overrides:
            return self._overrides[key]
        definition = self._definitions.get(key)
        if definition is None:
            raise KeyError(f"Unknown prompt id: {key}")
        return definition.renderer(dict(context or {}))

    def ids(self) -> list[str]:
        return sorted(self._definitions)


def build_default_prompt_registry(prompt_style: str = "enhanced") -> PromptRegistry:
    registry = PromptRegistry()
    normalized_style = str(prompt_style or "enhanced").strip().lower()

    if normalized_style == "simple":
        registry.register("agent", lambda _context: get_default_agent_prompt())
        registry.register("writer", lambda _context: _simple_writer_prompt())
        registry.register("planner", lambda _context: _simple_planner_prompt())
        registry.register("deep_research", lambda _context: get_default_agent_prompt())
    else:
        registry.register(
            "agent",
            lambda context: get_enhanced_agent_prompt(mode="agent", context=context or None),
        )
        registry.register("writer", lambda _context: get_enhanced_writer_prompt())
        registry.register("planner", lambda _context: RUNTIME_PROMPT_TEMPLATES["planning.plan"])
        registry.register("deep_research", lambda _context: get_enhanced_deep_research_prompt())

    registry.register(
        "direct_answer",
        lambda _context: "You are a helpful assistant. Answer succinctly and accurately.",
    )

    for prompt_id, template in RUNTIME_PROMPT_TEMPLATES.items():
        registry.register(prompt_id, _static_renderer(template))

    return registry

