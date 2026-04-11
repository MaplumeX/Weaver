# Tool Runtime Contracts

> Executable contracts for agent profiles, tool registry/runtime context, MCP,
> and streaming tool event payloads.

---

## Overview

These contracts apply when backend work changes any of:

- agent profile payloads (`/api/agents`)
- tool registry / capability resolution (`agent/tooling/*`)
- MCP bootstrap (`tools/mcp.py`, `tools/core/mcp.py`)
- tool catalog payloads (`/api/tools/catalog`)
- tool event streaming payloads (`/api/chat`, `/api/events/{thread_id}`)
- Deep Research runtime tool policy snapshots
  (`deep_runtime["runtime_state"]`)
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

- Trigger: changing `common/agents_store.py`, `agent/execution/models.py`,
  `agent/execution/state.py`, or `/api/agents` payloads.

### 2. Signatures

- File: `common/agents_store.py`
  - Model: `AgentProfile`
- File: `agent/execution/models.py`
  - Model: `AgentProfileConfig`
  - `execution_mode_from_public_mode(mode, *, default=ExecutionMode.TOOL_ASSISTED) -> ExecutionMode`
- File: `main.py`
  - Model: `AgentUpsertPayload`
- Endpoint:
  - `GET /api/agents`
  - `GET /api/agents/{agent_id}`
  - `POST /api/agents`
  - `PUT /api/agents/{agent_id}`
  - `DELETE /api/agents/{agent_id}`

### 3. Contracts

Stored profile fields:

- `id: str`
- `name: str`
- `description: str`
- `system_prompt: str`
- `model: str`
- `tools: list[str]`
- `blocked_tools: list[str]`
- `roles: list[str]`
- `capabilities: list[str]`
- `blocked_capabilities: list[str]`
- `mcp_servers: dict[str, Any] | None`
- `policy: dict[str, Any]`
- `metadata: dict[str, Any]`
- `created_at: str`
- `updated_at: str`

Rules:

- `tools`/`blocked_tools` remain concrete tool-name overrides.
- `roles`/`capabilities` are the preferred product-level configuration.
- `blocked_capabilities` removes concrete tools after capability expansion.
- `policy` must be JSON-object shaped; do not store free-form strings.
- Legacy public search tool names `fallback_search` and `tavily_search` must
  normalize to `web_search` when profiles are loaded from disk.

### 4. Validation & Error Matrix

| Input | Expected behavior | Error shape |
|-------|-------------------|-------------|
| Valid profile JSON | Persist and return normalized profile | `200` JSON |
| Missing `name` | FastAPI validation error | `422` |
| Unknown extra fields | Ignored by current Pydantic settings unless modeled | `200` or `422` depending on model |
| Updating missing agent id | Reject | `404` |
| Deleting protected `default` agent | Reject | `400` |

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
- `tests/test_agents_store_migrations.py`
  - assert legacy tool names migrate to `web_search`
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

- Trigger: changing `agent/tooling/runtime_context.py`,
  `agent/tooling/registry.py`, `agent/tooling/policy.py`,
  `agent/tooling/assembly.py`, or capability/provider builders.

### 2. Signatures

- File: `agent/tooling/runtime_context.py`
  - `build_tool_runtime_context(config, *, e2b_ready) -> ToolRuntimeContext`
- File: `agent/tooling/registry.py`
  - `build_tool_registry(config) -> dict[str, ToolSpec]`
- File: `agent/tooling/policy.py`
  - `resolve_profile_tool_policy(registry, *, profile) -> ToolPolicyResolution`
- File: `agent/tooling/assembly.py`
  - `build_tool_inventory(config) -> list[BaseTool]`
  - `build_tools_for_names(config, tool_names) -> list[BaseTool]`
  - `build_agent_toolset(config) -> list[BaseTool]`
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
- `configurable`
- `profile`
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
| Missing `user_id` with `principal_user_id` or `memory_user_id` present | `ToolRuntimeContext.user_id` uses the first available fallback | `"default_user"` if none are provided |
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

