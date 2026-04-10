from __future__ import annotations

from typing import Any


def configurable_dict(config: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
        if isinstance(configurable, dict):
            return configurable
    return {}


def configurable_value(config: dict[str, Any] | Any, key: str) -> Any:
    return configurable_dict(config).get(key)


def configurable_int(config: dict[str, Any] | Any, key: str, default: int) -> int:
    value = configurable_value(config, key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def configurable_float(config: dict[str, Any] | Any, key: str, default: float) -> float:
    value = configurable_value(config, key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
