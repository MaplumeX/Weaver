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

(Add summary)

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

- [OK] (Add test results)

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
