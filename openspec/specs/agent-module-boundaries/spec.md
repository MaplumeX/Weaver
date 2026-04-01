# agent-module-boundaries Specification

## Purpose
TBD - created by archiving change modularize-agent-runtime. Update Purpose after archive.
## Requirements
### Requirement: Agent package module boundaries are explicit
系统 MUST 为 `agent/` 包中的主要目录建立显式职责边界，并使每个目录只承载单一类型的责任。

#### Scenario: Assigning module ownership
- **WHEN** 系统组织 `agent/` 包内代码
- **THEN** facade、graph 装配、runtime orchestration、prompts、parsers 和 shared contracts MUST 有明确且互不混淆的目录归属

#### Scenario: Splitting oversized orchestration files
- **WHEN** 单个模块同时承担节点编排、runtime 分发、schema 定义和事件发射等多种职责
- **THEN** 系统 MUST 将其拆分为按职责分离的子模块，而不能继续通过单文件承载所有责任

### Requirement: Dependency direction is constrained
系统 MUST 限制 `agent/` 包内部模块之间的依赖方向，避免通过循环依赖或懒加载维持结构。

#### Scenario: Runtime depends on shared contracts
- **WHEN** runtime orchestration 需要使用事件、artifact schema、worker context 或 registry
- **THEN** 系统 MUST 依赖共享契约模块，而不是依赖其他 runtime 实现文件中的内部定义

#### Scenario: Detecting circular structure pressure
- **WHEN** 某个公开入口需要依赖 lazy import 才能避免循环导入
- **THEN** 系统 MUST 将其视为模块边界失真的信号，并通过移动职责或抽离共享契约消除该依赖压力

### Requirement: Duplicate infrastructure concepts are unified
系统 MUST 为相同基础设施概念保留单一权威实现，并避免多个同名核心类型长期共存。

#### Scenario: Duplicate manager names exist
- **WHEN** 仓库中存在多个承担不同职责却使用相同核心名称的类型，例如多个 `ContextManager`
- **THEN** 系统 MUST 通过重命名或职责迁移消除歧义，并让名称与真实职责一致

#### Scenario: Duplicate cache implementations exist
- **WHEN** 仓库中存在多个同名 `SearchCache` 实现
- **THEN** 系统 MUST 明确其中唯一权威实现，其他实现 MUST 被移除、重命名或降级为显式 adapter

### Requirement: Deep Research compatibility layers are removed from workflow internals
系统 MUST 不再在 `agent.workflows.*` 中保留 Deep Research runtime 的兼容实现、镜像入口或共享 helper 宿主；相关职责 MUST 收敛到 runtime、shared contracts 和公开 facade 的明确边界内。

#### Scenario: Reused deep research helper still exists in a legacy workflow module
- **WHEN** 某个仍被当前功能使用的 Deep Research helper 仍定义在 `agent.workflows.deepsearch_*` 中
- **THEN** 系统 MUST 将该 helper 迁移到显式 shared/runtime 模块
- **THEN** 删除 legacy workflow 模块后，剩余调用方 MUST 不再依赖旧路径

#### Scenario: Assigning ownership after cleanup
- **WHEN** 系统重新梳理 Deep Research 相关目录职责
- **THEN** `agent.runtime.deep.*` MUST 持有 runtime orchestration 与内部状态实现
- **THEN** `agent.workflows.*` MUST NOT 继续承载隐藏的 Deep Research 入口或长期兼容层
