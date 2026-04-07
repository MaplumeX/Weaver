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
