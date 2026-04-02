## Why

当前 `agent/` 包已经完成了第一轮模块显式化，但仍保留 `agent.compat`、`agent.core.graph` 这类过渡 shim，以及 `agent.workflows.*` 中混杂的公开转发、legacy adapter 和 runtime 反向依赖。继续在这个半迁移状态上演进，会把兼容语义固化成长期结构，抬高后续按 agent 角色和 runtime ownership 继续整理的成本。

## What Changes

- 以 hard cut 方式完成 `agent/` 包重组，删除 `agent.compat` 目录及其对应的运行时回退逻辑。
- 重新划分 `agent/` 顶层目录职责，使 facade、contracts、core、runtime、builders、interaction、research helpers、prompts、parsers 各自拥有清晰边界。
- 将当前仍由 `agent.workflows.*` 承载的 runtime-owned helper、tool-agent builder 和 shared helper 迁移到新的 owned 位置，不再保留 workflow-internal compat 出口。
- 按 Deep Research 角色组织 runtime 子域，把 clarify、scope、supervisor、researcher、reporter 等角色与 orchestration、services、artifacts、state 分离。
- 收敛公开入口，只保留 `agent` facade、`agent.api`、`agent.contracts.*` 与显式 runtime public entrypoints。
- 拆分 oversized runtime/orchestration 文件，尤其是 multi-agent deep runtime 的主图与辅助逻辑。
- **BREAKING**: 移除 `agent.compat.*`、`agent.core.graph` shim、以及所有仍把 `agent.workflows.*` 视为兼容公开入口的导入路径；调用方必须迁移到新的 facade、contract、runtime 或 role-owned 模块。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-module-boundaries`: 将 `agent/` 包从“兼容迁移态”收口到明确 ownership 布局，并要求兼容层可被完整删除。
- `agent-public-api-surface`: 明确移除 workflow internals 与 compat 路径作为受支持 API 的地位，只保留 facade、contracts 与显式 runtime 入口。
- `deep-runtime-modularization`: 继续拆分 Deep Research multi-agent runtime，使角色、编排、services、artifacts 与 shared helpers 按职责归位。

## Impact

- 主要影响 `agent/__init__.py`、`agent/api.py`、`agent/core/*`、`agent/runtime/*`、`agent/workflows/*`、`agent/contracts/*`、`agent/compat/*`。
- 将影响 examples、tests、`main.py`、`common/*`、`tools/*` 中对旧导入路径、旧 patch 点或旧兼容行为的依赖。
- 不引入新的产品能力，但会一次性调整内部导入路径、测试 patch 点、目录布局和部分 runtime 公开模块位置。
