from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig


def _configurable(config: RunnableConfig) -> dict[str, Any]:
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        if isinstance(cfg, dict):
            return cfg
    return {}


def _string_list(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set)):
        return ()
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return tuple(items)


@dataclass(frozen=True)
class ToolRuntimeContext:
    thread_id: str
    user_id: str
    session_id: str
    agent_id: str
    run_id: str
    roles: tuple[str, ...]
    capabilities: tuple[str, ...]
    blocked_capabilities: tuple[str, ...]
    configurable: dict[str, Any]
    profile: dict[str, Any]
    e2b_ready: bool


def build_tool_runtime_context(
    config: RunnableConfig,
    *,
    e2b_ready: bool,
) -> ToolRuntimeContext:
    configurable = _configurable(config)
    profile = configurable.get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    thread_id = str(configurable.get("thread_id") or "default")
    user_id = str(
        configurable.get("user_id")
        or configurable.get("principal_user_id")
        or configurable.get("memory_user_id")
        or "default_user"
    )
    session_id = str(configurable.get("session_id") or thread_id)
    run_id = str(configurable.get("run_id") or configurable.get("request_id") or "")
    agent_id = str(profile.get("id") or configurable.get("agent_id") or "")

    return ToolRuntimeContext(
        thread_id=thread_id,
        user_id=user_id,
        session_id=session_id,
        agent_id=agent_id,
        run_id=run_id,
        roles=_string_list(profile.get("roles")),
        capabilities=_string_list(profile.get("capabilities")),
        blocked_capabilities=_string_list(profile.get("blocked_capabilities")),
        configurable=dict(configurable),
        profile=dict(profile),
        e2b_ready=bool(e2b_ready),
    )


__all__ = ["ToolRuntimeContext", "build_tool_runtime_context"]
