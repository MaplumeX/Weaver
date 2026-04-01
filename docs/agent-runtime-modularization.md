# Agent Runtime 模块化说明

## 目标

`modularize-agent-runtime` 变更在不改变现有对外能力语义的前提下，收敛 `agent/` 包内部的模块边界。重点不是把 `agent/` 拆成多个顶层工程，而是在单包内建立稳定公开入口、共享契约层和运行时装配层。

## 当前目录职责

### `agent/__init__.py` / `agent/api.py`

- 作为 facade，只暴露稳定公开符号。
- 外部调用方优先从这里获取能力入口，不直接依赖内部实现文件。

### `agent/contracts/*`

- 存放可被外围模块稳定依赖的共享契约。
- 当前包括事件、search cache、source registry、research contract、worker context。
- `main.py`、`common/*`、`tools/*` 访问共享概念时，应优先依赖这里，而不是 `agent.workflows.*` 或 `agent.core.*` 的内部位置。

### `agent/runtime/*`

- 存放运行时公开装配入口。
- `agent/runtime/nodes/*` 按职责暴露 graph node 入口。
- `agent/runtime/deep/entrypoints.py` 持有 Deep Research 的稳定公开入口。
- `agent/runtime/deep/multi_agent/*` 承载唯一受支持的 Deep Research runtime，包括 schema、store、dispatcher、event helper、public artifacts 适配和 LangGraph entrypoint。

### `agent/core/*`

- 保留 graph、state、上下文窗口管理等基础能力。
- `agent/core/graph.py` 已切换为从 `agent.runtime.nodes` 装配 graph。
- `agent/core/state.py` 新增 `deep_runtime` 嵌套状态块，用于收敛 deep runtime 私有字段。

### `agent/workflows/*`

- 仍然承载较多历史实现。
- 在本次变更中，它逐步退回为内部实现层，不再建议被外围模块直接依赖。

## 依赖方向

建议遵循以下方向：

1. 外围模块 `main.py`、`common/*`、`tools/*` -> `agent` facade 或 `agent/contracts/*`
2. graph 装配 -> `agent/runtime/nodes/*`
3. deep runtime 入口 -> `agent/runtime/deep/entrypoints.py`
4. 具体 runtime 实现 -> `agent/runtime/deep/multi_agent/*`

反向依赖应避免：

- `tools/*` 直接 import `agent.workflows.*`
- `common/*` 直接 import `agent.workflows.*`
- 将 `agent/core/*` 中的内部实现路径当作稳定 API 暴露给外围

## 共享概念收敛

### Context 管理

- `agent/core/context_manager.py` 中的上下文窗口管理器统一命名为 `ContextWindowManager`
- `agent/core/context.py` 中的 worker/sub-agent 上下文存储统一命名为 `WorkerContextStore`
- 历史 `ContextManager` 名称仍保留兼容别名，便于迁移期平滑过渡

### Search Cache

- 权威实现通过 `agent.contracts.search_cache` 暴露
- `agent/workflows/search_cache.py` 只保留显式 adapter，避免继续出现第二个核心 `SearchCache` 概念

### Deep Runtime State

- 推荐读取 `state["deep_runtime"]`
- 其中包含：
  - `engine`
  - `task_queue`
  - `artifact_store`
  - `runtime_state`
  - `agent_runs`
- 旧的 `deepsearch_*` 平铺字段仍保留过渡兼容，后续可在兼容窗口结束后继续删除

## 当前迁移状态

以下边界已经稳定下来：

- `agent/contracts/*` 已成为外围共享契约入口
- `agent/runtime/*` 已成为 runtime 公开装配入口
- `agent/core/graph.py` 已从 `agent.runtime.nodes` 装配
- Deep Research 已收敛到单一 `multi_agent` runtime
- `agent/runtime/nodes/*` 已承载 route、answer、planning、review、deepsearch 的真实节点实现
- `agent/workflows/nodes.py` 已降级为兼容 facade，不再持有节点实现本体
- `agent/runtime/deep/entrypoints.py`、`config.py`、`public_artifacts.py`、`shared.py` 已成为 Deep Research 的公开入口和共享契约层
- `agent/runtime/deep/multi_agent/schema.py`、`store.py`、`support.py`、`dispatcher.py`、`events.py`、`runtime.py`、`graph.py` 已承载 multi-agent runtime 的真实实现
- legacy deep runtime、selector 和 `agent.workflows.deepsearch_*` compatibility facade 已删除

当前阶段已经完成“模块边界显式化”“外围依赖迁移”和 legacy Deep Research 清理。

## 开发约定

- 新增外围依赖时，默认先看 `agent/__init__.py`、`agent/api.py`、`agent/contracts/*`
- 新增 graph node 公开入口时，放到 `agent/runtime/nodes/*`
- 新增 deep runtime facade 或 runtime entrypoint 时，放到 `agent/runtime/deep/*`
- 不要再把 `agent.workflows.*` 的具体文件路径扩散为新的外部依赖约定

## 后续建议

- 将 `agent/workflows/nodes.py` 中的节点实现逐步搬入 `agent/runtime/nodes/*` 对应模块
- 继续收敛旧 `deepsearch_*` 平铺状态字段，只保留 `state["deep_runtime"]` 作为权威内部快照
