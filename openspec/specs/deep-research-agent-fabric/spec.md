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
系统 MUST 将 `clarify`、`scope`、`supervisor` 保持为控制平面 agents，并将 `researcher`、`verifier`、`reporter` 限定为受策略约束的执行型 agents；所有角色 MUST 只在其拥有的工具表面和状态边界内行动，并通过 `research brief`、ledger、验证 artifacts 和 outline handoff 协作。

#### Scenario: Clarify or scope executes
- **WHEN** `clarify` 或 `scope` 角色被触发
- **THEN** 它们 MUST 只负责补足用户背景、目标和约束，或生成与修订 scope draft，并把已批准结果交接到 `research brief` 生成阶段
- **THEN** 它们 MUST NOT 直接驱动 world-facing 的外部研究工具循环

#### Scenario: Supervisor executes
- **WHEN** `supervisor` 角色被触发
- **THEN** 它 MUST 只通过 fabric tools 消费 `research brief`、ledger、task、artifact 和 verification 状态并产出调度决策
- **THEN** 它 MUST NOT 直接执行 branch 级证据采集、跳过 outline gate 或绕过 graph merge 改写权威状态

#### Scenario: Research, verification or reporting executes
- **WHEN** `researcher`、`verifier` 或 `reporter` 被触发
- **THEN** 它们 MUST 仅在角色允许的工具边界内执行多步动作并返回结构化结果
- **THEN** 它们 MUST NOT 直接创建不受控 graph 分支、直接改写共享权威状态，或绕过权威 brief/outline handoff

### Requirement: Report handoff remains outline-gated
系统 MUST 将最终报告前的结构整理保持为 graph-controlled handoff，而不是让 `reporter` 直接从已验证 branch synthesis 跳到最终报告。

#### Scenario: Outline gate consumes verified branch knowledge
- **WHEN** 系统准备把研究结果交给 `reporter`
- **THEN** 系统 MUST 先基于已验证 branch synthesis、coverage matrix、contradiction registry 和 missing evidence list 生成 outline artifact
- **THEN** `reporter` MUST 只消费该 outline artifact 与其引用的已验证研究结果，而不是自行重建独立写作计划

#### Scenario: Outline gaps return to supervisor instead of bypassing the graph
- **WHEN** 结构整理阶段发现当前研究结果无法支撑目标报告结构
- **THEN** 系统 MUST 将该缺口表示为结构化 `outline_gap` coordination request
- **THEN** `reporter` MUST NOT 直接跳过该缺口进入最终成文

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

### Requirement: Verifier is a bounded adjudication role over structured contracts
系统 MUST 将 `verifier` 保持为 graph-controlled 的执行型角色，但其职责应围绕结构化 verification contracts 做裁决，而不是重新定义研究 scope 或 branch contract。

#### Scenario: Verifier executes on a branch bundle
- **WHEN** `verifier` 被触发检查某个 branch bundle
- **THEN** 它 MUST 读取该 branch 的 claims、obligations、grounding context 和 consistency context
- **THEN** 它 MUST NOT 通过自由文本 prompt 临时改写该 branch 的权威研究目标或 scope 边界

#### Scenario: Verifier requests corrective work
- **WHEN** `verifier` 认定需要补证据、反证或修订
- **THEN** 它 MUST 通过结构化 findings、issues 或受限 request 把控制权交回 `supervisor`
- **THEN** 它 MUST NOT 直接绕过 graph 创建新的 task topology

#### Scenario: Verifier tool-agent submits contract-addressable verdicts
- **WHEN** bounded verifier tool-agent 提交 claim 或 coverage 裁决
- **THEN** 它 MUST 在提交中显式引用相关的 `claim_ids`、`obligation_ids`、`consistency_result_ids` 或 `issue_ids`
- **THEN** 若它声称某个 coverage 检查通过，系统 MUST 能追溯该通过结论对应了哪些 obligations 与哪些证据引用
- **THEN** 系统 MUST NOT 接受一个未绑定具体 contracts 的 blanket `passed` 裁决并据此把整条 branch 的 obligations 一次性改写为 satisfied

### Requirement: Supervisor owns revision routing decisions
系统 MUST 让 `supervisor` 成为唯一可以决定 patch existing branch、spawn follow-up branch、spawn counterevidence branch 或 bounded stop 的控制平面角色。

#### Scenario: Corrective work is required
- **WHEN** 当前研究存在 unresolved revision issues
- **THEN** 只有 `supervisor` MAY 决定这些 issues 由哪个 branch 或哪个新任务处理
- **THEN** `researcher` 与 `verifier` MUST NOT 直接修改任务拓扑或共享权威状态

#### Scenario: Reporter consumes resolved verification state
- **WHEN** `reporter` 进入 outline 或 final report handoff
- **THEN** 它 MUST 只消费已经过 `supervisor` 决策收敛的 verification state
- **THEN** 它 MUST NOT 自行解释 unresolved issues 为“可忽略”并绕过控制平面
