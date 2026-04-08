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
- Deep Research branch runtime artifacts (`deep_research_artifacts`,
  `artifact_store`, `section_drafts`)

This document is mandatory for cross-layer tool-system work because the same
payloads are consumed by:

- backend persistence (`session_service`, session snapshots)
- runtime graphs (`chat`, `tool_agent`, Deep Research)
- frontend hooks (`useChatStream`, `useBrowserEvents`)
- generated OpenAPI TypeScript clients
- report/review stages that consume Deep Research draft artifacts

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
- File: `tools/search/contracts.py`
  - `SearchStrategy`
  - `SearchResult.to_dict() -> dict[str, Any]`
  - `SearchProvider.search(query, max_results=10) -> list[SearchResult]`
- File: `tools/search/web_search.py`
  - `run_web_search(*, query, max_results=5, strategy=None, provider_profile=None) -> list[dict[str, Any]]`
  - `web_search(query, max_results=5) -> list[dict[str, Any]]`

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

Search-tool contract:

- The only public API search tool name is `web_search`.
- `fallback_search` and `tavily_search` are not valid public tool names after
  the A2 search-runtime consolidation.
- `tools/search/orchestrator.py` is the internal runtime module that owns
  provider fan-out, reliability, cache lookup, and ranking.
- Do not add a second public API such as `multi_search(...)`; runtime callers
  should stay on `run_web_search(...)`.
- `settings.search_engines` is an ordered provider preference for
  `run_web_search`; it no longer selects between separate public tool
  implementations.
- `run_web_search(...)` delegates directly to the global search orchestrator
  and serializes `SearchResult` via `SearchResult.to_dict()`.
- `SearchResult.to_dict()` owns the normalized public payload shape, including
  fallback derivation for `summary`, `raw_excerpt`, and `content`.
- Runtime-owned callers that need normalized API search results should call
  `run_web_search(...)` instead of importing provider-specific tools.
- Runtime-owned callers should not layer a second search-result cache on top of
  `run_web_search(...)` unless they are intentionally changing cache scope or
  invalidation semantics.
- `web_search` / `run_web_search` return normalized result items with:
  `title`, `url`, `summary`, `snippet`, `raw_excerpt`, `content`, `score`,
  `published_date`, `provider`.

### 4. Validation & Error Matrix

| Condition | Expected behavior | Fallback |
|-----------|-------------------|----------|
| Empty profile | No tool grants unless explicit defaults are provided elsewhere | empty tuple/list |
| Unknown capability | Expands to nothing | safe no-op |
| Duplicate tool names | Deduped in registry/policy | keep first semantic entry |
| Provider tool missing `name` | Skip from registry | safe no-op |
| Unknown provider name in `search_engines` / `provider_profile` | Treat as preference only; keep available providers | safe fallback to remaining providers |
| `run_web_search(...)` provider failure | provider logs warning/error; orchestrator keeps trying based on strategy | return `[]` only after all paths fail |

### 5. Good / Base / Bad Cases

Good:

```python
profile = {
    "roles": ["default_agent"],
    "capabilities": ["search"],
    "blocked_capabilities": ["shell"],
    "tools": ["web_search"],
    "blocked_tools": [],
}
```

Base:

```python
profile = {"capabilities": ["search"]}
```

Bad:

```python
profile = {
    "tools": ["tavily_search", "fallback_search"],  # removed public tool names
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
- `tests/test_web_search.py`
  - `run_web_search(...)` respects provider preference and returns normalized payloads from `SearchResult.to_dict()`
- `tests/test_agent_builtin_profiles.py`
  - built-in profiles expose `web_search` instead of removed legacy API search tools
- `tests/test_deepsearch_web_search.py`
  - Deep Research runtime uses `run_web_search(...)`, does not add an extra outer cache, and returns `[]` on total failure

### 7. Wrong vs Correct

#### Wrong

```python
results = get_search_orchestrator().search(query="OpenAI")  # bypasses unified public runtime boundary
```

#### Correct

```python
results = run_web_search(
    query="OpenAI",
    max_results=5,
    provider_profile=settings.search_engines_list,
)
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

## Scenario: Deep Research Branch Runtime Contract

### 1. Scope / Trigger

- Trigger: changing `agent/runtime/deep/schema.py`,
  `agent/runtime/deep/roles/researcher.py`,
  `agent/runtime/deep/researcher_runtime/*`,
  `agent/runtime/deep/orchestration/graph.py`, or
  `agent/runtime/deep/artifacts/public_artifacts.py`.
- This is mandatory when the branch-scoped researcher loop, artifact-store
  snapshot keys, or public `deep_research_artifacts` payload shape changes.

### 2. Signatures

- File: `agent/runtime/deep/roles/supervisor.py`
  - `ResearchSupervisor.create_outline_plan(topic, *, approved_scope=None) -> dict[str, Any]`
- File: `agent/runtime/deep/roles/researcher.py`
  - `ResearchAgent.research_branch(task, *, topic, existing_summary="", max_results_per_query=5) -> dict[str, Any]`
- File: `agent/runtime/deep/researcher_runtime/runner.py`
  - `BranchResearchRunner.run(task, *, topic, existing_summary, max_results_per_query) -> dict[str, Any]`
- File: `agent/runtime/deep/orchestration/graph.py`
  - `LightweightArtifactStore.snapshot() -> dict[str, Any]`
