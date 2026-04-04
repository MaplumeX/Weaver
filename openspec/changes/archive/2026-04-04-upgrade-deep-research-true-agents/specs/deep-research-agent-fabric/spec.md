## MODIFIED Requirements

### Requirement: Deep research role topology is explicit
系统 MUST 将 Deep Research 的 `clarify`、`scope`、`supervisor` 建模为显式的 control-plane handoff agents，并将 `researcher`、`verifier`、`reporter` 建模为由 `supervisor` 调用的 execution subagents；系统 MUST 让这种拓扑在 graph 和运行时状态中都清晰可辨。

#### Scenario: Initializing the deep research subgraph
- **WHEN** 系统为一个 `multi_agent` Deep Research 请求构建执行图
- **THEN** 系统 MUST 为 `clarify`、`scope`、`supervisor` 建立明确的 control-plane 节点或子图归属
- **THEN** `researcher`、`verifier`、`reporter` MUST 被表示为 supervisor-owned execution path，而不是并列的全局控制者

#### Scenario: Inspecting runtime topology
- **WHEN** 开发者或测试需要理解 multi-agent Deep Research 的控制流
- **THEN** 系统 MUST 能够从 graph 拓扑和 runtime state 上辨认当前 `active_agent`、control-plane handoff 链以及 `supervisor` 调用的 subagent 路径
- **THEN** 系统 MUST NOT 依赖阅读单个大循环函数才能理解 control-plane owner 与 branch 级协作结构

### Requirement: Role autonomy is bounded by ownership
系统 MUST 将 `clarify`、`scope`、`supervisor` 保持为控制平面 handoff agents，并将 `researcher`、`verifier`、`reporter` 限定为受策略约束的执行型 subagents；所有角色 MUST 只在其拥有的工具表面和状态边界内行动，并通过 `research brief`、handoff payload、ledger、验证 artifacts 和 outline gate 协作。

#### Scenario: Clarify or scope executes
- **WHEN** `clarify` 或 `scope` 角色被触发
- **THEN** 它们 MUST 只负责补足用户背景、目标和约束，或生成与修订 scope draft，并通过 handoff 把控制权交给下一个 control-plane role
- **THEN** 它们 MUST NOT 直接驱动 world-facing 的外部研究工具循环

#### Scenario: Supervisor executes
- **WHEN** `supervisor` 角色被触发
- **THEN** 它 MUST 只通过 fabric tools 与结构化 handoff state 消费 `research brief`、ledger、task、artifact 和 verification 状态并产出调度决策
- **THEN** 它 MUST 成为唯一可以调用 `researcher`、`verifier`、`reporter` subagents 的全局控制平面 owner

#### Scenario: Research, verification or reporting executes
- **WHEN** `researcher`、`verifier` 或 `reporter` 被触发
- **THEN** 它们 MUST 仅在角色允许的工具边界内执行多步动作并返回结构化结果
- **THEN** 它们 MUST NOT 直接创建 control-plane handoff、直接改写共享权威状态，或绕过 `supervisor` 改写任务拓扑

### Requirement: Researcher workers are graph-dispatched actors
系统 MUST 通过 graph-native fan-out/fan-in 机制派发 branch-scoped `researcher` subagents，而不是把并发研究封装为 query worker pool 或让它们获得独立控制平面所有权。

#### Scenario: Multiple ready branch objectives are approved
- **WHEN** `supervisor` 批准执行多个 `ready` 的 branch 级研究任务
- **THEN** 系统 MUST 为每个 branch 任务创建独立的 `researcher` subagent 执行路径
- **THEN** 每条执行路径 MUST 绑定唯一任务标识和 `branch_id`，并由 `supervisor` 保持其调度所有权

#### Scenario: Worker results return to the supervisor-owned fabric
- **WHEN** `researcher` branch subagent 完成一个任务
- **THEN** 系统 MUST 将该 branch agent 的结果、follow-up request 或失败状态回流到统一的 merge 或 reduce 阶段
- **THEN** 系统 MUST 只在 `supervisor` 所拥有的 graph merge 阶段更新共享 artifacts、任务状态和预算计数

### Requirement: Report handoff remains outline-gated
系统 MUST 将最终报告前的结构整理保持为 graph-controlled gate，并要求 `supervisor` 只在 outline 已就绪时调用 `reporter` subagent，而不是让 `reporter` 自行取得全局控制权或绕过结构门控。

#### Scenario: Outline gate consumes verified branch knowledge
- **WHEN** 系统准备把研究结果交给 `reporter`
- **THEN** 系统 MUST 先基于已验证 branch synthesis、coverage matrix、contradiction registry 和 missing evidence list 生成 outline artifact
- **THEN** `supervisor` MUST 只在该 outline artifact ready 且无 blocking gaps 时调用 `reporter` subagent

#### Scenario: Outline gaps return to supervisor instead of bypassing the graph
- **WHEN** 结构整理阶段发现当前研究结果无法支撑目标报告结构
- **THEN** 系统 MUST 将该缺口表示为结构化 `outline_gap` coordination request 并把控制权保留在 `supervisor` 路径中
- **THEN** `reporter` MUST NOT 直接跳过该缺口进入最终成文