- Trigger: changing `agent/deep_research/schema.py`,
  `agent/deep_research/agents/researcher.py`,
  `agent/deep_research/branch_research/*`,
  `agent/deep_research/engine/graph.py`,
  `agent/deep_research/engine/artifact_store.py`, or
  `agent/deep_research/artifacts/public_artifacts.py`.
- This is mandatory when the branch-scoped researcher loop, artifact-store
  snapshot keys, or public `deep_research_artifacts` payload shape changes.

### 2. Signatures

- File: `agent/deep_research/agents/supervisor.py`
  - `ResearchSupervisor.create_outline_plan(topic, *, approved_scope=None) -> dict[str, Any]`
- File: `agent/deep_research/agents/researcher.py`
  - `ResearchAgent.research_branch(task, *, topic, existing_summary="", max_results_per_query=5) -> dict[str, Any]`
- File: `agent/deep_research/branch_research/runner.py`
  - `BranchResearchRunner.run(task, *, topic, existing_summary, max_results_per_query) -> dict[str, Any]`
- File: `agent/deep_research/engine/artifact_store.py`
  - `LightweightArtifactStore.snapshot() -> dict[str, Any]`
- File: `agent/deep_research/artifacts/public_artifacts.py`
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
- File: `agent/deep_research/engine/graph.py`
  - `MultiAgentDeepResearchRuntime._build_report_sections(store) -> list[ReportSectionContext]`
  - `MultiAgentDeepResearchRuntime._aggregate_sections(queue, store, runtime_state) -> dict[str, Any]`
- File: `agent/deep_research/agents/reporter.py`
  - `ResearchReporter.generate_report(topic_or_context, findings=None, sources=None) -> str`
  - `ResearchReporter.generate_executive_summary(report, topic, *, report_context=None) -> str`
- Reporter admission contract:
  - Sections with `reportability in {"high", "medium"}` may enter the final
    report context.
  - Sections with `reportability in {"low", "insufficient"}` must be excluded
    from the final report context.
  - Sections with `contradiction_summary.has_material_conflict == true` must be
    excluded from the final report context even if `reportability == "medium"`.
  - `quality_summary.report_ready` / `outline_gate_summary.report_ready` mean
    "at least one admitted section is available for reporting", not merely
    "some section draft has non-empty text".
- Reporter prompt contract:
  - Reporter input may use `summary`, `key_findings`, and admitted
    `source_urls`.
  - Reporter input must not rely on `limitations`, `open_questions`,
    `manual_review_items`, or advisory/blocking issue text for final body
    generation in the "silent denoise" path.
- Executive summary contract:
  - `generate_executive_summary(...)` should prefer admitted section
    `summary`/`findings` when `report_context` is available, instead of
    truncating only the final markdown body.
- Missing branch artifact lists in the store/public payload must degrade to
  `[]`/`{}` instead of raising.

### 4. Validation & Error Matrix

| Condition | Expected behavior | Fallback / output |
|-----------|-------------------|-------------------|
| Coverage + quality thresholds met inside branch loop | branch decision becomes `synthesize` | `stop_reason=""` |
| No new evidence and no follow-up queries | bounded stop | `stop_reason="evidence_stagnated"` or `no_follow_up_queries` |
| Only weak snippet evidence exists | draft may still be produced | reviewer can mark section `reportability=low` and `needs_manual_review=true` |
| Evidence dominated by one source domain | contradiction artifact requests counterevidence | advisory follow-up, not hard failure by itself |
| Draft has `reportability=low` or `insufficient` | reporter excludes it from final report context | `report_ready=false` when no admitted sections remain |
| Draft has `reportability=medium` but `contradiction_summary.has_material_conflict=true` | reporter excludes it from final report context | final report omits the section |
| Final report is long but admitted `report_context` is available | executive summary uses admitted section summaries/findings first | avoids summary drift from truncated markdown |
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

Good reporter-admission case:

