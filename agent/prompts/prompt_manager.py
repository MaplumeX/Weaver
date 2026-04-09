"""Central prompt manager and registry facade."""

import logging
from typing import Any

from agent.infrastructure.prompts import PromptRegistry, build_default_prompt_registry
from common.config import settings

logger = logging.getLogger(__name__)


class PromptManager:
    """Centralized prompt management for Weaver agents."""

    def __init__(self, prompt_style: str = "enhanced", registry: PromptRegistry | None = None):
        self.prompt_style = prompt_style
        self._registry = registry or build_default_prompt_registry(prompt_style)

    @property
    def registry(self) -> PromptRegistry:
        return self._registry

    def render(self, prompt_id: str, context: dict[str, Any] | None = None) -> str:
        return self._registry.render(str(prompt_id or "").strip(), context=context)


# ============================================================================
# Global PromptManager Instance
# ============================================================================

# Default instance (can be overridden)
_default_prompt_manager: PromptManager | None = None


def _get_prompt_manager() -> PromptManager:
    """Return the shared prompt manager used by module-level helpers."""
    global _default_prompt_manager

    if _default_prompt_manager is None:
        style = getattr(settings, "prompt_style", "enhanced")
        _default_prompt_manager = PromptManager(prompt_style=style)
        logger.info(f"Initialized PromptManager with style: {style}")

    return _default_prompt_manager


def render_prompt(prompt_id: str, context: dict[str, Any] | None = None) -> str:
    return _get_prompt_manager().render(prompt_id, context=context)
