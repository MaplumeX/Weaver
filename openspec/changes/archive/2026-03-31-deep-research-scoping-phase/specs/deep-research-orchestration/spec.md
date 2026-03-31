## MODIFIED Requirements

### Requirement: Coordinator-controlled research loop
系统 MUST 由 coordinator 统一控制 multi-agent Deep Research 的研究循环，并通过显式 graph 转移驱动 intake、范围确认、计划、研究、校验、汇总和结束阶段。

#### Scenario: Coordinator initializes intake before research plan
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** coordinator MUST 先触发 intake/scoping 阶段，而不是直接触发 planner 生成初始研究任务集合
- **THEN** 系统 MUST 只在 scope draft 被用户批准后，才将 planner 产出的任务写入可调度的任务队列并分配唯一任务标识

#### Scenario: Coordinator triggers replan from gaps
- **WHEN** verifier 或 researcher 产出了新的 `KnowledgeGap` 且预算仍允许继续研究
- **THEN** coordinator MUST 基于当前证据和缺口决定是否触发 replan
- **THEN** 系统 MUST 只将被批准的新任务加入任务队列

#### Scenario: Coordinator terminates the loop
- **WHEN** coordinator 判断覆盖度已满足完成条件或剩余预算不足以继续研究
- **THEN** 系统 MUST 停止发放新的 researcher 任务
- **THEN** 系统 MUST 转入最终汇总与完成阶段

### Requirement: Multi-agent graph execution is checkpoint-aware
系统 MUST 让 multi-agent Deep Research 的权威执行状态落在 LangGraph 可 checkpoint 和恢复的边界上，而不是只存在于进程内循环。

#### Scenario: Deep research pauses or resumes
- **WHEN** multi-agent Deep Research 因 interrupt、暂停或进程恢复而需要继续执行
- **THEN** 系统 MUST 能从已持久化的 graph 状态恢复任务队列、artifacts 和当前阶段
- **THEN** 系统 MUST 不要求重新从头执行整个研究流程

#### Scenario: Scope review resumes after checkpoint
- **WHEN** Deep Research 在 scope 审阅阶段因 interrupt 或会话恢复而继续执行
- **THEN** 系统 MUST 恢复当前 scope draft、修订次数、用户反馈历史和下一步动作
- **THEN** 系统 MUST 不跳过用户批准而直接进入 planner

#### Scenario: Worker fan-out resumes after checkpoint
- **WHEN** 一个包含 researcher fan-out 的阶段在 checkpoint 之后恢复
- **THEN** 系统 MUST 依据已持久化任务状态决定哪些任务需要继续、跳过或重试
- **THEN** 系统 MUST 不因恢复而把已完成任务重复视为新的 ready 任务