- File: `agent/runtime/deep/artifacts/public_artifacts.py`
  - `build_public_deep_research_artifacts(...) -> dict[str, Any]`

### 3. Contracts

`ResearchTask` fields consumed by the branch runtime:

- required: `id`, `goal`, `query`, `priority`
- optional branch-policy fields:
  - `source_preferences: list[str]`
  - `authority_preferences: list[str]`
  - `coverage_targets: list[str]`
  - `language_hints: list[str]`
  - `deliverable_constraints: list[str]`
  - `source_requirements: list[str]`
  - `freshness_policy: str`
  - `time_boundary: str`

`OutlineSection` fields that must flow into section tasks when present:

- `coverage_targets`
- `source_preferences`
- `authority_preferences`
- `follow_up_policy`
- `branch_stop_policy`
- `deliverable_constraints`
- `constraints`
- `time_boundary`

`ResearchAgent.research_branch(...)` must return these top-level keys:

- `queries`
- `search_results`
- `sources`
- `documents`
- `passages`
- `summary`
- `key_findings`
- `open_questions`
- `confidence_note`
- `claim_units`
- `coverage_summary`
- `quality_summary`
- `contradiction_summary`
- `grounding_summary`
- `research_decisions`
- `limitations`
- `stop_reason`
- `branch_artifacts`

`branch_artifacts` must contain:

- `query_rounds`
- `coverage`
- `quality`
- `contradiction`
- `grounding`
- `decisions`

`SectionDraftArtifact` must persist the structured branch summaries:

- `coverage_summary`
- `quality_summary`
- `contradiction_summary`
- `grounding_summary`

`LightweightArtifactStore.snapshot()` and public
`deep_research_artifacts` payloads must expose these plural keys:

- `branch_query_rounds`
- `branch_coverages`
- `branch_qualities`
- `branch_contradictions`
- `branch_groundings`
- `branch_decisions`

Reviewer/reporter consumption rules:

- Reviewer should prefer `coverage_summary`, `quality_summary`,
  `contradiction_summary`, and `grounding_summary` from the draft instead of
  recomputing all branch quality from raw text only.
- `grounding_summary.primary_grounding_ratio` is the primary hard-gate input
  for claim grounding.
- Missing branch artifact lists in the store/public payload must degrade to
  `[]`/`{}` instead of raising.

### 4. Validation & Error Matrix

| Condition | Expected behavior | Fallback / output |
|-----------|-------------------|-------------------|
| Coverage + quality thresholds met inside branch loop | branch decision becomes `synthesize` | `stop_reason=""` |
| No new evidence and no follow-up queries | bounded stop | `stop_reason="evidence_stagnated"` or `no_follow_up_queries` |
| Only weak snippet evidence exists | draft may still be produced | reviewer can mark section `reportability=low` and `needs_manual_review=true` |
| Evidence dominated by one source domain | contradiction artifact requests counterevidence | advisory follow-up, not hard failure by itself |
| Branch artifacts omitted from merge/public adapters | merge must not crash | empty plural lists / empty summary dicts |

### 5. Good / Base / Bad Cases

Good:

```python
task = {
    "id": "task_1",
    "goal": "Research AI chips",
    "query": "AI chips market share",
    "priority": 1,
    "coverage_targets": ["Cloud training workload concentration"],
    "source_preferences": ["official filings"],
    "freshness_policy": "default_advisory",
    "time_boundary": "2025-2026",
}
```

Base:

```python
task = {
    "id": "task_1",
    "goal": "Research AI chips",
    "query": "AI chips market share",
    "priority": 1,
}
```

Bad:

```python
payload = {
    "summary": "...",
    "key_findings": ["..."],
    "branch_artifact": {"coverage": {}},  # wrong key and missing required summaries
}
```

Bad because downstream merge/public adapters and reviewer logic are keyed on
`branch_artifacts` plus the plural snapshot keys listed above.

### 6. Tests Required

- `tests/test_deepsearch_researcher.py`
  - assert branch runtime emits structured summaries and branch artifacts
  - assert bounded multi-round query refinement can cover missing criteria
- `tests/test_deepsearch_supervisor.py`
  - assert outline sections propagate richer branch policy fields
- `tests/test_deepsearch_multi_agent_runtime.py`
  - assert artifact store/public payload expose `branch_*` snapshot keys
  - assert section drafts carry structured coverage/quality/grounding summaries
  - assert report generation still works for low-confidence sections

### 7. Wrong vs Correct

#### Wrong

- Return only branch summary text from `research_branch(...)`.
- Recompute coverage/grounding later from free-form text only.
- Introduce singular or ad-hoc artifact-store keys such as `branch_quality`.

#### Correct

- Treat branch runtime output as a structured contract.
- Persist branch summaries into `SectionDraftArtifact`.
- Mirror branch artifact lists through `artifact_store.snapshot()` and the
  public `deep_research_artifacts` payload using the plural key names above.

---

## Review Checklist

Before finishing tool-system work:

- [ ] `make openapi-types` run and generated files are updated if contracts changed
- [ ] `tests/test_agent_tools.py` updated if capability resolution changed
- [ ] `tests/test_mcp_tool_provider.py` updated if MCP bootstrap changed
- [ ] `tests/test_chat_stream_tool_events.py` updated if stream payload changed
- [ ] frontend hook/type consumers updated when stream or catalog payloads change
