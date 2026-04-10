from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool

from agent.tooling.registry import ToolSpec

_ROLE_CAPABILITY_MAP: dict[str, tuple[str, ...]] = {
    "default_agent": ("search", "browser", "planning"),
    "researcher": ("search", "browser"),
    "reporter": ("python", "planning"),
    "supervisor": ("planning",),
}


def _normalize_names(values: Iterable[str] | None) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values or ():
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def filter_tools_by_name(
    tools: list[BaseTool],
    *,
    allowed: Iterable[str] | None = None,
    blocked: Iterable[str] | None = None,
) -> list[BaseTool]:
    allowed_names = set(_normalize_names(allowed))
    blocked_names = set(_normalize_names(blocked))
    filtered = tools
    if allowed_names:
        filtered = [tool for tool in filtered if getattr(tool, "name", "") in allowed_names]
    if blocked_names:
        filtered = [tool for tool in filtered if getattr(tool, "name", "") not in blocked_names]
    return filtered


def capabilities_for_roles(roles: Iterable[str] | None) -> tuple[str, ...]:
    capabilities: list[str] = []
    for role in _normalize_names(roles):
        capabilities.extend(_ROLE_CAPABILITY_MAP.get(role, ()))
    return _normalize_names(capabilities)


def expand_capabilities_to_tool_names(
    registry: Mapping[str, ToolSpec],
    capabilities: Iterable[str] | None,
) -> tuple[str, ...]:
    wanted = set(_normalize_names(capabilities))
    if not wanted:
        return ()
    matched = [
        tool_name
        for tool_name, spec in registry.items()
        if wanted.intersection(spec.capabilities)
    ]
    return _normalize_names(matched)


@dataclass(frozen=True)
class ToolPolicyResolution:
    allowed_tool_names: tuple[str, ...]
    blocked_tool_names: tuple[str, ...]
    granted_capabilities: tuple[str, ...]


def resolve_profile_tool_policy(
    registry: Mapping[str, ToolSpec],
    *,
    profile: Mapping[str, Any] | None,
) -> ToolPolicyResolution:
    profile = profile or {}
    explicit_allowed = _normalize_names(profile.get("tools"))
    explicit_blocked = _normalize_names(profile.get("blocked_tools"))
    direct_capabilities = _normalize_names(profile.get("capabilities"))
    blocked_capabilities = _normalize_names(profile.get("blocked_capabilities"))
    role_capabilities = capabilities_for_roles(profile.get("roles"))

    granted_capabilities = _normalize_names((*role_capabilities, *direct_capabilities))
    capability_allowed = expand_capabilities_to_tool_names(registry, granted_capabilities)
    capability_blocked = expand_capabilities_to_tool_names(registry, blocked_capabilities)

    allowed_tool_names = explicit_allowed or capability_allowed
    blocked_tool_names = _normalize_names((*explicit_blocked, *capability_blocked))

    return ToolPolicyResolution(
        allowed_tool_names=allowed_tool_names,
        blocked_tool_names=blocked_tool_names,
        granted_capabilities=granted_capabilities,
    )


__all__ = [
    "ToolPolicyResolution",
    "capabilities_for_roles",
    "expand_capabilities_to_tool_names",
    "filter_tools_by_name",
    "resolve_profile_tool_policy",
]
