## MODIFIED Requirements

### Requirement: Coordinator-controlled research loop
系统 MUST 由 coordinator 统一控制 multi-agent Deep Research 的研究循环，并通过显式 graph 转移驱动 intake、范围确认、branch planning、branch research、验证、汇总和结束阶段。

#### Scenario: Coordinator initializes intake before branch planning
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** coordinator MUST 先触发 intake/scoping 阶段，而不是直接触发 planner 生成正式研究任务集合
- **THEN** 系统 MUST 只在 scope draft 被用户批准后，才将 planner 产出的 branch 级任务写入可调度队列并分配唯一任务标识

#### Scenario: Coordinator triggers replan from validation feedback
- **WHEN** verifier 产出了新的 claim/citation 问题、coverage gap 或 rejected branch synthesis 且预算仍允许继续研究
- **THEN** coordinator MUST 基于当前证据和验证结果决定是否触发 replan
- **THEN** 系统 MUST 只将被批准的新 branch 任务加入任务队列

#### Scenario: Coordinator terminates the loop after validated coverage is sufficient
- **WHEN** coordinator 判断已验证的 branch 结论足以支撑最终报告，或剩余预算不足以继续研究
- **THEN** 系统 MUST 停止发放新的 researcher 任务
- **THEN** 系统 MUST 只在验证和覆盖条件满足后转入最终汇总与完成阶段

### Requirement: Parallel researcher worker dispatch
系统 MUST 支持多个 researcher branch agent 并发执行研究任务，并通过 graph-native fan-out/fan-in 统一控制并发数、预算和任务状态。

#### Scenario: Multiple branch tasks are ready
- **WHEN** 任务队列中存在多个 `ready` 状态的 branch 级研究任务且未超过并发上限
- **THEN** 系统 MUST 通过 graph 分发机制为不同任务创建独立的 researcher branch execution path
- **THEN** 同一 branch 任务 MUST NOT 被多个 worker 同时执行

#### Scenario: Branch execution is budget-gated
- **WHEN** researcher branch agent 尝试领取或继续执行任务
- **THEN** 系统 MUST 在 graph 分发前检查时间、搜索次数、token 或其他预算限制
- **THEN** 若预算不足，系统 MUST 阻止新的 branch fan-out 并将控制权交回 coordinator

### Requirement: Multi-agent graph execution is checkpoint-aware
系统 MUST 让 multi-agent Deep Research 的权威执行状态落在 LangGraph 可 checkpoint 和恢复的边界上，而不是只存在于进程内循环，并在恢复后继续向调用方暴露 branch 级执行进度。

#### Scenario: Deep research pauses or resumes
- **WHEN** multi-agent Deep Research 因 interrupt、暂停或进程恢复而需要继续执行
- **THEN** 系统 MUST 能从已持久化的 graph 状态恢复任务队列、artifacts 和当前阶段
- **THEN** 系统 MUST 不要求重新从头执行整个研究流程

#### Scenario: Branch execution resumes after checkpoint
- **WHEN** 某个 branch researcher agent 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 恢复该 branch 任务的当前阶段、已提交的中间产物和重试上下文
- **THEN** 系统 MUST 不把该恢复错误地表示为一个全新的无关 branch

#### Scenario: Validation stage resumes after checkpoint
- **WHEN** claim/citation 检查或 coverage/gap 检查在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 保留稳定的 `branch_id`、任务标识和验证阶段上下文
- **THEN** coordinator MUST 能基于恢复后的验证结果继续做 replan、dispatch 或 report 决策
