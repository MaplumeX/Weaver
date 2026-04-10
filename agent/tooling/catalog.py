from __future__ import annotations

from collections import Counter
from typing import Any

from agent.tooling.registry import ToolSpec


def _tool_parameters(tool: Any) -> dict[str, Any]:
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is None:
        return {}
    try:
        if hasattr(args_schema, "model_json_schema"):
            return dict(args_schema.model_json_schema())
        if hasattr(args_schema, "schema"):
            return dict(args_schema.schema())
    except Exception:
        return {}
    return {}


def _tool_payload(tool: Any, *, spec: ToolSpec | None = None) -> dict[str, Any] | None:
    name = str(getattr(tool, "name", "") or "").strip()
    if not name:
        return None

    description = str(getattr(tool, "description", "") or "").strip()
    module_name = str(getattr(tool, "__module__", "") or "").strip()
    class_name = str(getattr(tool.__class__, "__name__", "") or "").strip()
    tags = [str(tag).strip() for tag in (getattr(tool, "tags", None) or []) if str(tag).strip()]

    return {
        "tool_id": spec.tool_id if spec is not None else name,
        "name": name,
        "description": description,
        "tool_type": "langchain",
        "parameters": _tool_parameters(tool),
        "capabilities": list(spec.capabilities) if spec is not None else [],
        "source": spec.source if spec is not None else "",
        "risk_level": spec.risk_level if spec is not None else "standard",
        "return_type": None,
        "module_name": module_name,
        "class_name": class_name,
        "function_name": name,
        "version": "1.0.0",
        "tags": tags,
        "call_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "last_called": None,
        "average_duration_ms": 0.0,
        "enabled": True,
        "deprecated": False,
        "deprecation_message": None,
        "success_rate": 0.0,
    }


def build_tool_catalog_snapshot(
    *,
    tools: list[Any],
    source: str,
    registry: dict[str, ToolSpec] | None = None,
) -> dict[str, Any]:
    entries = [
        payload
        for payload in (
            _tool_payload(tool, spec=(registry or {}).get(str(getattr(tool, "name", "") or "").strip()))
            for tool in tools
        )
        if payload is not None
    ]
    entries.sort(key=lambda item: item["name"])

    by_type = Counter(entry["tool_type"] for entry in entries)
    tags = sorted(
        {
            tag
            for entry in entries
            for tag in [*entry["tags"], *entry.get("capabilities", [])]
        }
    )

    return {
        "source": str(source or "").strip(),
        "total_tools": len(entries),
        "by_type": dict(by_type),
        "tags": tags,
        "tools": entries,
    }
