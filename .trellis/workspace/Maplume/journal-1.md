# Journal - Maplume (Part 1)

> AI development session journal
> Started: 2026-04-07

---



## Session 1: Bootstrap backend Trellis guidelines

**Date**: 2026-04-07
**Task**: Bootstrap backend Trellis guidelines

### Summary

Filled backend Trellis specs from actual repository patterns and archived the bootstrap task.

### Main Changes

| Area | Description |
|------|-------------|
| Backend specs | Replaced `.trellis/spec/backend/` templates with project-specific guidance for structure, persistence, error handling, logging, and quality expectations |
| Research basis | Extracted conventions from `main.py`, `common/`, `agent/`, `tools/`, `triggers/`, tests, and repo-level docs |
| Task tracking | Archived `00-bootstrap-guidelines` and preserved `implement/check/debug` context files under the archive directory |

**Updated Specs**:
- `.trellis/spec/backend/index.md`
- `.trellis/spec/backend/directory-structure.md`
- `.trellis/spec/backend/database-guidelines.md`
- `.trellis/spec/backend/error-handling.md`
- `.trellis/spec/backend/logging-guidelines.md`
- `.trellis/spec/backend/quality-guidelines.md`

**Archived Task**:
- `.trellis/tasks/archive/2026-04/00-bootstrap-guidelines/task.json`


### Git Commits

| Hash | Message |
|------|---------|
| `29641f8` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: Redesign long-term memory system

**Date**: 2026-04-07
**Task**: Redesign long-term memory system

### Summary

Rebuilt long-term memory around a project-owned PostgreSQL memory store/service, unified chat/support/session ingestion around explicit user memory intent, added memory debug/admin APIs, migrated backend specs, and added regression tests for memory store/service/API/session integration.

### Main Changes



### Git Commits

| Hash | Message |
|------|---------|
| `7c68373` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: Remove Legacy Long-Term Memory Compatibility

**Date**: 2026-04-07
**Task**: Remove Legacy Long-Term Memory Compatibility

### Summary

删除旧长期记忆兼容路径，保留项目自有长期记忆主路径，并补充 DDL 防回归保护。

### Main Changes

| Area | Description |
|------|-------------|
| Backend memory cleanup | 删除 mem0 / JSON fallback / legacy migration / 旧 helper 包装，只保留 `MemoryService` + `MemoryStore` + `/api/memory/*` 主路径 |
| Config and schema | 清理旧 memory 配置项，删除 `memory_user_migrations` DDL，并修复一次 DDL 括号错误 |
| Type sync | 重新生成 `web/lib/api-types.ts` 和 `sdk/typescript/src/openapi-types.ts` |
| Tests and docs | 更新 memory 相关回归测试，新增 `tests/test_persistence_schema.py`，补充数据库规范里的 DDL 删除注意事项 |

**Validation**:
- `python3 -m compileall main.py common`
- `uv run pytest` 针对 memory / startup / stream 相关目标集通过
- `uv run ruff check --select I001,F401 ...` 通过
- 按用户要求，未将全量 `build` / 全量 `test` 作为提交阻塞项


### Git Commits

| Hash | Message |
|------|---------|
| `756cdb0` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: 修复 Deep Research interrupt 恢复状态

**Date**: 2026-04-07
**Task**: 修复 Deep Research interrupt 恢复状态

### Summary

修复自定义 checkpointer 的最新 checkpoint 选择与特殊 __interrupt__/__resume__ 写入覆盖语义，补充回归测试，并更新相关 backend/cross-layer spec。

### Main Changes



### Git Commits

| Hash | Message |
|------|---------|
| `efaf856` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: Repo-wide lint pass and runtime export fixes

**Date**: 2026-04-07
**Task**: Repo-wide lint pass and runtime export fixes

### Summary

完成全仓库 Ruff 收口，修复 agent facade / deep research runtime 导出缺口，并对齐前端 search_mode 类型与相关回归测试。

### Main Changes

| Area | Description |
|------|-------------|
| Lint | 配置 Ruff 忽略 `.trellis/`，修复全仓库历史 lint 问题，并修正 `scripts/ruff_changed_files.sh` 的空结果边界行为 |
| Runtime Exports | 恢复 `agent/api.py` 的公共导出，修复 `agent.runtime.deep.orchestration.graph` 的依赖容器导出，消除 `ImportError` / `AttributeError` |
| Backend Compatibility | 补齐 `answer.py` 与 deep runtime 模块级依赖绑定，恢复测试中的 monkeypatch 入口 |
| Frontend Types | 修复 `web/lib/chat-request.ts` 的 `search_mode` payload 类型，打通 `tsc --noEmit` |

