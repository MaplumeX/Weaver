# Tool Runtime Architecture

## Runtime Source Of Truth

- Runtime tools come from provider-composed `BaseTool` inventories.
- `agent/infrastructure/tools/assembly.py` builds the full inventory and the
  filtered agent-facing toolset.
- Profile flags, capability aliases, whitelist, and blacklist checks are policy
  concerns layered on top of that inventory.

## Catalog Layer

- `ToolRegistry` remains available for metadata discovery and developer-facing
  catalog refresh workflows.
- `/api/tools/registry` and `/api/health/agent` now expose runtime inventory
  snapshots instead of treating the registry as the execution source of truth.

## Compatibility Layer

- `WeaverTool` is an authoring-time compatibility abstraction.
- `tools/core/langchain_adapter.py` is a bridge for migrating legacy
  `WeaverTool` definitions into LangChain `BaseTool` instances.
- `set_registered_tools()` only exists as a backward-compatible shim and should
  not drive runtime assembly.

## MCP Integration

- MCP tools are exposed through a live runtime snapshot in `tools/mcp.py`.
- The runtime inventory reads that snapshot through the MCP provider rather than
  mutating a global registered-tools list.
