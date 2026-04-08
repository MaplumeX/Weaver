# Tool Runtime Contracts

> Executable contracts for agent profiles, tool registry/runtime context, MCP,
> and streaming tool event payloads.

---

## Overview

These contracts apply when backend work changes any of:

- agent profile payloads (`/api/agents`)
- tool registry / capability resolution (`agent/infrastructure/tools/*`)
- MCP bootstrap (`tools/mcp.py`, `tools/core/mcp.py`)
- tool catalog payloads (`/api/tools/catalog`)
- tool event streaming payloads (`/api/chat`, `/api/events/{thread_id}`)
- Deep Research runtime tool policy snapshots (`deep_runtime.runtime_state`)

This document is mandatory for cross-layer tool-system work because the same
payloads are consumed by:

- backend persistence (`session_service`, session snapshots)
- runtime graphs (`chat`, `tool_agent`, Deep Research)
- frontend hooks (`useChatStream`, `useBrowserEvents`)
- generated OpenAPI TypeScript clients

---

## Scenario: Agent Profile Contract

### 1. Scope / Trigger

- Trigger: changing `common/agents_store.py`, `agent/domain/execution.py`, or
  `/api/agents` payloads.

### 2. Signatures

- File: `common/agents_store.py`
- Model: `AgentProfile`
- File: `main.py`
- Model: `AgentUpsertPayload`
- Endpoint:
  - `GET /api/agents`
  - `GET /api/agents/{agent_id}`
  - `POST /api/agents`
  - `PUT /api/agents/{agent_id}`

### 3. Contracts

Required profile fields:

- `id: str`
- `name: str`
- `system_prompt: str`
- `tools: list[str]`
- `blocked_tools: list[str]`
- `roles: list[str]`
- `capabilities: list[str]`
- `blocked_capabilities: list[str]`
- `policy: dict[str, Any]`
- `metadata: dict[str, Any]`

Rules:

- `tools`/`blocked_tools` remain concrete tool-name overrides.
- `roles`/`capabilities` are the preferred product-level configuration.
- `blocked_capabilities` removes concrete tools after capability expansion.
- `policy` must be JSON-object shaped; do not store free-form strings.

### 4. Validation & Error Matrix

| Input | Expected behavior | Error shape |
|-------|-------------------|-------------|
| Valid profile JSON | Persist and return normalized profile | `200` JSON |
| Missing `name` | FastAPI validation error | `422` |
| Unknown extra fields | Ignored by current Pydantic settings unless modeled | `200` or `422` depending on model |
| Updating missing agent id | Reject | `404` |
| Updating `default` agent via delete-protected path | Reject | `400` |

### 5. Good / Base / Bad Cases

Good:

```json
{
  "name": "Research Agent",
  "roles": ["default_agent"],
  "capabilities": ["search", "browser"],
  "blocked_capabilities": ["shell"],
  "policy": {"approval_mode": "manual"},
  "tools": ["browser_search"],
  "blocked_tools": []
}
```

Base:

```json
{
  "name": "Minimal Agent",
  "tools": [],
  "blocked_tools": [],
  "roles": [],
  "capabilities": [],
  "blocked_capabilities": [],
  "policy": {}
}
```

Bad:

```json
{
  "name": "",
  "roles": "default_agent",
  "capabilities": "search"
}
```

### 6. Tests Required

- `tests/test_agents_api.py`
  - assert new profile fields round-trip through POST/PUT
- `tests/test_agent_builtin_profiles.py`
  - assert built-in profiles carry `roles/capabilities/policy`
- `tests/test_agent_state_slices.py`
  - assert `build_initial_agent_state()` projects role/capability fields

### 7. Wrong vs Correct

#### Wrong

- Treat `capabilities` as concrete tool names.
- Store only `tools` and ignore `roles/capabilities`.

#### Correct

- Keep `tools` as explicit overrides.
- Treat `roles/capabilities` as first-class config inputs that resolve to
  concrete tools later.

---

## Scenario: Tool Registry / Runtime Context

### 1. Scope / Trigger

- Trigger: changing `agent/infrastructure/tools/runtime_context.py`,
  `registry.py`, `policy.py`, `assembly.py`, or capability/provider builders.

