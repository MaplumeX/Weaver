## MODIFIED Requirements

### Requirement: Deep research role topology is explicit
系统 MUST 将 Deep Research 的 `clarify`、`scope`、`planner`、`coordinator`、`researcher`、`verifier`、`reporter` 建模为显式的 graph-level 角色，并将 `researcher` 明确建模为 branch-scoped execution path，而不是仅作为单次 query worker。

#### Scenario: Initializing the deep research subgraph
- **WHEN** 系统为一个 `multi_agent` Deep Research 请求构建执行图
- **THEN** 系统 MUST 为上述角色建立明确的节点或子图归属
- **THEN** researcher 的执行路径 MUST 绑定唯一 `branch_id` 与正式研究任务，而不是仅绑定临时 query

#### Scenario: Inspecting runtime topology
- **WHEN** 开发者或测试需要理解 multi-agent Deep Research 的控制流
- **THEN** 系统 MUST 能够从 graph 拓扑上辨认 intake/scoping、branch planning、branch dispatch、verification 和 reporting 的前后关系
- **THEN** 系统 MUST NOT 依赖阅读单个大循环函数才能理解 branch 级协作结构

### Requirement: Role autonomy is bounded by ownership
系统 MUST 将 clarify、scope、planner、coordinator、verifier、reporter 保持为窄职责角色，只允许 researcher 作为执行层向工具自治演进。

#### Scenario: Clarify or scope executes
- **WHEN** `clarify` 或 `scope` 角色被触发
- **THEN** clarify MUST 只负责补足用户背景、目标和约束信息
- **THEN** scope MUST 只负责生成或重写 scope draft，而 MUST NOT 直接生成 branch 任务或驱动外部工具循环

#### Scenario: Planning, coordination or verification executes
- **WHEN** planner、coordinator、verifier 或 reporter 被触发
- **THEN** 这些角色 MUST 只消费其职责范围内的结构化输入并产出结构化结果
- **THEN** 这些角色 MUST NOT 自主派生无限任务或绕过 graph 控制直接驱动外部工具循环

#### Scenario: Research execution requires tool autonomy
- **WHEN** 某个 branch objective 需要搜索、读取或抽取外部信息
- **THEN** 系统 MAY 将该执行能力集中在 researcher branch agent
- **THEN** researcher 的 fan-out、预算边界和回流路径 MUST 仍由 graph 统一控制

### Requirement: Researcher workers are graph-dispatched actors
系统 MUST 通过 graph-native fan-out/fan-in 机制派发 branch-scoped researcher actors，而不是把并发研究封装为 query worker pool。

#### Scenario: Multiple ready branch objectives are approved
- **WHEN** coordinator 批准执行多个 `ready` 的 branch 级研究任务
- **THEN** 系统 MUST 为每个 branch 任务创建独立的 researcher 执行路径
- **THEN** 每条执行路径 MUST 绑定唯一任务标识和 `branch_id`，并能够独立完成、失败或重试

#### Scenario: Worker results return to the fabric
- **WHEN** researcher branch agent 完成一个任务
- **THEN** 系统 MUST 将该 branch agent 的结果回流到统一的 merge 或 reduce 阶段
- **THEN** 系统 MUST 只在该阶段更新共享 artifacts、任务状态和预算计数

## ADDED Requirements

### Requirement: Verification remains a graph-controlled role
系统 MUST 将 branch-level 验证保持在 graph-controlled verifier 角色中，而不是让 researcher 自行宣布分支结论已满足汇总条件。

#### Scenario: Branch synthesis waits for verifier approval
- **WHEN** researcher 返回新的 branch synthesis 或等价分支结论
- **THEN** 系统 MUST 先将其交给 verifier 流水线处理
- **THEN** reporter MUST NOT 直接把未验证的 branch synthesis 当作最终事实依据

#### Scenario: Verification fails or requests follow-up work
- **WHEN** verifier 发现 claim、citation 或 coverage 问题
- **THEN** verifier MUST 通过结构化结果将控制权交回 coordinator
- **THEN** coordinator MUST 决定重试当前 branch、触发 replan，或停止继续推进该 branch
