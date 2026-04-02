## MODIFIED Requirements

### Requirement: Agent package module boundaries are explicit
系统 MUST 为 `agent/` 包中的主要目录建立显式职责边界，并使每个目录只承载单一类型的责任；facade、shared contracts、shared primitives、runtime orchestration、deep runtime internals、compatibility adapters、prompts/parsers MUST 有稳定且不重叠的目录归属。

#### Scenario: Assigning module ownership
- **WHEN** 系统重组 `agent/` 包内代码
- **THEN** `agent/__init__.py` 与 `agent/api.py` MUST 继续充当公开 facade
- **THEN** `agent.contracts.*` MUST 只暴露共享契约或稳定 wrapper
- **THEN** `agent.core.*` MUST 只承载 mode-agnostic shared primitives，而 MUST NOT 继续持有依赖 runtime nodes 的 graph 装配逻辑
- **THEN** `agent.runtime.*` MUST 持有 graph assembly、nodes 与 Deep Research runtime 的内部角色/服务实现
- **THEN** 任何临时兼容桥 MUST 位于显式 compat 位置，而不是继续隐藏在 owned modules 中

#### Scenario: Splitting oversized orchestration files
- **WHEN** 单个 runtime 文件同时承担节点编排、role 构建、service 协调、state 归并和事件发射等多种职责
- **THEN** 系统 MUST 将其拆分为按 loop、roles、services、schema、events 或 adapters 分离的模块
- **THEN** 拆分结果 MUST 让调用方能够从目录结构判断模块所有权，而不是继续依赖注释或命名约定理解边界

### Requirement: Dependency direction is constrained
系统 MUST 限制 `agent/` 包内部模块之间的依赖方向；公开 contracts 与 shared primitives MUST 不依赖 runtime/workflow 实现，runtime 可以依赖 core/contracts，但 MUST NOT 通过反向导入 legacy workflow internals 维持当前结构。

#### Scenario: Runtime depends on shared contracts
- **WHEN** runtime orchestration 需要使用事件、artifact schema、worker context 或 registry
- **THEN** 系统 MUST 依赖 `agent.contracts.*`、runtime-owned schema 或其他显式共享模块
- **THEN** `agent.contracts.*` MUST NOT 继续通过 re-export 指向 `agent.workflows.*` 实现文件

#### Scenario: Detecting circular structure pressure
- **WHEN** 某个公开入口或 shared module 需要依赖 lazy import、compat 回调或 `core -> runtime -> workflows -> core` 式链路才能避免循环导入
- **THEN** 系统 MUST 将其视为边界失真的信号
- **THEN** 系统 MUST 通过移动职责、抽离共享定义或收敛公开入口来消除该压力，而不是继续扩大兼容桥

## ADDED Requirements

### Requirement: Compatibility adapters are explicitly isolated
系统 MUST 将仍需保留的导入兼容桥放入显式 compatibility 模块，并使其生命周期与迁移计划绑定。

#### Scenario: Providing a temporary import bridge
- **WHEN** 某个内部调用方在迁移期间仍需要旧导入路径
- **THEN** 系统 MUST 只通过显式 compat 模块提供薄 re-export 或参数适配
- **THEN** 新代码 MUST NOT 再新增对旧路径的依赖

#### Scenario: Completing the migration
- **WHEN** 所有调用方已经迁移到 facade 或公开 contract/runtime 入口
- **THEN** 系统 MUST 能直接删除 compatibility adapter
- **THEN** 删除该 adapter MUST NOT 需要再次移动真正的拥有者模块