### 2. Signatures

- File: `agent/infrastructure/tools/runtime_context.py`
  - `build_tool_runtime_context(config, *, e2b_ready) -> ToolRuntimeContext`
- File: `agent/infrastructure/tools/registry.py`
  - `build_tool_registry(config) -> dict[str, ToolSpec]`
- File: `agent/infrastructure/tools/policy.py`
  - `resolve_profile_tool_policy(registry, *, profile) -> ToolPolicyResolution`

### 3. Contracts

`ToolRuntimeContext` fields:

- `thread_id`
- `user_id`
- `session_id`
- `agent_id`
- `run_id`
- `roles`
- `capabilities`
- `blocked_capabilities`
- `e2b_ready`

`ToolSpec` fields:

- `tool_id`
- `tool_name`
- `description`
- `capabilities`
- `source`
- `risk_level`
- `parameters`

Resolution contract:

1. Start from profile `roles` -> expand to capability defaults.
2. Merge explicit `capabilities`.
3. Expand capabilities to concrete tool names via registry.
4. Apply explicit `tools` override if present.
5. Remove `blocked_capabilities`.
6. Remove `blocked_tools`.

### 4. Validation & Error Matrix

| Condition | Expected behavior | Fallback |
|-----------|-------------------|----------|
| Empty profile | No tool grants unless explicit defaults are provided elsewhere | empty tuple/list |
| Unknown capability | Expands to nothing | safe no-op |
| Duplicate tool names | Deduped in registry/policy | keep first semantic entry |
| Provider tool missing `name` | Skip from registry | safe no-op |

### 5. Good / Base / Bad Cases

Good:

```python
profile = {
    "roles": ["default_agent"],
    "capabilities": ["search"],
    "blocked_capabilities": ["shell"],
    "tools": [],
    "blocked_tools": [],
}
```

Base:

```python
profile = {}
```

Bad:

```python
profile = {
    "capabilities": ["browser_search"],  # concrete tool leaked into capability field
}
```

### 6. Tests Required

- `tests/test_agent_tools.py`
  - capability expansion to concrete tools
  - blocked capability filtering
- `tests/test_tool_runtime_context.py`
  - context fields derived from config/profile
- `tests/test_tool_catalog_api.py`
  - catalog exposes `tool_id/capabilities/source/risk_level`

### 7. Wrong vs Correct

#### Wrong

```python
selected = profile["capabilities"]  # assumes capabilities are tool names
```

#### Correct

```python
registry = build_tool_registry(config)
resolution = resolve_profile_tool_policy(registry, profile=profile)
selected = resolution.allowed_tool_names
```

---

## Scenario: MCP Bootstrap Contract

### 1. Scope / Trigger

- Trigger: changing `tools/mcp.py`, `tools/core/mcp.py`, or MCP admin APIs.

### 2. Signatures

- File: `tools/mcp.py`
  - `init_mcp_tools(servers_override=None, enabled=None)`
  - `reload_mcp_tools(servers_config, enabled=None)`
  - `get_live_mcp_tools()`
  - `close_mcp_tools()`
- File: `tools/core/mcp.py`
  - official adapter path using `MultiServerMCPClient`

### 3. Contracts

Input server config accepts JSON object of MCP servers.

Private fields:

- `__thread_id__` may exist in `main.py` config shaping.
- `tools/mcp.py` must strip any `__*` keys before handing config to
  `MultiServerMCPClient`.

Output:

- `get_live_mcp_tools()` returns a snapshot list of LangChain-compatible tools.

### 4. Validation & Error Matrix

| Input | Expected behavior | Error behavior |
|-------|-------------------|----------------|
| `enabled=False` | close MCP and return `[]` | no error |
| Empty server map | close MCP and return `[]` | no error |
| Invalid JSON string | log error, disable MCP | return `[]` |
| Config with `__thread_id__` | strip private key before adapter call | return live tools |

### 5. Good / Base / Bad Cases

Good:

```json
{
  "demo": {"type": "sse", "url": "https://example.com/sse"}
}
```

Base:

```json
{}
```

Bad:

```json
{
  "__thread_id__": "catalog",
  "demo": {"type": "sse", "url": "https://example.com/sse"}
}
```