**Verification**:
- `make lint-all`
- `make test` (`379 passed, 1 skipped, 2 warnings`，由人工确认)
- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`
- `pnpm -C web test`

**Notes**:
- 本次未归档 `.trellis/tasks/04-07-prune-agentstate-fields`，因为它仍是未完成且未跟踪的独立任务。
- 为避免误提交该任务目录，本次 session 记录使用 `--no-commit`。


### Git Commits

| Hash | Message |
|------|---------|
| `ac7a5eb` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: Prune Unused AgentState Root Fields

**Date**: 2026-04-07
**Task**: Prune Unused AgentState Root Fields

### Summary

Reorganized the agent module into capability-owned packages, split Deep Research internals into focused runtime components, migrated shared helpers to their new owners, and synced backend Trellis specs to the new architecture.

### Main Changes

| Area | Description |
|------|-------------|
| Runtime state | Removed unused root `AgentState` fields from the root graph contract and initial state builder |
| Node updates | Stopped returning unused routing/tool bookkeeping fields from root graph nodes |
| Tests | Updated root graph and state slice tests to assert the leaner state contract |
| Verification | Ran targeted Ruff and pytest checks for the touched backend files |

**Updated Files**:
- `agent/application/state.py`
- `agent/core/state.py`
- `agent/domain/state.py`
- `agent/runtime/nodes/answer.py`
- `agent/runtime/nodes/chat.py`
- `agent/runtime/nodes/routing.py`
- `tests/test_agent_state_slices.py`
- `tests/test_root_graph_contract.py`

**Checks Run**:
- `uv run ruff check agent/application/state.py agent/core/state.py agent/domain/state.py agent/runtime/nodes/chat.py agent/runtime/nodes/answer.py agent/runtime/nodes/routing.py tests/test_agent_state_slices.py tests/test_root_graph_contract.py`
- `uv run pytest tests/test_agent_state_slices.py tests/test_root_graph_contract.py`

**Task Status**:
- Archived `04-07-prune-agentstate-fields`


### Git Commits

| Hash | Message |
|------|---------|
| `9f9e386` | (see git log) |

### Testing

- [OK] `uv run ruff check agent tests main.py common tools`
- [OK] `uv run pytest ...` for agent profile, tooling/runtime context, chat/session, checkpointer/session store, and Deep Research regression coverage (`122 passed`)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: Prune deep research legacy runtime snapshots

**Date**: 2026-04-07
**Task**: Prune deep research legacy runtime snapshots

### Summary

收口 deep research 运行时到当前 multi_agent 契约，删除旧 nested runtime snapshot 兼容读取，并补充回归测试。

### Main Changes

| Area | Description |
|------|-------------|
| Deep Runtime Flow | 梳理并确认当前执行链路为 bootstrap -> clarify -> scope -> scope_review -> research_brief -> outline_plan -> dispatch -> researcher/revisor -> merge -> reviewer -> supervisor_decide -> outline_gate -> report -> final_claim_gate -> finalize |
| Artifact Projection | 删除 legacy artifact_store 适配，只保留 lightweight snapshot 到 public artifacts 的投影 |
| Runtime Store | 去掉 `branch_results` / `validation_summaries` 等旧键恢复与别名入口，统一使用 `section_drafts` / `section_reviews` |
| Regression Tests | 增加测试，明确旧 nested runtime snapshot 不再恢复 public artifacts，且 runtime store 不再接受旧键名 |

**Updated Files**:
- `agent/runtime/deep/artifacts/public_artifacts.py`
- `agent/runtime/deep/orchestration/graph.py`
- `tests/test_checkpoint_runtime_artifacts.py`
- `tests/test_deepsearch_multi_agent_runtime.py`

**Validation**:
- `uv run ruff check agent/runtime/deep/artifacts/public_artifacts.py agent/runtime/deep/orchestration/graph.py tests/test_checkpoint_runtime_artifacts.py tests/test_deepsearch_multi_agent_runtime.py`
- `uv run pytest tests/test_checkpoint_runtime_artifacts.py tests/test_deepsearch_multi_agent_runtime.py tests/test_deepsearch_mode_selection.py tests/test_resume_session_deepsearch.py`
- `uv run pytest tests/test_session_evidence_api.py tests/test_export_json.py`


### Git Commits

| Hash | Message |
|------|---------|
| `9bc3f7b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: Improve chat short-term memory pipeline

**Date**: 2026-04-07
**Task**: Improve chat short-term memory pipeline

### Summary

统一 chat 短期记忆链路，删除未使用 ContextWindowManager，并修复 SessionStore 共享连接并发问题

### Main Changes

| Area | Description |
|------|-------------|
| Chat runtime | 从 session history 回填最近对话到 runtime messages，并统一 seed history 与运行期裁剪/摘要策略 |
| Persistence | 为 SessionStore 共享 AsyncConnection 增加串行化保护，避免并发请求触发 another command is already in progress |
| Cleanup | 删除未接入主链路的 `agent/core/context_manager.py` 与相关导出 |
| Spec | 补充 backend database guideline，记录 SessionStore 单连接并发约束 |

