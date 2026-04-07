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
