## Purpose
定义 multi-agent Deep Research 的 graph 角色拓扑、职责边界与 researcher worker 分发契约。

## Requirements

### Requirement: Deep research role topology is explicit
系统 MUST 将 Deep Research 的 `planner`、`coordinator`、`researcher`、`verifier`、`reporter` 建模为显式的 graph-level 角色，而不是仅存在于单个 runtime 内部的隐式函数调用关系。

#### Scenario: Initializing the deep research subgraph
- **WHEN** 系统为一个 `multi_agent` Deep Research 请求构建执行图
- **THEN** 系统 MUST 为上述角色建立明确的节点或子图归属
- **THEN** 每个角色 MUST 具有稳定且可测试的输入输出契约

#### Scenario: Inspecting runtime topology
- **WHEN** 开发者或测试需要理解 multi-agent Deep Research 的控制流
- **THEN** 系统 MUST 能够从 graph 拓扑上辨认各角色之间的调用和回流关系
- **THEN** 系统 MUST NOT 依赖阅读单个大循环函数才能理解角色协作结构

### Requirement: Role autonomy is bounded by ownership
系统 MUST 将 planner、coordinator、verifier、reporter 保持为窄职责角色，只允许 researcher 作为执行层向工具自治演进。

#### Scenario: Planning or coordination executes
- **WHEN** planner、coordinator、verifier 或 reporter 被触发
- **THEN** 这些角色 MUST 只消费其职责范围内的结构化输入并产出结构化结果
- **THEN** 这些角色 MUST NOT 自主派生无限任务或绕过 graph 控制直接驱动外部工具循环

#### Scenario: Research execution requires tool autonomy
- **WHEN** 研究任务需要搜索、读取或抽取外部信息
- **THEN** 系统 MAY 将该执行能力集中在 researcher worker
- **THEN** researcher 的 fan-out、预算边界和回流路径 MUST 仍由 graph 统一控制

### Requirement: Researcher workers are graph-dispatched actors
系统 MUST 通过 graph-native fan-out/fan-in 机制派发 researcher worker，而不是把并发研究封装为单节点内部线程池。

#### Scenario: Multiple ready tasks are approved
- **WHEN** coordinator 批准执行多个 `ready` 研究任务
- **THEN** 系统 MUST 为每个任务创建独立的 researcher 执行路径
- **THEN** 每条执行路径 MUST 绑定唯一任务标识并能够独立完成、失败或重试

#### Scenario: Worker results return to the fabric
- **WHEN** researcher worker 完成一个任务
- **THEN** 系统 MUST 将该 worker 的结果回流到统一的 merge 或 reduce 阶段
- **THEN** 系统 MUST 只在该阶段更新共享 artifacts、任务状态和预算计数
