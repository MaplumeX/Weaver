## Purpose
定义 multi-agent Deep Research 的 graph 角色拓扑、职责边界与 branch-scoped tool-agent 分发契约。

## Requirements

### Requirement: Deep research role topology is explicit
系统 MUST 将 Deep Research 的 `clarify`、`scope`、`supervisor`、`researcher`、`verifier`、`reporter` 建模为显式的 graph-level 角色，并将 `researcher` 与 `verifier` 明确建模为 branch-scoped execution path，而不是仅作为单次 query worker 或纯函数检查器。

#### Scenario: Initializing the deep research subgraph
- **WHEN** 系统为一个 `multi_agent` Deep Research 请求构建执行图
- **THEN** 系统 MUST 为上述角色建立明确的节点或子图归属
- **THEN** `researcher` 与 `verifier` 的执行路径 MUST 绑定正式任务标识与 `branch_id`，而不是仅绑定临时 query

#### Scenario: Inspecting runtime topology
- **WHEN** 开发者或测试需要理解 multi-agent Deep Research 的控制流
- **THEN** 系统 MUST 能够从 graph 拓扑上辨认 clarify、scope、scope review、supervisor plan/decide、branch dispatch、verification 和 reporting 的前后关系
- **THEN** 系统 MUST NOT 依赖阅读单个大循环函数才能理解 branch 级协作结构

### Requirement: Role autonomy is bounded by ownership
系统 MUST 将 `clarify`、`scope`、`supervisor` 保持为控制平面 agents，并将 `researcher`、`verifier`、`reporter` 限定为受策略约束的执行型 agents；所有角色 MUST 只在其拥有的工具表面和状态边界内行动。

#### Scenario: Clarify or scope executes
- **WHEN** `clarify` 或 `scope` 角色被触发
- **THEN** 它们 MUST 只负责补足用户背景、目标和约束，或生成与修订 scope draft
- **THEN** 它们 MUST NOT 直接驱动 world-facing 的外部研究工具循环

#### Scenario: Supervisor executes
- **WHEN** `supervisor` 角色被触发
- **THEN** 它 MUST 只通过 fabric tools 消费 scope、task、artifact 和 verification 状态并产出调度决策
- **THEN** 它 MUST NOT 直接执行 branch 级证据采集或绕过 graph merge 改写权威状态

#### Scenario: Research, verification or reporting executes
- **WHEN** `researcher`、`verifier` 或 `reporter` 被触发
- **THEN** 它们 MUST 仅在角色允许的工具边界内执行多步动作并返回结构化结果
- **THEN** 它们 MUST NOT 直接创建不受控 graph 分支或直接改写共享权威状态

### Requirement: Researcher workers are graph-dispatched actors
系统 MUST 通过 graph-native fan-out/fan-in 机制派发 branch-scoped `researcher` actors，而不是把并发研究封装为 query worker pool。

#### Scenario: Multiple ready branch objectives are approved
- **WHEN** `supervisor` 批准执行多个 `ready` 的 branch 级研究任务
- **THEN** 系统 MUST 为每个 branch 任务创建独立的 `researcher` 执行路径
- **THEN** 每条执行路径 MUST 绑定唯一任务标识和 `branch_id`，并能够独立完成、失败或重试

#### Scenario: Worker results return to the fabric
- **WHEN** `researcher` branch agent 完成一个任务
- **THEN** 系统 MUST 将该 branch agent 的结果、follow-up request 或失败状态回流到统一的 merge 或 reduce 阶段
- **THEN** 系统 MUST 只在该阶段更新共享 artifacts、任务状态和预算计数

### Requirement: Verification remains a graph-controlled role
系统 MUST 将 branch-level 验证保持在 graph-controlled `verifier` 角色中，而不是让 `researcher` 或 `reporter` 自行宣布分支结论已满足汇总条件。

#### Scenario: Branch synthesis waits for verifier approval
- **WHEN** `researcher` 返回新的 branch synthesis 或等价分支结论
- **THEN** 系统 MUST 先将其交给 `verifier` 路径处理
- **THEN** `reporter` MUST NOT 直接把未验证的 branch synthesis 当作最终事实依据

#### Scenario: Verification fails or requests follow-up work
- **WHEN** `verifier` 发现 claim、citation、coverage 或来源可信度问题
- **THEN** `verifier` MUST 通过结构化结果将控制权交回 `supervisor`
- **THEN** `supervisor` MUST 决定重试当前 branch、触发 replan，或停止继续推进该 branch
