"""Runtime-owned config, model, and tool-context helpers for Deep Research."""

from __future__ import annotations

from typing import Any

from agent.execution.config_utils import configurable_float, configurable_int, configurable_value
from agent.foundation.multi_model import resolve_model_name
from agent.tooling import build_tool_context
from agent.tooling.agents.factory import resolve_deep_research_role_tool_policy
from common.config import settings

_configurable_value = configurable_value
_configurable_int = configurable_int
_configurable_float = configurable_float
_model_for_task = resolve_model_name


def _tool_runtime_context_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    try:
        runtime = build_tool_context(config).runtime
    except Exception:
        return {}
    return {
        "thread_id": runtime.thread_id,
        "user_id": runtime.user_id,
        "session_id": runtime.session_id,
        "agent_id": runtime.agent_id,
        "run_id": runtime.run_id,
        "roles": list(runtime.roles),
        "capabilities": list(runtime.capabilities),
        "blocked_capabilities": list(runtime.blocked_capabilities),
        "e2b_ready": bool(runtime.e2b_ready),
    }


def _deep_research_role_tool_policy_snapshot(
    role: str,
    *,
    allowed_tools: list[str] | None = None,
) -> dict[str, Any]:
    policy = resolve_deep_research_role_tool_policy(
        role,
        allowed_tools=allowed_tools,
        enable_supervisor_world_tools=bool(
            getattr(settings, "deep_research_supervisor_allow_world_tools", False)
        ),
        enable_reporter_python_tools=bool(
            getattr(settings, "deep_research_reporter_enable_python_tools", True)
        ),
    )
    return {
        "role": policy.role,
        "requested_tools": list(policy.requested_tools),
        "allowed_tool_names": list(policy.allowed_tool_names),
    }


__all__ = [
    "_configurable_float",
    "_configurable_int",
    "_configurable_value",
    "_deep_research_role_tool_policy_snapshot",
    "_model_for_task",
    "_tool_runtime_context_snapshot",
]
