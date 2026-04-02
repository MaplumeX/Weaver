# Agent Runtime 模块化说明

## 目标

当前 `agent/` 包的目标不是拆成多个顶层工程，而是在单包内建立稳定 facade、共享契约层、运行时装配层，以及按 ownership 划分的 builders / interaction / research helper 目录。

## 当前目录职责

### `agent/__init__.py` / `agent/api.py`

- 作为 facade，只暴露稳定公开符号。
- 外部调用方优先从这里获取能力入口，不直接依赖内部实现文件。

### `agent/contracts/*`

- 存放可被外围模块稳定依赖的共享契约。
- 当前包括事件、search cache、source registry、research contract、worker context。
- `main.py`、`common/*`、`tools/*` 访问共享概念时，应优先依赖这里，而不是 runtime / builder / research 的具体实现文件。

### `agent/builders/*`

- 存放 tool-agent / writer-agent 构建逻辑、tool registry 装配和 provider-safe middleware。
- `agent.runtime.nodes.answer`、Deep Research tool-agent session 以及其他运行时调用方通过这里获取 agent builder。

### `agent/interaction/*`

- 存放 continuation、response handler、browser context hint 等交互型 helper。
- 这些模块不负责 runtime graph 编排，只负责对话与工具调用交互流程。

### `agent/research/*`

- 存放 domain routing、quality assessment、source URL 归一化、evidence passage、query strategy、visualization、compressor 等研究辅助能力。
- runtime 可以依赖这些 helper，但它们本身不持有 graph loop 或 Deep Research runtime 状态。

### `agent/runtime/*`

- 存放运行时公开装配入口。
- `agent/runtime/nodes/*` 按职责暴露 graph node 入口。
- `agent/runtime/deep/entrypoints.py` 持有 Deep Research 的稳定公开入口。
- `agent/runtime/deep/orchestration/*` 持有 Deep Research graph loop、dispatcher、event helper 与 runtime public entrypoint。
- `agent/runtime/deep/roles/*`、`services/*`、`artifacts/*`、`support/*`、`schema.py`、`store.py` 共同承载唯一受支持的 Deep Research runtime。

### `agent/core/*`

- 保留 state、上下文窗口管理、LLM / middleware / smart routing 等 mode-agnostic 基础能力。
- `agent/core/state.py` 新增 `deep_runtime` 嵌套状态块，用于收敛 deep runtime 私有字段。

## 依赖方向

建议遵循以下方向：

1. 外围模块 `main.py`、`common/*`、`tools/*` -> `agent` facade、`agent/contracts/*` 或显式 runtime public entrypoint
2. graph 装配 -> `agent/runtime/nodes/*`、`agent/runtime/graph.py`
3. Deep Research 入口 -> `agent/runtime/deep/entrypoints.py` / `agent/runtime/deep/orchestration/*`
4. 具体 runtime 实现 -> `agent/runtime/deep/roles/*`、`services/*`、`artifacts/*`、`support/*`、`schema.py`、`store.py`
5. builders / interaction / research helper -> 各自 owning 目录，不再通过 catch-all 目录聚合

反向依赖应避免：

- `tools/*` / `common/*` 直接 import runtime / builder / research 的内部实现文件
- `agent/core/*` 反向依赖 `agent/runtime/*`
- 通过 `sys.modules`、隐式 re-export 或 shim 维持历史目录兼容

## 共享概念收敛

### Context 管理

- `agent/core/context_manager.py` 中的上下文窗口管理器统一命名为 `ContextWindowManager`
- `agent/core/context.py` 中的 worker/sub-agent 上下文存储统一命名为 `WorkerContextStore`
- 历史 `ContextManager` 名称仍保留兼容别名，便于迁移期平滑过渡

### Search Cache

- 权威实现通过 `agent.contracts.search_cache` 暴露

### Deep Runtime State

- 唯一权威状态为 `state["deep_runtime"]`
- 其中包含：
  - `engine`
  - `task_queue`
  - `artifact_store`
  - `runtime_state`
  - `agent_runs`

## 当前迁移状态

以下边界已经稳定下来：

- `agent/contracts/*` 已成为外围共享契约入口
- `agent/builders/*`、`agent/interaction/*`、`agent/research/*` 已成为各自职责的 owning 目录
- `agent/runtime/*` 已成为 runtime 公开装配入口
- `agent/runtime/graph.py` 持有 graph 与 checkpointer 装配入口
- Deep Research 已收敛到单一 `multi_agent` runtime
- `agent/runtime/nodes/*` 已承载 route、answer、planning、review、deepsearch 的真实节点实现
- `agent/runtime/deep/entrypoints.py`、`config.py`、`artifacts/public_artifacts.py`、`shared.py` 已成为 Deep Research 的公开入口和共享契约层
- `agent/runtime/deep/orchestration/*`、`schema.py`、`store.py`、`support/*`、`roles/*`、`services/*` 已承载 multi-agent runtime 的真实实现
- 旧的 compat 目录、workflow 聚合目录与 graph shim 已删除

当前阶段已经完成“模块边界显式化”“外围依赖迁移”“deep_runtime 状态收口”和 legacy shim 清理。

## 开发约定

- 新增外围依赖时，默认先看 `agent/__init__.py`、`agent/api.py`、`agent/contracts/*`
- 新增 graph node 公开入口时，放到 `agent/runtime/nodes/*`
- 新增 deep runtime facade 或 runtime entrypoint 时，放到 `agent/runtime/deep/*`
- 不要再把 runtime / builder / interaction / research 的具体实现文件扩散为新的外部依赖约定

## 后续建议

- 继续细化 `agent/runtime/deep/orchestration/graph.py` 内部职责，把可独立演进的 worker 执行与结果归并逻辑进一步拆到 supporting modules
- 保持 `agent` facade、`agent.api`、`agent.contracts.*` 与显式 runtime public entrypoint 的公开面稳定
