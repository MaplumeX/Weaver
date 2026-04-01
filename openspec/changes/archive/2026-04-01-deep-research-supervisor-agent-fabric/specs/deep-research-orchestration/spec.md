## REMOVED Requirements

### Requirement: Coordinator-controlled research loop
**Reason**: Deep Research 的控制平面将从 `planner + coordinator` 双角色迁移为单一 `supervisor agent`，以统一计划、调度、replan 和 stop 决策。
**Migration**: 使用 `supervisor` 驱动的计划和调度节点替换原有 coordinator/planner 控制回路；保留 clarify/scope 前置门控与 graph 级预算、merge、checkpoint 边界。

### Requirement: Parallel researcher worker dispatch
**Reason**: 研究执行不再建模为通用 worker，而是建模为 branch-scoped researcher tool-agent runs。
**Migration**: 通过 `supervisor` 批准和 graph fan-out 派发 branch `researcher` agents，并继续由 graph 统一控制预算和 merge。

## ADDED Requirements

### Requirement: Supervisor-controlled research loop
系统 MUST 由 `supervisor` 统一控制 multi-agent Deep Research 的研究循环，并通过显式 graph 转移驱动 clarify、scope、scope review、branch dispatch、验证、汇总和结束阶段。

#### Scenario: Supervisor waits for approved scope before dispatch
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** 系统 MUST 先完成 clarify/scoping 和 scope review
- **THEN** `supervisor` MUST 只在 scope draft 被用户批准后，才将 branch 级任务写入可调度队列并分配唯一任务标识

#### Scenario: Supervisor replans from verifier feedback
- **WHEN** `verifier` 产出了新的 claim/citation 问题、coverage gap 或 follow-up 请求且预算仍允许继续研究
- **THEN** `supervisor` MUST 基于当前证据、scope 和验证结果决定是否触发 replan
- **THEN** 系统 MUST 只将被 `supervisor` 批准的新 branch 任务加入任务队列

#### Scenario: Supervisor stops after verified coverage is sufficient
- **WHEN** `supervisor` 判断已验证的 branch 结论足以支撑最终报告，或剩余预算不足以继续研究
- **THEN** 系统 MUST 停止发放新的 `researcher` 任务
- **THEN** 系统 MUST 只在验证和覆盖条件满足后转入最终汇总与完成阶段

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

## MODIFIED Requirements

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