Bad because the adapter must not receive `__thread_id__`; sanitize first.

### 6. Tests Required

- `tests/test_mcp_tool_provider.py`
  - assert private thread hint is stripped
  - assert loaded tool count is returned by MCP config endpoint

### 7. Wrong vs Correct

#### Wrong

- Use project-private `MCPClients` as the runtime bootstrap path.

#### Correct

- Keep `tools/mcp.py` as a thin sanitizer/facade over `tools/core/mcp.py`
  using `MultiServerMCPClient`.

---

## Scenario: Tool Event Streaming Contract

### 1. Scope / Trigger

- Trigger: changing `main.py` tool event normalization, session persistence, or
  frontend tool event consumers.

### 2. Signatures

- Endpoint: `POST /api/chat` streaming response
- Endpoint: `GET /api/events/{thread_id}`
- Function: `_normalize_tool_event_data(event_type, data)`
- Function: `_build_langchain_tool_stream_payload(...)`
- Function: `_upsert_persisted_tool_invocation(...)`

### 3. Contracts

Chat stream contract:

- lifecycle events must emit `type: "tool"`
- progress events emit `type: "tool_progress"`
- screenshots emit `type: "tool_screenshot"` / `type: "screenshot"` depending on channel

Required `tool` payload fields:

- `tool_id`
- `name`
- `tool`
- `status`
- `phase`
- `payload`

Optional fields:

- `toolCallId`
- `args`
- `query`
- `result`

Persisted tool invocation shape:

- `toolId`
- `toolName`
- `toolCallId`
- `state`
- `phase`
- `args`
- `result`
- `payload`

`phase` mapping:

- `tool_start` -> `start`
- `tool_result` -> `result`
- `tool_error` -> `error`
- `tool_progress` -> `progress`

### 4. Validation & Error Matrix

| Event input | Stream output | Persistence output |
|-------------|---------------|--------------------|
| start payload without status | `status=running`, `phase=start` | invocation `state=running` |
| result payload with success omitted | `status=completed`, `phase=result` | invocation merged to `completed` |
| error payload | `status=failed`, `phase=error` | invocation merged to `failed` |
| progress payload | `type=tool_progress`, `phase=progress` | process event only, no invocation merge |

### 5. Good / Base / Bad Cases

Good:

```json
{
  "type": "tool",
  "data": {
    "tool_id": "browser_search",
    "name": "browser_search",
    "status": "running",
    "phase": "start",
    "args": {"query": "OpenAI"}
  }
}
```

Base:

```json
{
  "type": "tool_progress",
  "data": {
    "tool": "browser_search",
    "phase": "progress",
    "info": "https://example.com"
  }
}
```

Bad:

```json
{
  "type": "tool_start",
  "data": {"tool": "browser_search"}
}
```

Bad because `tool_start/tool_result/tool_error` are no longer the public stream
contract for chat/browser consumers; normalize them to `tool`.

### 6. Tests Required

- `tests/test_chat_stream_tool_events.py`
  - assert LangChain `on_tool_*` stream becomes `type="tool"`
- `tests/test_chat_session_persistence.py`
  - assert persisted `tool_invocations` include `toolId/phase/payload`
- `tests/test_tool_events_endpoint.py`
  - assert `/api/events/{thread}` normalizes lifecycle events to `type="tool"`
- `web/tests/session-utils.test.ts`
  - assert restored tool invocations preserve `toolId/phase`

### 7. Wrong vs Correct

#### Wrong

```python
yield await format_stream_event("tool_start", payload)
```

#### Correct

```python
yield await format_stream_event(
    "tool",
    _normalize_tool_event_data("tool_start", payload),
)
```

---

## Review Checklist

Before finishing tool-system work:

- [ ] `make openapi-types` run and generated files are updated if contracts changed
- [ ] `tests/test_agent_tools.py` updated if capability resolution changed
- [ ] `tests/test_mcp_tool_provider.py` updated if MCP bootstrap changed
- [ ] `tests/test_chat_stream_tool_events.py` updated if stream payload changed
- [ ] frontend hook/type consumers updated when stream or catalog payloads change
