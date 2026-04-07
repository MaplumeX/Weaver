import json
import logging
from typing import Any

from langchain.tools import BaseTool

from common.config import settings
from tools.core.mcp_clients import MCPClients

logger = logging.getLogger(__name__)

_CLIENTS: MCPClients | None = None
_LIVE_MCP_TOOLS: list[BaseTool] = []


def _parse_servers(servers: Any) -> dict[str, Any]:
    if isinstance(servers, str):
        try:
            return json.loads(servers)
        except json.JSONDecodeError:
            logger.error("MCP_SERVERS is not valid JSON; MCP tools disabled")
            return {}
    return servers or {}


async def init_mcp_tools(
    servers_override: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> list[BaseTool]:
    """
    Initialize MCP tools with evented proxy tools.
    """
    global _CLIENTS
    servers_cfg = servers_override if servers_override is not None else settings.mcp_servers
    servers: dict[str, Any] = _parse_servers(servers_cfg)
    use_mcp = enabled if enabled is not None else settings.enable_mcp

    if not use_mcp or not servers:
        logger.info("MCP disabled or no servers configured.")
        _CLIENTS = None
        _LIVE_MCP_TOOLS.clear()
        return []

    thread_id = servers.get("__thread_id__", "default")
    clients = MCPClients(thread_id=thread_id)
    server_items = [
        (server_id, cfg)
        for server_id, cfg in servers.items()
        if isinstance(server_id, str) and not server_id.startswith("__")
    ]
    for server_id, cfg in server_items:
        try:
            if not isinstance(cfg, dict):
                logger.warning(f"Invalid MCP server config for {server_id}; expected object.")
                continue
            if cfg.get("type") == "sse":
                await clients.connect_sse(cfg.get("url"), server_id)
            elif cfg.get("type") == "stdio":
                await clients.connect_stdio(cfg.get("command"), cfg.get("args", []), server_id)
            else:
                logger.warning(f"Unknown MCP server type for {server_id}")
        except Exception as e:
            logger.error(f"MCP connect failed for {server_id}: {e}")

    _CLIENTS = clients
    _LIVE_MCP_TOOLS[:] = list(clients.tools)
    logger.info(f"Loaded {len(clients.tools)} MCP tools from {len(server_items)} servers")
    return list(_LIVE_MCP_TOOLS)


def get_live_mcp_tools() -> list[BaseTool]:
    return list(_LIVE_MCP_TOOLS)


async def reload_mcp_tools(
    servers_config: dict[str, Any], enabled: bool | None = None
) -> list[BaseTool]:
    await close_mcp_tools()
    return await init_mcp_tools(servers_override=servers_config, enabled=enabled)


async def close_mcp_tools() -> None:
    global _CLIENTS
    _LIVE_MCP_TOOLS.clear()
    if _CLIENTS is None:
        return
    try:
        await _CLIENTS.disconnect()
    finally:
        _CLIENTS = None