```python
draft = {
    "summary": "Cloud demand remains concentrated in a few hyperscalers.",
    "key_findings": ["NVIDIA remains the dominant training supplier."],
    "contradiction_summary": {"has_material_conflict": False},
}
review = {"reportability": "medium"}
certification = {"certified": True, "reportability": "medium"}
```

Base reporter-admission case:

```python
draft = {
    "summary": "Supply remains constrained.",
    "key_findings": [],
    "contradiction_summary": {},
}
review = {"reportability": "high"}
certification = {"certified": True}
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

Bad reporter-admission case:

```python
draft = {
    "summary": "Unverified market share claim",
    "key_findings": ["Vendor X holds 80% share"],
    "contradiction_summary": {"has_material_conflict": True},
}
review = {"reportability": "medium"}
```

Bad because final report generation must not surface materially conflicting
sections just because the draft text is non-empty.

### 6. Tests Required

- `tests/test_deepsearch_researcher.py`
  - assert branch runtime emits structured summaries and branch artifacts
  - assert bounded multi-round query refinement can cover missing criteria
- `tests/test_deepsearch_supervisor.py`
  - assert outline sections propagate richer branch policy fields
- `tests/test_deepsearch_multi_agent_runtime.py`
  - assert artifact store/public payload expose `branch_*` snapshot keys
  - assert section drafts carry structured coverage/quality/grounding summaries
  - assert report generation excludes `low`/`insufficient` sections from the
    admitted reporter context
  - assert materially conflicting sections are excluded from the admitted
    reporter context
  - assert admitted `medium` sections keep only the truncated reporter finding
    set when the silent-denoise path is active
- `tests/test_deepsearch_reporter.py`
  - assert reporter prompt omits risk/manual-review/limitation blocks in the
    silent-denoise path
  - assert executive summary prefers admitted `report_context` summaries over
    raw markdown truncation
- `tests/test_agent_runtime_public_contracts.py`
  - assert removed legacy `agent.runtime.*` / `agent.research.*` modules stay
    non-importable after the capability-package split

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

---

## Scenario: Runtime Config And Model Resolution

### 1. Scope / Trigger

- Trigger: changing runtime-node config readers, Deep Research runtime config
  readers, or task-to-model resolution helpers.
- Applies to:
  - `agent/execution/config_utils.py`
  - `agent/foundation/multi_model.py`
  - `agent/execution/shared.py`
  - `agent/chat/prompting.py`
  - `agent/deep_research/engine/runtime_context.py`

### 2. Signatures

- File: `agent/execution/config_utils.py`
  - `configurable_dict(config) -> dict[str, Any]`
  - `configurable_value(config, key) -> Any`
  - `configurable_int(config, key, default) -> int`
  - `configurable_float(config, key, default) -> float`
- File: `agent/foundation/multi_model.py`
  - `resolve_model_name(task_type: str, config: dict[str, Any] | None = None) -> str`
- Runtime aliases:
  - `agent/execution/shared.py`
    - `_configurable = configurable_dict`
    - `_model_for_task = resolve_model_name`
  - `agent/chat/prompting.py`
    - `_configurable = configurable_dict`
  - `agent/deep_research/engine/runtime_context.py`
    - `_configurable_value = configurable_value`
    - `_configurable_int = configurable_int`
    - `_configurable_float = configurable_float`
    - `_model_for_task = resolve_model_name`

### 3. Contracts

Runtime config contract:

1. Runtime helpers only read overrides from `config["configurable"]`.
2. Missing config, non-dict config, or non-dict `configurable` payloads must
   degrade to `{}` instead of raising.
3. Integer/float readers must accept stringified numeric values and return the
   provided default on `None`, wrong types, or parse failure.

Model resolution contract:

1. Known task strings must delegate to `ModelRouter.get_model_name(...)`.
2. Unknown task strings must not raise; they fall back to general runtime
   overrides and settings defaults.
3. For reasoning tasks, fallback priority is:
   - `configurable.reasoning_model`
   - `configurable.model`
   - `settings.reasoning_model`
   - `settings.primary_model`
4. For non-reasoning or unknown non-reasoning tasks, fallback priority is:
   - `configurable.model`
   - `settings.primary_model`
5. Runtime nodes and Deep Research support helpers must reuse the shared
   helpers above instead of reimplementing config parsing or task/model
   fallback chains locally.

### 4. Validation & Error Matrix

| Input / Condition | Expected behavior | Fallback |
|------------------|-------------------|----------|
| `config is None` | treat as empty config | `{}` / default |
| `config["configurable"]` missing | no override applied | `{}` / default |
| `config["configurable"]` is not a dict | ignore invalid payload | `{}` / default |
| `configurable_int(..., "4", default)` | parse to `4` | n/a |
| `configurable_int(..., "oops", default)` | ignore invalid override | return `default` |
| `resolve_model_name("planning", {"configurable": {"reasoning_model": "x"}})` | use reasoning override | `"x"` |
| `resolve_model_name("writing", {"configurable": {"model": "y"}})` | use general model override | `"y"` |
| `resolve_model_name("legacy_unknown_task", {"configurable": {"model": "z"}})` | do not raise on unknown task string | `"z"` |

### 5. Good / Base / Bad Cases

Good:

```python
config = {
    "configurable": {
        "reasoning_model": "gpt-5-thinking",
        "model": "gpt-4o",
        "deep_research_max_epochs": "6",
    }
}