**Validated**:
- `uv run ruff check` on touched Python files
- targeted pytest for session store/service, chat persistence, prompt/runtime state paths

**Updated Files**:
- `main.py`
- `common/session_store.py`
- `common/session_service.py`
- `agent/application/state.py`
- `agent/core/state.py`
- `agent/runtime/nodes/prompting.py`
- `agent/core/__init__.py`
- `agent/core/context_manager.py` (removed)
- `.trellis/spec/backend/database-guidelines.md`
- related tests under `tests/`


### Git Commits

| Hash | Message |
|------|---------|
| `82cff32` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: Remove root human review node

**Date**: 2026-04-07
**Task**: Remove root human review node

### Summary

删除根图 human review 收口层和 human_review_node 模块，收敛到标准 END 收口，并同步测试与设计文档。

### Main Changes

| 项目 | 说明 |
|------|------|
| Root runtime | 删除根图 `human_review` 收口层，改为 `finalize` / `deep_research` 直接连到 `END` |
| Runtime exports | 删除 `human_review_node` 模块与公开导出，同时清理 `common/config.py` 和 `main.py` 中的死配置 |
| Tests & docs | 更新 root graph / output contract / stream 去重测试，并清理 `docs/superpowers` 下的实现文档残留 |

**验证**
- `uv run pytest tests/test_root_graph_contract.py tests/test_output_contracts.py tests/test_chat_stream_report_artifact_dedup.py tests/test_agent_runtime_public_contracts.py`
- `uv run ruff check agent/runtime/__init__.py agent/runtime/nodes/__init__.py common/config.py main.py tests/test_agent_runtime_public_contracts.py tests/test_output_contracts.py`


### Git Commits

