## Why

当前 `agent/` 包处于重组未完成状态，`core`、`runtime`、`workflows`、`contracts` 之间存在职责重叠、兼容桥残留和反向依赖，导致公开入口重复、模块边界模糊、Deep Research runtime 难以继续拆分。现在 `multi_agent` 已经成为实际主路径，需要完成一次面向边界收敛的结构整理，避免继续在迁移中的目录布局上叠加新功能。

## What Changes

- 重新划分 `agent/` 包内目录职责，明确 facade、shared contracts、runtime orchestration、deep runtime、prompts、parsers 和 interaction helper 的归属。
- 将当前仍挂在 `agent.workflows.*` 下、但已属于 Deep Research runtime 的角色与服务迁移到更明确的 runtime-owned 模块。
- 收敛公开入口，保留稳定的 `agent` facade 与显式 contract 导入点，逐步移除 `agent.workflows.*` 中继续充当公开 API 的兼容出口。
- 拆分 oversized runtime/orchestration 文件，并把 deep runtime 私有状态继续收敛到嵌套、mode-scoped 的结构中。
- **BREAKING**: 对仍直接依赖 `agent.workflows.*` 兼容路径的内部调用方，要求迁移到新的 facade 或 contract/runtime 公开入口。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-module-boundaries`: 收紧 `agent/` 包目录职责、依赖方向与兼容层归属，完成 runtime/workflows/contracts 的边界收敛。
- `agent-public-api-surface`: 保持 `agent` facade 稳定，同时取消把 workflow internals 继续视为受支持公开 API 的做法。
- `deep-runtime-modularization`: 将 Deep Research multi-agent runtime 相关角色、服务与状态进一步模块化，并去除遗留 selector/compat 结构压力。

## Impact

- 受影响代码主要集中在 `agent/__init__.py`、`agent/api.py`、`agent/core/*`、`agent/runtime/*`、`agent/workflows/*`、`agent/contracts/*`。
- 可能影响 `common/*`、`tools/*`、`web/*` 或测试中对 `agent.workflows.*` 内部路径的直接导入。
- 不改变受支持的 `agent` facade 使用方式，但会调整内部导入路径、目录布局和模块所有权。
