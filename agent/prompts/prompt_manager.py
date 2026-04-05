"""Central prompt manager and registry facade."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agent.infrastructure.prompts import PromptRegistry, build_default_prompt_registry
from common.config import settings

logger = logging.getLogger(__name__)


class PromptManager:
    """Centralized prompt management for Weaver agents."""

    def __init__(self, prompt_style: str = "enhanced", registry: PromptRegistry | None = None):
        self.prompt_style = prompt_style
        self._registry = registry or build_default_prompt_registry(prompt_style)
        self._custom_prompts: Dict[str, str] = {}

    def set_custom_prompt(self, prompt_type: str, content: str):
        prompt_id = str(prompt_type or "").strip()
        self._custom_prompts[prompt_id] = content
        self._registry.set_override(prompt_id, content)
        logger.info(f"Custom {prompt_type} prompt set ({len(content)} chars)")

    def load_custom_prompt(self, prompt_type: str, file_path: str):
        """
        Load a custom prompt from a file.

        Args:
            prompt_type: "agent", "writer", "planner", etc.
            file_path: Path to prompt file
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        content = path.read_text(encoding="utf-8")
        self.set_custom_prompt(prompt_type, content)
        logger.info(f"Loaded custom {prompt_type} prompt from {file_path}")

    @property
    def registry(self) -> PromptRegistry:
        return self._registry

    def render(self, prompt_id: str, context: Optional[Dict[str, Any]] = None) -> str:
        prompt_key = str(prompt_id or "").strip()
        if prompt_key in self._custom_prompts:
            return self._custom_prompts[prompt_key]
        return self._registry.render(prompt_key, context=context)

    def get_agent_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        return self.render("agent", context=context)

    def get_writer_prompt(self) -> str:
        return self.render("writer")

    def get_planner_prompt(self) -> str:
        return self.render("planner")

    def get_deep_research_prompt(self) -> str:
        return self.render("deep_research")

    def get_direct_answer_prompt(self) -> str:
        return self.render("direct_answer")


# ============================================================================
# Global PromptManager Instance
# ============================================================================

# Default instance (can be overridden)
_default_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """
    Get the global PromptManager instance.

    Returns:
        PromptManager instance
    """
    global _default_prompt_manager

    if _default_prompt_manager is None:
        style = getattr(settings, "prompt_style", "enhanced")
        _default_prompt_manager = PromptManager(prompt_style=style)
        logger.info(f"Initialized PromptManager with style: {style}")

    return _default_prompt_manager


def set_prompt_manager(manager: PromptManager):
    """
    Set the global PromptManager instance.

    Args:
        manager: PromptManager instance to use
    """
    global _default_prompt_manager
    _default_prompt_manager = manager
    logger.info(f"Set global PromptManager to: {manager.prompt_style}")


def reset_prompt_manager():
    """Reset the global PromptManager instance."""
    global _default_prompt_manager
    _default_prompt_manager = None
    logger.info("Reset global PromptManager")


# ============================================================================
# Prompt accessors
# ============================================================================


def get_prompt_registry() -> PromptRegistry:
    return get_prompt_manager().registry


def render_prompt(prompt_id: str, context: Optional[Dict[str, Any]] = None) -> str:
    return get_prompt_manager().render(prompt_id, context=context)