| Hash | Message |
|------|---------|
| `260870c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 10: Fix deep research pre-execution timeline labeling

**Date**: 2026-04-07
**Task**: Fix deep research pre-execution timeline labeling

### Summary

(Add summary)

### Main Changes

| Item | Description |
|------|-------------|
| Fix | Prevented Deep Research timeline from showing section/iteration metrics before section research actually starts |
| Frontend | Reclassified pre-execution `research_task_update` events (`ready`, `planned`, `dispatch`) into outline/control-plane instead of section research |
| Validation | Added regression coverage for outline-only event streams so the UI no longer shows research iterations too early |

**Updated Files**:
- `web/lib/deep-research-timeline.ts`
- `web/tests/deep-research-timeline.test.ts`

**Verification**:
- `pnpm -C web test`
- `pnpm -C web lint`


### Git Commits

| Hash | Message |
|------|---------|
| `9f0b3a5` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 11: Standardize Tool Runtime Contracts

**Date**: 2026-04-08
**Task**: Standardize Tool Runtime Contracts

### Summary

(Add summary)

### Main Changes

| Area | Description |
|------|-------------|
| Tool runtime | Introduced unified tool runtime context, tool registry, and capability/role-based policy resolution. |
| Agent path | Switched normal agent execution from keyword preselection to policy-driven resolved toolsets. |
| Deep Research | Added explicit requested/resolved tool policy snapshots into deep runtime state and agent runs. |
| MCP | Replaced custom MCP runtime path with the official adapter-backed facade and removed the old `tools/core/mcp_clients.py`. |
| Events | Unified chat/browser tool lifecycle events around a single `tool` envelope plus `tool_progress`/`tool_screenshot`. |
| Contracts | Updated `/api/agents`, `/api/tools/catalog`, generated OpenAPI TS types, and backend code-spec docs. |

**Validation**:
- `pnpm -C web lint` passed.
- `pnpm -C web test` passed.
- Targeted backend pytest suites for agent tools, MCP, event streaming, deep research runtime, and session persistence passed.
- Manual testing completed by human.
- Human confirmed local `make test` passed.

**Known Follow-up**:
- `pnpm -C web build` still reports a webpack failure in this environment and later runtime logs referenced a missing `web/.next/server/middleware-manifest.json`; the human should validate build behavior in their normal local workflow if needed.

**Updated Files**:
- `agent/infrastructure/tools/*`
- `agent/infrastructure/agents/factory.py`
- `agent/runtime/nodes/{chat,answer}.py`
- `agent/runtime/deep/{orchestration/graph.py,schema.py,support/runtime_support.py}`
- `tools/{mcp.py,core/mcp.py}`
- `main.py`
- `common/agents_store.py`
- `agent/domain/execution.py`
- `agent/application/state.py`
- `agent/core/state.py`
- `data/agents.json`
- `.trellis/spec/backend/{index.md,tool-runtime-contracts.md}`
- `web/hooks/{useChatStream.ts,useBrowserEvents.ts}`
- `web/lib/{api-types.ts,deep-research-timeline.ts,process-display.ts,session-utils.ts}`
- `web/types/{chat.ts,browser.ts}`


### Git Commits

| Hash | Message |
|------|---------|
| `043b3b0` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 12: Archive beta.9 migration task

**Date**: 2026-04-08
**Task**: Archive beta.9 migration task
**Branch**: `main`

### Summary

确认 Trellis beta.9 迁移已完成，补齐任务上下文与完成说明，并归档 04-08-migrate-to-0.4.0-beta.9 任务。

### Main Changes

| Area | Description |
|------|-------------|
| Migration review | 确认仓库已处于 `0.4.0-beta.9`，`.agents/skills/` 下不存在旧的拆分技能文件，统一 `before-dev` / `check` 已生效 |
| Task completion | 为迁移任务初始化并校验 `implement/check/debug` 上下文，补充 `prd.md` 完成说明，并将任务标记为 `completed` |
| Task archival | 将 `04-08-migrate-to-0.4.0-beta.9` 归档到 `.trellis/tasks/archive/2026-04/04-08-migrate-to-0.4.0-beta.9/` |

**Validation**:
- `trellis update --dry-run --migrate`
- `trellis update --migrate`
- `python3 ./.trellis/scripts/task.py validate ".trellis/tasks/04-08-migrate-to-0.4.0-beta.9"`
- `python3 ./.trellis/scripts/task.py list`

**Archived Task**:
- `.trellis/tasks/archive/2026-04/04-08-migrate-to-0.4.0-beta.9/task.json`


### Git Commits

| Hash | Message |
|------|---------|
| `9038363` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 13: Soften deep research validation gates

**Date**: 2026-04-08
**Task**: Soften deep research validation gates
**Branch**: `main`

### Summary

(Add summary)

### Main Changes

| Item | Description |
|------|-------------|
| Goal | 将 Deep Research 的校验流程从 hard gate 调整为 advisory-first，避免因部分信息不可得而阻断最终报告生成 |
| Backend | 调整 `agent/runtime/deep/orchestration/graph.py`，允许基于可用 section draft 生成 partial report，并将 final claim gate 改为 review-needed 提示而非 blocked |
| Frontend | 更新 deep research 状态文案和 timeline，新增 `report_partial`、`outline_partial`、`final_claim_gate_review_needed` 语义 |
| Tests | 补充回归测试，覆盖预算耗尽时仍输出部分报告，以及 claim 冲突只触发复核提示 |

**Validation**
- `uv run ruff check agent/runtime/deep/orchestration/graph.py tests/test_deepsearch_multi_agent_runtime.py`
- `uv run pytest tests/test_deepsearch_multi_agent_runtime.py tests/test_settings_quality_gates.py`
- `pnpm -C web lint`
- `pnpm -C web exec tsc -p tsconfig.json --noEmit`
- `pnpm -C web build` 仍仅返回泛化 webpack 错误，未得到可定位明细，因此未作为通过项记录

**Updated Files**
- `agent/runtime/deep/orchestration/graph.py`
- `tests/test_deepsearch_multi_agent_runtime.py`
- `web/hooks/useChatStream.ts`
- `web/lib/chat-stream-state.ts`
- `web/lib/deep-research-timeline.ts`


### Git Commits

| Hash | Message |
|------|---------|
| `045fd59` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 14: 清理 agent 模块未使用代码

**Date**: 2026-04-08
**Task**: 清理 agent 模块未使用代码
**Branch**: `main`

### Summary

删除 agent 模块中确认无消费者的 legacy runtime 代码，收窄公开导出，移除 deep research 中已废弃的 knowledge_gap 链路，并同步更新回归测试。

### Main Changes

- 清理 `agent/core/processor_config.py`、`agent/parsers/` 以及 `agent/core` 中确认无人调用的辅助逻辑，收窄 `agent.core` 公共导出。
- 删除 deep research 中未接入主流程的 `knowledge_gap` 实现、悬空状态字段和相关 facade/export。
- 更新 `tests/test_agent_runtime_public_contracts.py`、`tests/test_deepsearch_multi_agent_runtime.py`、`tests/test_deepsearch_intake_context.py` 以匹配当前真实运行链。
- 验证通过：`uv run ruff check ...`、`uv run pytest tests/test_agent_runtime_public_contracts.py`、`uv run pytest tests/test_deepsearch_multi_agent_runtime.py tests/test_deepsearch_intake_context.py`。


### Git Commits

| Hash | Message |
|------|---------|
| `7963add` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 15: Deep Research validation soft gating

**Date**: 2026-04-08
**Task**: Deep Research validation soft gating
**Branch**: `main`

### Summary

(Add summary)

### Main Changes

| Area | Description |
|------|-------------|
| Validation model | Reworked deep research section review into a quality snapshot model with `reportability`, `quality_band`, `risk_flags`, `suggested_actions`, and `needs_manual_review` while keeping compatibility fields. |
| Runtime flow | Removed quality-based hard report gates by introducing `report_ready` and `preferred_ready`, and updated supervisor / outline decisions to allow best-effort report generation when reportable content exists. |
| Reporting | Extended reporter section context with confidence, limitation, risk, and manual-review metadata so final reports can surface weaker sections explicitly. |
| Tests | Added regression coverage for low-confidence sections still producing a report and kept deep research artifact/checkpoint/export tests passing. |

**Commits**:
- `24144f8` `refactor(deep-research): decouple report gating from validation`

**Validation**:
- `uv run pytest tests/test_deepsearch_multi_agent_runtime.py`
- `uv run pytest tests/test_export_json.py`
- `uv run pytest tests/test_checkpoint_runtime_artifacts.py`
- `uv run ruff check agent/runtime/deep/schema.py agent/runtime/deep/roles/reporter.py agent/runtime/deep/artifacts/public_artifacts.py agent/runtime/deep/orchestration/graph.py agent/runtime/deep/roles/supervisor.py tests/test_deepsearch_multi_agent_runtime.py`


### Git Commits

| Hash | Message |
|------|---------|
| `24144f8` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 16: Consolidate web_search runtime

**Date**: 2026-04-08
**Task**: Consolidate web_search runtime
**Branch**: `main`

### Summary

(Add summary)

### Main Changes

| Area | Summary |
|------|---------|
| Public API | Consolidated all public API search entrypoints into `web_search` and removed legacy `fallback_search` / `search` surfaces |
| Runtime | Split shared search contracts into `tools/search/contracts.py`, moved internal orchestration to `tools/search/orchestrator.py`, and routed callers through `run_web_search(...)` |
| Deep Research | Removed the extra outer search cache layer and updated Deep Research search event payloads to report `web_search` |
| Sandbox | Removed dead Tavily-specific fallback helpers, rejected `tavily` as a fake browser engine, and normalized API fallback rendering through the unified runtime |
| Profiles/Migrations | Migrated built-in/default profiles and persisted agent tool names to `web_search` |
| Tests/Spec | Renamed search test files to the new runtime terminology and updated backend tool/logging specs to match |

**Validation**:
- `uv run pytest tests/test_web_search.py tests/test_deepsearch_web_search.py tests/test_search_cache_ttl.py tests/test_search_reliability.py tests/test_search_ranking.py tests/test_search_provider_profiles.py tests/test_search_providers_endpoint.py`
- `uv run pytest tests/test_sandbox_web_search_inputs.py ...`
- `uv run ruff check ...`


### Git Commits

| Hash | Message |
|------|---------|
| `d8a76a7` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 17: Clean common dead code

**Date**: 2026-04-08
**Task**: Clean common dead code
**Branch**: `main`

### Summary

Removed confirmed dead code from common/, deleted the unused agent_runs module, trimmed unused helper exports, cleaned runtime cache leftovers, and verified with Ruff plus targeted pytest coverage.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `653572d640ecfe5205414b5c03fbb13e13d9cc15` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 18: Clean tools dead code and remove RAG support

**Date**: 2026-04-08
**Task**: Clean tools dead code and remove RAG support
**Branch**: `main`

### Summary

Removed confirmed dead code under tools/, deleted the RAG tool and document APIs, tightened package facades, and regenerated OpenAPI TypeScript outputs.

### Main Changes

| Area | Description |
|------|-------------|
| Dead code cleanup | Removed unused browser/content-extractor and tool collection modules, plus unused crawler helpers. |
| RAG removal | Deleted `tools/rag/`, removed `rag_search` registration, removed `/api/documents/*`, and dropped RAG config fields. |
| Facades | Replaced wildcard package exports in `tools/*/__init__.py` with explicit facades. |
| API sync | Regenerated `web/lib/api-types.ts` and `sdk/typescript/src/openapi-types.ts`, then rebuilt SDK declarations. |
| Spec sync | Updated backend spec docs to remove stale RAG references. |

**Verification**:
- `uv run ruff check agent/infrastructure/tools/capabilities.py common/config.py main.py scripts/live_api_smoke.py tests/test_agent_tools.py tests/test_tools_facades.py`
- `uv run pytest tests/test_agent_tools.py tests/test_tool_catalog_api.py tests/test_tools_facades.py tests/test_browser_session_reuses_httpx_client.py tests/test_content_fetcher_render.py tests/test_content_fetcher_render_heuristics.py tests/test_computer_use_optional_dep.py`
- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`