assert resolve_model_name("planning", config) == "gpt-5-thinking"
assert configurable_int(config, "deep_research_max_epochs", 3) == 6
```

Base:

```python
config = {"configurable": {"model": "gpt-4o-mini"}}

assert resolve_model_name("writing", config) == "gpt-4o-mini"
assert configurable_float(config, "deep_research_max_seconds", 30.0) == 30.0
```

Bad:

```python
config = {"configurable": {"deep_research_max_epochs": "oops"}}
value = configurable_int(config, "deep_research_max_epochs", 3)
```

Bad because runtime helpers must not trust invalid numeric overrides; this must
return `3` instead of raising or preserving the malformed string.

Bad:

```python
resolve_model_name("legacy_unknown_task", {})
```

Bad if it raises `ValueError` for the unknown task name. Unknown runtime task
strings must still degrade to settings-backed defaults.

### 6. Tests Required

- `tests/test_multi_model_resolve_model_name.py`
  - assert writing tasks prefer `configurable.model`
  - assert reasoning tasks prefer `configurable.reasoning_model`
  - assert unknown task names do not raise and still use general fallback
- `tests/test_chat_first_agent_nodes.py`
  - assert chat node still resolves a writing model and answers without tools
- `tests/test_deepsearch_multi_agent_runtime.py`
  - assertion points that Deep Research runtime still accepts numeric config
    overrides and builds the multi-agent runtime successfully
- `tests/test_tool_runtime_context.py`
  - assert runtime config fallback fields still project through
    `ToolRuntimeContext`

### 7. Wrong vs Correct

#### Wrong

- Re-implement `config["configurable"]` parsing in each runtime module.
- Keep a second ad-hoc task/model fallback chain in node helpers or Deep
  Research support helpers.
- Raise on unknown task strings passed from runtime-owned code.

#### Correct

- Reuse `configurable_dict/value/int/float(...)` for runtime override parsing.
- Reuse `resolve_model_name(...)` for task-string model selection.
- Keep the router-backed selection contract in one place so runtime nodes and
  Deep Research support stay behaviorally aligned.

---

## Scenario: Knowledge File RAG Ingestion And Retrieval

### 1. Scope / Trigger

- Trigger: changing knowledge-file upload/download endpoints, MinIO object
  storage integration, Milvus retrieval integration, or Deep Research
  researcher/runtime code that merges private knowledge into branch evidence.
- Applies to:
  - `main.py`
  - `common/config.py`
  - `common/knowledge_registry.py`
  - `tools/rag/service.py`
  - `tools/rag/file_parser.py`
  - `agent/deep_research/agents/researcher.py`
  - `agent/deep_research/branch_research/research_pipeline.py`
  - `web/hooks/useKnowledgeFiles.ts`
  - `web/components/views/Library.tsx`
- This is an infra and cross-layer contract:
  Library upload UI -> FastAPI multipart API -> MinIO original-file storage ->
  parser/chunker/embedding provider -> Milvus collection -> Deep Research
  source normalization -> frontend file/status display.

### 2. Signatures

- File: `main.py`
  - `GET /api/knowledge/files`
  - `POST /api/knowledge/files`
  - `POST /api/knowledge/files/{file_id}/reindex`
  - `DELETE /api/knowledge/files/{file_id}`
  - `GET /api/knowledge/files/{file_id}/download`
- File: `common/knowledge_registry.py`
  - `KnowledgeFileRecord.content_hash: str`
  - `KnowledgeRegistry.find_record_by_content_hash(content_hash, exclude_id=None) -> KnowledgeFileRecord | None`
  - `KnowledgeRegistry.delete_record(record_id: str) -> KnowledgeFileRecord | None`
- File: `tools/rag/service.py`
  - `KnowledgeObjectStore.upload_bytes(file_id, filename, content_type, data) -> tuple[str, str]`
  - `KnowledgeObjectStore.delete_object(bucket: str, object_key: str) -> None`
  - `RagEmbeddingClient.embed_texts(texts: list[str]) -> list[list[float]]`
  - `KnowledgeMilvusStore.ensure_collection(dimension: int) -> None`
  - `KnowledgeMilvusStore.insert_chunks(chunks: list[dict[str, Any]]) -> None`
  - `KnowledgeMilvusStore.delete_file_chunks(file_id: str) -> None`
  - `KnowledgeMilvusStore.search(query_vector: list[float], limit: int) -> list[dict[str, Any]]`
  - `KnowledgeService.ingest_file(filename, content_type, data) -> KnowledgeFileRecord`
  - `KnowledgeService.reindex_file(file_id: str) -> KnowledgeFileRecord`
  - `KnowledgeService.delete_file(file_id: str) -> KnowledgeFileRecord`
  - `KnowledgeService.download_file(file_id: str) -> tuple[KnowledgeFileRecord, bytes]`
  - `KnowledgeService.search(query: str, limit: int | None = None) -> list[dict[str, Any]]`
- File: `common/config.py`
  - `knowledge_allowed_extensions`
  - `knowledge_max_upload_bytes`
  - `knowledge_chunk_max_chars`
  - `knowledge_search_top_k`
  - `knowledge_milvus_collection`
  - `minio_endpoint`, `minio_access_key`, `minio_secret_key`, `minio_bucket`, `minio_secure`
  - `milvus_uri`, `milvus_token`, `milvus_db_name`
  - `rag_embedding_model`, `rag_embedding_api_key`, `rag_embedding_base_url`,
    `rag_embedding_timeout`, `rag_embedding_dimensions`, `rag_embedding_batch_size`
- File: `web/hooks/useKnowledgeFiles.ts`
  - `useKnowledgeFiles()`
- File: `web/components/views/Library.tsx`
  - knowledge upload entry and knowledge-base list rendering

### 3. Contracts

Knowledge upload contract:

1. `POST /api/knowledge/files` accepts `multipart/form-data` with one or more
   `files` parts.
2. Supported extensions are `pdf`, `docx`, `md`, and `txt`.
3. Original file bytes must be stored in MinIO before indexing, and the stored
   `bucket` / `object_key` must be persisted into `KnowledgeFileRecord`.
4. `GET /api/knowledge/files/{file_id}/download` must stream the original file
   bytes from MinIO using the recorded storage location.
5. Upload dedupe is content-based, not filename-based: the backend computes a
   stable `content_hash` from raw bytes before ingest and rejects duplicate
   uploads instead of creating a second record.
6. `POST /api/knowledge/files/{file_id}/reindex` must rebuild chunks from the
   original stored object for the same `file_id`; it is a maintenance action,
   not a new upload.
7. `DELETE /api/knowledge/files/{file_id}` must remove both the original
   object-store payload and the Milvus chunks for that `file_id` before the
   registry entry is deleted.

Embedding-provider contract:

1. Query/document embeddings use only the dedicated `rag_embedding_*`
   settings.
2. `RagEmbeddingClient` must not fall back to `OPENAI_API_KEY`,
   `OPENAI_BASE_URL`, or any primary LLM provider config.
3. Large chunk batches must be split by `rag_embedding_batch_size`; provider
   per-request limits are an integration concern, not a caller concern.

Milvus schema contract:

1. Existing collections must be introspected with
   `MilvusClient.describe_collection(...)`; do not assume field names.
2. The active primary-key field and vector field come from the real collection
   schema, not hard-coded defaults.
3. New collections created by Weaver use:
   - primary key: `chunk_id`
   - vector field: `embedding`
   - dynamic fields enabled for chunk metadata
4. Insert payloads must be mapped to the actual collection schema. For example,
   if the collection primary key is `chunk_id` and the vector field is
   `embedding`, inserts must send those exact field names even if the internal
   chunk payload was assembled as `id` / `vector`.
5. Search requests must set `anns_field` to the real vector field name and
   request `chunk_id`-compatible output fields.
6. Existing collection vector dimension and embedding output dimension must
   match; fail early if they differ.
7. Maintenance deletes/reindexes must target chunks by `file_id`, not by
   guessing chunk ids from filenames.

Research runtime contract:

1. `KnowledgeService.search(...)` returns normalized search-result dicts that
   can be merged with web search results by `ResearchAgent._search(...)`.
2. RAG hits must flow through the normal
   `documents / passages / synthesis` pipeline, not a side-channel prompt
   append.
3. RAG-only documents are authoritative knowledge-file sources and must bypass
   HTTP refetch in `build_documents_and_sources(...)`.

Registry/UI contract:

1. `common/knowledge_registry.py` remains the owner of lightweight file-status
   metadata; do not move this small runtime state into a heavier persistence
   layer without need.
2. Library UI renders indexed/uploading/failed statuses from the backend
   registry payload and uses the API download path for file retrieval.
3. Library UI triggers maintenance actions through the backend:
   `Reindex` calls `POST /api/knowledge/files/{file_id}/reindex`, and `Delete`
   calls `DELETE /api/knowledge/files/{file_id}` with destructive confirmation.
4. OpenAPI-generated frontend types must stay in sync when these endpoints or
   response models change.

### 4. Validation & Error Matrix

| Input / Condition | Expected behavior | Surface |
|------------------|-------------------|---------|
| Unsupported extension | reject upload | `400` HTTP |
| File exceeds `knowledge_max_upload_bytes` | reject upload | `400` HTTP |
| Duplicate content hash matches an existing registry record | reject upload without new record creation | `409` HTTP |
| MinIO not configured | fail upload before parse/index | `503` HTTP |
| RAG embedding provider not configured | fail upload/search without falling back to LLM config | `503` HTTP or empty best-effort search |
| Milvus not configured | fail upload before indexing | `503` HTTP |
| Uploaded file has no extractable text | mark file failed with error | indexed record status |
| Embedding provider request limit exceeded | client splits into multiple requests via `rag_embedding_batch_size` | internal adapter behavior |
| Existing Milvus collection uses `chunk_id` / `embedding` | adapter introspects schema and maps payload accordingly | internal adapter behavior |
| Existing Milvus collection dimension differs from embedding output | stop ingest with clear runtime error | failed record / logs |
| Reindex target is missing from registry | reject maintenance request | `404` HTTP |
| Delete target is missing from registry | reject maintenance request | `404` HTTP |
| Reindex target has no stored object location | keep registry record, fail request or record update clearly | `503` HTTP or failed record |
| Milvus unavailable during researcher query | RAG returns no hits and researcher continues with web search | best-effort runtime fallback |

### 5. Good / Base / Bad Cases

Good:

```python
schema = {
    "fields": [
        {"name": "chunk_id", "is_primary": True, "type": DataType.VARCHAR},
        {"name": "embedding", "type": DataType.FLOAT_VECTOR, "params": {"dim": 1024}},
    ],
    "enable_dynamic_field": True,
}

