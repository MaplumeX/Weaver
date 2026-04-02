## Purpose
定义 Deep Research 收敛到单一 `multi_agent` 运行时后的入口约束与编排行为。
## Requirements
### Requirement: Deep Research engine selection
系统 MUST 将需要真正深入研究的 `deep` 请求固定到单一 canonical Deep Research runtime，并在进入 runtime 前允许执行一次显式 preflight 判断；若该判断认定请求属于简单问题，则系统 MUST 将其转交 `agent` 模式处理，而 MUST NOT 路由到 `direct`、`web`、legacy runtime、`coordinator` 分支或任何 tree/linear 旧路径。

#### Scenario: Deep research enters the only supported runtime
- **WHEN** 请求被路由到 `deep` 模式且 preflight 判断该请求需要真实的深度研究
- **THEN** 系统 MUST 直接启动 canonical Deep Research 子图
- **THEN** 系统 MUST NOT 通过 `deepsearch` 时代的兼容入口、兼容节点名称或兼容 engine alias 启动运行时

#### Scenario: Simple deep request is downgraded to agent
- **WHEN** 请求被路由到 `deep` 模式且 preflight 判断该请求可由简单路径满足
- **THEN** 系统 MUST 将该请求转交 `agent` 执行路径处理
- **THEN** 系统 MUST NOT 调用 `direct_answer_node`、`web` 专用路径、legacy deep runtime 或 outer hierarchical Deep Research 分支

#### Scenario: Obsolete legacy runtime inputs are rejected
- **WHEN** 调用方仍传入 `legacy` engine、`deepsearch_mode`、tree/linear 选择项或其他 deepsearch 时代兼容输入
- **THEN** 系统 MUST 不再路由到任何兼容 runtime，也 MUST NOT 静默迁移这些输入
- **THEN** 系统 MUST 以显式校验错误或配置错误暴露该输入已废弃

### Requirement: Supervisor-controlled research loop
系统 MUST 由 `supervisor` 独占 multi-agent Deep Research 的规划与循环控制语义，并通过显式 graph 转移驱动 clarify、scope、scope review、branch dispatch、验证、汇总和结束阶段；系统 MUST NOT 再公开或保留独立 `coordinator` 角色、outer hierarchical path 或等价兼容控制面。

#### Scenario: Supervisor waits for approved scope before dispatch
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** 系统 MUST 先完成 clarify/scoping 和 scope review
- **THEN** `supervisor` MUST 只在 scope draft 被用户批准后，才将 branch 级任务写入可调度队列并分配唯一任务标识

#### Scenario: Supervisor replans from verifier feedback
- **WHEN** `verifier` 产出了新的 claim/citation 问题、coverage gap 或 follow-up 请求且预算仍允许继续研究
- **THEN** `supervisor` MUST 基于当前证据、scope 和验证结果决定是否触发 replan
- **THEN** 系统 MUST 只将被 `supervisor` 批准的新 branch 任务加入任务队列

#### Scenario: Supervisor owns orchestration decisions directly
- **WHEN** runtime 需要决定继续研究、触发 replan、重试 branch、开始汇总或停止
- **THEN** 系统 MUST 由 `supervisor` 直接产出这些决策
- **THEN** 系统 MUST NOT 再暴露 `coordinator` 角色、`coordinator_action` 状态或 outer hierarchical 决策分支

### Requirement: Parallel branch tool-agent dispatch
系统 MUST 支持多个 `researcher` branch tool agent 并发执行研究任务，并通过 graph-native fan-out/fan-in 统一控制并发数、预算和任务状态。

#### Scenario: Multiple branch tasks are ready
- **WHEN** 任务队列中存在多个 `ready` 状态的 branch 级研究任务且未超过并发上限
- **THEN** 系统 MUST 通过 graph 分发机制为不同任务创建独立的 `researcher` branch execution path
- **THEN** 同一 branch 任务 MUST NOT 被多个 agent 同时执行

#### Scenario: Branch execution is budget-gated
- **WHEN** `researcher` branch agent 尝试领取或继续执行任务
- **THEN** 系统 MUST 在 graph 分发前检查时间、搜索次数、token、步骤数或其他预算限制
- **THEN** 若预算不足，系统 MUST 阻止新的 branch fan-out 并将控制权交回 `supervisor`

### Requirement: Surface multi-agent runtime failures explicitly
系统 MUST 在 multi-agent Deep Research runtime 发生不可恢复错误时显式报错，而不是自动回退到 legacy deepsearch runner。

#### Scenario: Multi-agent runtime initialization fails
- **WHEN** multi-agent Deep Research 子图在启动阶段发生不可恢复错误
- **THEN** 系统 MUST 记录失败原因
- **THEN** 系统 MUST 将错误透传到上层 Deep Research 错误处理链路

#### Scenario: Core orchestration becomes invalid during execution
- **WHEN** `supervisor`、artifact store、graph dispatch 或任务调度核心发生不可恢复错误
- **THEN** 系统 MUST 停止继续发放新的 multi-agent 任务
- **THEN** 系统 MUST 进入有界失败路径，而不能无限重试或静默切换 engine

### Requirement: Multi-agent graph execution is checkpoint-aware
系统 MUST 让 multi-agent Deep Research 的权威执行状态落在 LangGraph 可 checkpoint 和恢复的边界上，而不是只存在于进程内循环，并在恢复后继续向调用方暴露 branch 级执行进度与 `supervisor` 决策上下文。

#### Scenario: Deep research pauses or resumes
- **WHEN** multi-agent Deep Research 因 interrupt、暂停或进程恢复而需要继续执行
- **THEN** 系统 MUST 能从已持久化的 graph 状态恢复任务队列、artifacts、当前阶段和最近的 `supervisor` 决策上下文
- **THEN** 系统 MUST 不要求重新从头执行整个研究流程

#### Scenario: Branch execution resumes after checkpoint
- **WHEN** 某个 branch `researcher` agent 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 恢复该 branch 任务的当前阶段、已提交的中间产物、follow-up request 和重试上下文
- **THEN** 系统 MUST 不把该恢复错误地表示为一个全新的无关 branch

#### Scenario: Validation stage resumes after checkpoint
- **WHEN** verifier challenge、claim/citation 检查或 coverage/gap 检查在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 保留稳定的 `branch_id`、任务标识、验证阶段上下文和待处理 supervisor 决策输入
- **THEN** `supervisor` MUST 能基于恢复后的验证结果继续做 replan、dispatch 或 report 决策

#### Scenario: Resumed execution remains externally observable
- **WHEN** 调用方在 scope review 或其他 checkpoint 之后继续执行 Deep Research
- **THEN** 系统 MUST 支持通过可观察的继续执行路径暴露恢复后的 supervisor、research、verify 和 report 阶段进度
- **THEN** 调用方 MUST 不需要等待隐藏的后台完成或重新发起全新研究请求，才能看到恢复后的执行过程