**Note**:
- `pnpm -C web build` still failed with a generic webpack error and did not emit a detailed stack trace in this environment.


### Git Commits

| Hash | Message |
|------|---------|
| `dbce153` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 19: Refactor deep research progress display

**Date**: 2026-04-08
**Task**: Refactor deep research progress display
**Branch**: `main`

### Summary

重构 deep research 事件流显示，新增用户态进度投影，改为章节视图优先，并修复 web 构建对远程 Google Fonts 的依赖。

### Main Changes

| Area | Description |
|------|-------------|
| Process display | 新增用户态 deep research progress 投影，统一 header、章节列表和自动状态文案 |
| UX | 折叠态收敛为当前动作 + 章节进度，展开态改为章节视图优先，未开始章节聚合显示 |
| Build | 移除 `next/font/google` 依赖，改为本地字体变量，修复受限网络下 `pnpm -C web build` 失败 |

**Updated Files**:
- `web/lib/deep-research-progress.ts`
- `web/lib/process-display.ts`
- `web/hooks/useChatStream.ts`
- `web/app/layout.tsx`
- `web/app/globals.css`
- `web/tests/process-display.test.ts`
- `web/tests/deep-research-events.test.ts`


### Git Commits

| Hash | Message |
|------|---------|
| `9af4bf0` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 20: Agentic Researcher Runtime Phase 1

