# agent-module-boundaries Specification

## Purpose
TBD - created by archiving change modularize-agent-runtime. Update Purpose after archive.
## Requirements
### Requirement: Agent package module boundaries are explicit
系统 MUST 为 `agent/` 包中的主要目录建立显式职责边界，并使每个目录只承载单一类型的责任；facade、shared contracts、shared primitives、runtime orchestration、deep runtime agent packages、builders、interaction helpers、research helpers、prompts/parsers MUST 有稳定且不重叠的目录归属。系统完成本次迁移后 MUST NOT 再保留 `agent.compat.*` 或 `agent.workflows.*` 这类 catch-all/compat 目录作为长期 owned modules。

#### Scenario: Assigning module ownership
- **WHEN** 系统重组 `agent/` 包内代码
- **THEN** `agent/__init__.py` 与 `agent/api.py` MUST 继续充当公开 facade
- **THEN** `agent.contracts.*` MUST 只暴露共享契约或稳定 wrapper
- **THEN** `agent.core.*` MUST 只承载 mode-agnostic shared primitives，而 MUST NOT 继续持有依赖 runtime nodes 的 graph 装配逻辑
- **THEN** `agent.runtime.*` MUST 持有 graph assembly、nodes 与 Deep Research runtime 的内部角色、编排、服务、artifact 与状态实现
- **THEN** `agent.builders.*`、`agent.interaction.*`、`agent.research.*` MUST 承载各自对应的 helper，而 MUST NOT 再借由 `agent.workflows.*` 聚合
- **THEN** 系统 MUST 删除 `agent.compat.*` 与 `agent.workflows.*` 作为长期目录边界

#### Scenario: Splitting oversized orchestration files
- **WHEN** 单个 runtime 文件同时承担节点编排、role 构建、service 协调、state 归并和事件发射等多种职责
- **THEN** 系统 MUST 将其拆分为按 loop、agents、services、artifacts、state、events 或 adapters 分离的模块
- **THEN** 拆分结果 MUST 让调用方能够从目录结构判断模块所有权，而不是继续依赖注释或历史目录命名理解边界

### Requirement: Dependency direction is constrained
系统 MUST 限制 `agent/` 包内部模块之间的依赖方向；公开 contracts 与 shared primitives MUST 不依赖 runtime、builder、interaction 或 research helper 实现，runtime 可以依赖 core/contracts 和显式 owned helper 模块，但 MUST NOT 通过 `agent.compat.*`、`agent.workflows.*` 或 `sys.modules` 兼容回退维持当前结构。

#### Scenario: Runtime depends on shared contracts
- **WHEN** runtime orchestration 需要使用事件、artifact schema、worker context、registry 或 shared helper
- **THEN** 系统 MUST 依赖 `agent.contracts.*`、runtime-owned schema 或显式 owned helper 模块
- **THEN** `agent.contracts.*` MUST NOT 继续通过 re-export 指向历史 `agent.workflows.*` 实现文件

#### Scenario: Detecting circular structure pressure
- **WHEN** 某个公开入口或 shared module 需要依赖 lazy import、compat 回调、`sys.modules` 检查或 `core -> runtime -> workflows/compat -> core` 式链路才能避免循环导入
- **THEN** 系统 MUST 将其视为边界失真的信号
- **THEN** 系统 MUST 通过移动职责、抽离共享定义或收敛公开入口来消除该压力，而不是保留新的兼容回退

### Requirement: Duplicate infrastructure concepts are unified
系统 MUST 为相同基础设施概念保留单一权威实现，并避免多个同名核心类型长期共存。

#### Scenario: Duplicate manager names exist
- **WHEN** 仓库中存在多个承担不同职责却使用相同核心名称的类型，例如多个 `ContextManager`
- **THEN** 系统 MUST 通过重命名或职责迁移消除歧义，并让名称与真实职责一致

#### Scenario: Duplicate cache implementations exist
- **WHEN** 仓库中存在多个同名 `SearchCache` 实现
- **THEN** 系统 MUST 明确其中唯一权威实现，其他实现 MUST 被移除、重命名或降级为显式 adapter

### Requirement: Deep Research compatibility layers are removed from workflow internals
系统 MUST 不再把 `agent.workflows.*` 作为 Deep Research runtime 或 shared helper 的宿主；相关职责 MUST 分别收敛到 `agent.runtime.deep.*`、`agent.builders.*`、`agent.interaction.*`、`agent.research.*` 或 `agent.contracts.*` 的明确边界内。

#### Scenario: Reused runtime helper still exists in workflow package
- **WHEN** 某个仍被当前功能使用的 Deep Research helper、tool-agent builder、domain/source helper 或 interaction helper 仍定义在 `agent.workflows.*`
- **THEN** 系统 MUST 将该 helper 迁移到其真实 owned 模块
- **THEN** 删除 `agent.workflows.*` 后，剩余调用方 MUST 不再依赖旧路径

#### Scenario: Assigning ownership after cleanup
- **WHEN** 系统重新梳理 Deep Research 相关目录职责
- **THEN** `agent.runtime.deep.*` MUST 持有 runtime orchestration 与 agent-owned 实现
- **THEN** `agent.builders.*`、`agent.interaction.*` 与 `agent.research.*` MUST 只承载各自职责范围内的 helper
- **THEN** 系统 MUST NOT 再通过单一 catch-all workflow 包承载多类 ownership

