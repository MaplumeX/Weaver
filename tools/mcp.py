from __future__ import annotations

import json
import logging
from typing import Any

from langchain.tools import BaseTool

from common.config import settings
from tools.core.mcp import (
    close_mcp_tools as _core_close_mcp_tools,
)
from tools.core.mcp import (
    get_live_mcp_tools as _core_get_live_mcp_tools,
)
from tools.core.mcp import (
    init_mcp_tools as _core_init_mcp_tools,
)
from tools.core.mcp import (
    reload_mcp_tools as _core_reload_mcp_tools,
)

logger = logging.getLogger(__name__)


def _parse_servers(servers: Any) -> dict[str, Any]:
    if isinstance(servers, str):
        try:
            return json.loads(servers)
        except json.JSONDecodeError:
            logger.error("MCP_SERVERS is not valid JSON; MCP tools disabled")
            return {}
    return servers or {}


def _sanitize_servers(servers: dict[str, Any]) -> dict[str, Any]:
    return {
        server_id: cfg
        for server_id, cfg in (servers or {}).items()
        if isinstance(server_id, str) and not server_id.startswith("__")
    }


async def init_mcp_tools(
    servers_override: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> list[BaseTool]:
    """
    Initialize MCP tools via the official LangChain MCP adapter path.

    `main.py` may inject private fields such as `__thread_id__`; strip those
    before handing the config to `MultiServerMCPClient`.
    """
    servers_cfg = servers_override if servers_override is not None else settings.mcp_servers
    parsed_servers = _parse_servers(servers_cfg)
    servers = _sanitize_servers(parsed_servers)
    use_mcp = enabled if enabled is not None else settings.enable_mcp

    if not use_mcp or not servers:
        logger.info("MCP disabled or no servers configured.")
        await _core_close_mcp_tools()
        return []

    return await _core_init_mcp_tools(servers_override=servers, enabled=use_mcp)


def get_live_mcp_tools() -> list[BaseTool]:
    return list(_core_get_live_mcp_tools())


async def reload_mcp_tools(
    servers_config: dict[str, Any], enabled: bool | None = None
) -> list[BaseTool]:
    servers = _sanitize_servers(_parse_servers(servers_config))
    return await _core_reload_mcp_tools(servers_config=servers, enabled=enabled)


async def close_mcp_tools() -> None:
    await _core_close_mcp_tools()


__all__ = [
    "close_mcp_tools",
    "get_live_mcp_tools",
    "init_mcp_tools",
    "reload_mcp_tools",
]