**Date**: 2026-04-08
**Task**: Agentic Researcher Runtime Phase 1
**Branch**: `main`

### Summary

Implemented a bounded branch-scoped agentic researcher runtime, propagated richer supervisor/section contracts, exposed structured branch artifacts through the deep runtime, added regression coverage, and updated backend tool-runtime specs.

### Main Changes

| Area | Description |
|------|-------------|
| Researcher Runtime | Added `agent/runtime/deep/researcher_runtime/` to run bounded multi-round branch research with query planning, coverage assessment, quality checks, contradiction handling, grounding evaluation, and structured branch decisions. |
| Runtime Contracts | Extended `ResearchTask`, `OutlineSection`, `SectionDraftArtifact`, and new `Branch*Artifact` contracts in `agent/runtime/deep/schema.py`. |
| Orchestration | Updated `agent/runtime/deep/orchestration/graph.py` and `agent/runtime/deep/artifacts/public_artifacts.py` to persist and expose `branch_query_rounds`, `branch_coverages`, `branch_qualities`, `branch_contradictions`, `branch_groundings`, and `branch_decisions`. |
| Supervisor | Enhanced outline sections in `agent/runtime/deep/roles/supervisor.py` to propagate source preferences, coverage targets, follow-up policy, stop policy, and time boundary metadata. |
| Prompts | Added branch gap-analysis, query-refine, counterevidence, and claim-grounding prompts in `agent/prompts/runtime_templates.py`. |
| Verification | Added/updated `tests/test_deepsearch_researcher.py`, `tests/test_deepsearch_supervisor.py`, and `tests/test_deepsearch_multi_agent_runtime.py`; validated with targeted pytest, full `uv run pytest -q` (`404 passed, 1 skipped`), and Ruff checks. |

**Notes**:
- Kept outer `reviewer`/`verifier` as hard gates while moving more coverage and grounding checks into the branch-scoped researcher runtime.
- Updated `.trellis/spec/backend/tool-runtime-contracts.md` with executable contracts for Deep Research branch runtime artifacts and public payload keys.


### Git Commits

| Hash | Message |
|------|---------|
| `462de93` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 21: Deep Research reporter 静默降噪

**Date**: 2026-04-08
**Task**: Deep Research reporter 静默降噪
**Branch**: `main`

### Summary

收紧 Deep Research reporter 的准入规则与写作输入，静默过滤低置信/冲突章节，并同步测试与 runtime contract 说明。

### Main Changes

| Area | Description |
|------|-------------|
| Reporter admission | 仅允许 `high/medium` 且无实质冲突的章节进入 final report context，低置信章节被静默过滤 |
| Prompting | 去掉 reporter 的强制长文倾向，要求只写被素材稳定支持的内容 |
| Executive summary | 优先基于 admitted `report_context` 的摘要与 findings 生成，避免正文与摘要漂移 |
| Runtime contract | 更新 `.trellis/spec/backend/tool-runtime-contracts.md`，写明 reporter 准入、`report_ready` 口径与摘要合同 |
| Regression tests | 增加 reporter prompt/summary 回归测试，以及 deep runtime 对 admitted sections 的验证 |

**Validation**:
- `uv run pytest tests/test_deepsearch_reporter.py tests/test_deepsearch_multi_agent_runtime.py -q`
- `uv run ruff check agent/runtime/deep/orchestration/graph.py agent/runtime/deep/roles/reporter.py agent/prompts/runtime_templates.py tests/test_deepsearch_reporter.py tests/test_deepsearch_multi_agent_runtime.py`
- Human verified `make test` and manual testing

**Notes**:
- 当前 `get_context.py --mode record` 仍显示旧的 current task path，但 `.trellis/tasks/` 下已无 active tasks，故本次仅记录 session，不做 task archive。


### Git Commits

| Hash | Message |
|------|---------|
| `5a2abed` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 22: 清理 agent 未使用代码并收口运行时配置

**Date**: 2026-04-10
**Task**: 清理 agent 未使用代码并收口运行时配置
**Branch**: `main`

### Summary