chunk = {
    "id": "kf_1:1",
    "chunk_id": "kf_1:1",
    "file_id": "kf_1",
    "vector": [0.1, 0.2],
}
```

Good because the adapter maps this to Milvus as `chunk_id` + `embedding` and
keeps metadata in dynamic fields.

Base:

```python
settings.rag_embedding_batch_size = 64
texts = ["chunk-1", "chunk-2"]
embeddings = RagEmbeddingClient().embed_texts(texts)
```

Base because small requests still use the same dedicated provider path without
special casing.

Good:

```python
content_hash = hashlib.sha256(data).hexdigest()
existing = registry.find_record_by_content_hash(content_hash)
if existing is not None:
    raise DuplicateKnowledgeFileError(existing)
```

Good because duplicate prevention happens before a new registry record or
vector insert is created.

Bad:

```python
payload = {"id": "kf_1:1", "vector": [0.1, 0.2]}
client.insert(collection_name="knowledge_chunks", data=[payload])
```

Bad because an existing collection may require `chunk_id` and `embedding`;
hard-coding create-time defaults causes runtime insert failures.

Bad:

```python
if not settings.rag_embedding_api_key:
    settings.rag_embedding_api_key = settings.openai_api_key
```

Bad because knowledge retrieval must not silently reuse the primary LLM
provider.

Bad:

```python
service.ingest_file(filename="guide-copy.txt", content_type="text/plain", data=data)
```

Bad when the same `data` already exists in the registry because it creates
duplicate file records and duplicate Milvus chunks for identical content.

### 6. Tests Required

- `tests/test_knowledge_service.py`
  - assert original bytes are uploaded before indexing metadata is finalized
  - assert duplicate content is rejected before a new record is created
  - assert reindex rebuilds chunks from the stored object for the same `file_id`
  - assert delete removes both object-store payload and Milvus chunks
  - assert dedicated embedding-provider config is used without LLM fallback
  - assert large embedding batches split according to `rag_embedding_batch_size`
  - assert existing Milvus `chunk_id` / `embedding` schema is introspected and
    mapped correctly
  - assert dimension mismatch raises a clear runtime error
- `tests/test_knowledge_api.py`
  - assert list/upload/download/delete/reindex endpoint contracts
  - assert duplicate upload returns `409`
- `tests/test_deepsearch_researcher.py`
  - assert RAG hits merge into researcher documents without HTTP refetch
- Assertion points:
  - `KnowledgeFileRecord.content_hash`
  - `KnowledgeFileRecord.bucket`
  - `KnowledgeFileRecord.object_key`
  - `KnowledgeFileRecord.status`
  - Milvus insert payload field names
  - Milvus delete filter uses `file_id`
  - Milvus search `anns_field`
  - normalized result `chunk_id` / `url`

### 7. Wrong vs Correct

#### Wrong

- Treat an external Milvus collection as if Weaver always created it.
- Hard-code insert/search field names as `id` and `vector`.
- Reuse primary LLM provider settings when `rag_embedding_*` is empty.
- Detect duplicate uploads only by filename while ignoring byte-identical
  content.
- Upload a file, index it, but keep the original bytes only in process memory
  or temp files instead of MinIO.

#### Correct

- Introspect real collection schema before insert/search.
- Map internal chunk payloads onto the actual Milvus primary/vector field
  names.
- Keep original uploaded bytes in MinIO and serve downloads from that storage.
- Keep query/document embeddings on the dedicated RAG provider settings only.