清理 agent 模块中的未使用与预留运行路径代码，收缩对外导出，统一 runtime configurable 解析与模型选择逻辑，补充回归测试并更新后端运行时契约规范。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7b5b8d9` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 23: 清理 deep research 未使用代码并收口 prompt 暴露面

**Date**: 2026-04-10
**Task**: 清理 deep research 未使用代码并收口 prompt 暴露面
**Branch**: `main`

### Summary

(Add summary)

### Main Changes

| Area | Description |
|------|-------------|
| Deep runtime | 基于运行覆盖率与引用面，清理 `agent/runtime/deep/` 中断链的 helper、空壳模块和包层冗余导出。 |
| Orchestration | 对齐 `graph.py` 注释与真实 LangGraph 节点注册，删除未注册且无调用点的 `_supervisor_plan_node`、`_verify_node` 等私有方法。 |
| Roles | 删除旧的 `agent/runtime/deep/roles/planner.py`，让 `ResearchSupervisor` 只保留活链使用的 `create_outline_plan` / `decide_section_action`。 |
| Prompt registry | 收缩 `agent/prompts/runtime_templates.py` 的 deep prompt 暴露面，仅保留当前 registry 真正需要对外暴露的 `deep.clarify` 和 `deep.scope`。 |
| Public contracts | 更新 `tests/test_agent_runtime_public_contracts.py` 与 `tests/test_prompt_registry.py`，锁定已移除模块、导出和 prompt id 不再暴露。 |

**Validation**
- 目标覆盖率测试集多轮通过，最终结果为 `177 passed`。
- 当前改动文件 Ruff 检查通过。
- `make test` 在 180 秒限制下超时终止，未作为通过项记录。

**Archived Task**
- `.trellis/tasks/04-10-clean-agent-unused-code-runtime-coverage` 已归档到 `archive/2026-04/`。


### Git Commits

| Hash | Message |
|------|---------|
| `9ab89bd` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 24: Reorganize agent capability architecture

**Date**: 2026-04-10
**Task**: Reorganize agent capability architecture
**Branch**: `main`

### Summary

Reorganized the agent module into capability-owned packages, split Deep Research internals into focused runtime components, migrated shared helpers to their new owners, and synced backend Trellis specs to the new architecture.

### Main Changes

| Area | Description |
|------|-------------|
| Agent package layout | Reorganized `agent/` into capability-oriented packages: `chat`, `deep_research`, `execution`, `foundation`, `prompting`, and `tooling`, and removed the legacy `application/core/domain/infrastructure/runtime/research/prompts` layout |
| Deep Research internals | Renamed Deep Research subpackages to `agents`, `branch_research`, and `engine`; split large runtime modules into focused flow/support modules; removed the old `support` bucket |
| Shared helpers | Moved domain routing into `agent/execution/intake`, moved passage/source URL helpers into `agent/foundation`, and kept top-level `tools/` and `prompts/` as infrastructure/assets rather than agent runtime buckets |
| Public contracts | Updated runtime/public entrypoints, import sites, and regression tests to enforce the new capability package boundaries and removal of legacy module paths |
| Trellis specs | Updated backend directory structure, tool runtime contracts, database guidelines, and error handling specs to match the new package ownership and runtime signatures |

**Key Validation**:
- `uv run ruff check agent tests main.py common tools`
- `uv run pytest tests/test_agents_api.py tests/test_agent_builtin_profiles.py tests/test_agents_store_migrations.py tests/test_agent_state_slices.py tests/test_tool_runtime_context.py tests/test_tool_catalog_api.py tests/test_agent_tools.py tests/test_web_search.py tests/test_search_provider_profiles.py tests/test_evidence_passages.py tests/test_evidence_passages_headings.py tests/test_source_url_utils.py tests/test_multi_model_resolve_model_name.py tests/test_chat_first_agent_nodes.py tests/test_chat_stream_tool_events.py tests/test_chat_session_persistence.py tests/test_tool_events_endpoint.py tests/test_weaver_checkpointer.py tests/test_session_store.py tests/test_agent_runtime_public_contracts.py tests/test_deepsearch_multi_agent_runtime.py tests/test_deepsearch_web_search.py tests/test_deepsearch_scope_draft_formatting.py tests/test_deepsearch_intake_context.py tests/test_deepsearch_researcher.py tests/test_deepsearch_reporter.py tests/test_deepsearch_supervisor.py` (`122 passed`)

**Archived Task**:
- `.trellis/tasks/archive/2026-04/04-10-agent-module-reorg/task.json`


### Git Commits

| Hash | Message |
|------|---------|
| `67f46fb` | (see git log) |

### Testing

- [OK] `uv run ruff check agent tests main.py common tools`
- [OK] `uv run pytest ...` for agent profile, tooling/runtime context, chat/session, checkpointer/session store, and Deep Research regression coverage (`122 passed`)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 25: Researcher RAG with Milvus and MinIO

**Date**: 2026-04-10
**Task**: Researcher RAG with Milvus and MinIO
**Branch**: `main`

### Summary

(Add summary)

### Main Changes

| Area | Description |
|------|-------------|
| Ingestion | Added knowledge file upload flow for `PDF / DOCX / MD / TXT`, storing original files in MinIO and indexing parsed chunks into Milvus. |
| Embeddings | Added dedicated `rag_embedding_*` configuration and batching support so RAG embeddings do not reuse the primary LLM provider and respect provider batch-size limits. |
| Milvus Compatibility | Reworked the Milvus adapter to introspect the live collection schema and map inserts/searches to the real primary/vector fields (`chunk_id` / `embedding`) instead of assuming local defaults. |
| Researcher Runtime | Merged RAG hits into the existing Deep Research `documents / passages / synthesis` pipeline without HTTP refetch for knowledge-file sources. |
| Library UI | Added Library upload/list/download support for knowledge files plus generated OpenAPI client type updates. |
| Spec | Added executable code-spec coverage for the knowledge-file RAG contract and a cross-layer reminder to verify live managed-service schema before assuming defaults. |

**Verification**
- `uv run pytest -q tests/test_knowledge_service.py tests/test_knowledge_api.py tests/test_deepsearch_researcher.py`
- `uv run ruff check common/config.py common/knowledge_registry.py tools/rag main.py agent/deep_research/agents/researcher.py agent/deep_research/branch_research/research_pipeline.py tests/test_knowledge_service.py tests/test_knowledge_api.py tests/test_deepsearch_researcher.py`
- `pnpm -C web lint`
- `pnpm -C web build`
- Confirmed real remote Milvus schema maps to `primary=chunk_id`, `vector=embedding`, `dim=1024`.


### Git Commits

| Hash | Message |
|------|---------|
| `2fb0b14` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 26: RAG knowledge file maintenance workflow

**Date**: 2026-04-11
**Task**: RAG knowledge file maintenance workflow
**Branch**: `main`

### Summary

(Add summary)

### Main Changes

| Feature | Description |
|---------|-------------|
| Strict dedupe | Added content-hash based duplicate upload rejection for knowledge files |
| Maintenance APIs | Added knowledge file delete and reindex endpoints backed by MinIO + Milvus cleanup/rebuild |
| Library UI | Added Reindex/Delete actions in Library knowledge items with destructive confirmation and better API error handling |
| Contracts | Updated OpenAPI-generated TypeScript types and backend tool-runtime contract for knowledge file maintenance |
| Regression coverage | Added service/API/OpenAPI tests and re-ran researcher regression coverage |

**Verification**:
- `uv run pytest tests/test_knowledge_service.py tests/test_knowledge_api.py tests/test_openapi_contract.py`
- `uv run pytest tests/test_deepsearch_researcher.py`
- `pnpm -C web lint`
- `pnpm -C web build`

**Updated Areas**:
- `tools/rag/service.py`
- `common/knowledge_registry.py`
- `main.py`
- `web/hooks/useKnowledgeFiles.ts`
- `web/components/views/Library.tsx`
- `web/components/library/KnowledgeFileItem.tsx`
- `.trellis/spec/backend/tool-runtime-contracts.md`


### Git Commits

| Hash | Message |
|------|---------|
| `c40ddc4` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 27: Add scoped knowledge search tool

**Date**: 2026-04-11
**Task**: Add scoped knowledge search tool
**Branch**: `main`

### Summary

Added owner-scoped knowledge_search for tool agents, wired the knowledge capability through runtime and knowledge APIs, updated Deep Research compatibility, and fixed streamed tool payload serialization for LangGraph Command objects.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `10385ef` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 28: RAG retrieval quality upgrade

**Date**: 2026-04-11
**Task**: RAG retrieval quality upgrade
**Branch**: `main`

### Summary

(Add summary)

### Main Changes

| Area | Description |
|------|-------------|
| Retrieval | Upgraded `KnowledgeService.search()` with internal query expansion, widened recall, chunk-level dedupe, and lightweight rerank while keeping the public `knowledge_search` contract stable. |
| Chunking | Added overlap-aware passage splitting and tightened low-signal heading-only chunk merging for knowledge ingestion. |
| Deep Research | Stopped collapsing knowledge evidence by canonicalized file URL; Deep Research now preserves chunk identity via `chunk_id` and keeps chunk locators in passages. |
| Tests | Added regression coverage for overlap offsets, reranked chunk-deduped search results, and multiple chunks from the same knowledge file remaining distinct in Deep Research. |
| Spec | Updated `.trellis/spec/backend/tool-runtime-contracts.md` with the new retrieval, chunk identity, and assertion-point contracts. |

**Verification**:
- `uv run ruff check` on touched backend/test files passed
- `uv run pytest tests/test_evidence_passages.py tests/test_knowledge_service.py tests/test_deepsearch_researcher.py` passed (`22 passed`)
- Full `pytest -q` did not complete within the harness timeout, so only targeted regression coverage is confirmed here


### Git Commits

| Hash | Message |
|------|---------|
| `e297999` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
