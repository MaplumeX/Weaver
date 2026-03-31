## Purpose
定义 Deep Research 在 `legacy` 与 `multi_agent` 运行时之间的选择规则，以及 multi-agent 编排循环的核心行为。

## Requirements

### Requirement: Deep Research engine selection
系统 MUST 为 Deep Research 提供可配置的运行时引擎选择，并支持在 `legacy` 与 `multi_agent` 引擎之间切换。

#### Scenario: Multi-agent engine is selected for deep research
- **WHEN** 请求被路由到 `deep` 模式且运行配置选择 `multi_agent` 引擎
- **THEN** 系统 MUST 从 `deepsearch` 入口启动一个 LangGraph 管理的 Deep Research 子图
- **THEN** 系统 MUST 保持现有 Deep Research 入口、取消语义和最终报告输出契约不变

#### Scenario: Legacy engine remains available
- **WHEN** 请求被路由到 `deep` 模式且运行配置选择 `legacy` 引擎
- **THEN** 系统 MUST 继续使用现有 legacy deepsearch runner
- **THEN** 系统 MUST 不要求前端或 API 调用方更改请求格式

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

### Requirement: Parallel researcher worker dispatch
系统 MUST 支持多个 researcher worker 并发执行研究任务，并通过 graph-native fan-out/fan-in 统一控制并发数、预算和任务状态。

#### Scenario: Multiple research tasks are ready
- **WHEN** 任务队列中存在多个 `ready` 状态的研究任务且未超过并发上限
- **THEN** 系统 MUST 通过 graph 分发机制为不同任务创建独立的 researcher 执行路径
- **THEN** 同一任务 MUST NOT 被多个 worker 同时执行

#### Scenario: Worker execution is budget-gated
- **WHEN** researcher worker 尝试领取或继续执行任务
- **THEN** 系统 MUST 在 graph 分发前检查时间、搜索次数或 token 等预算限制
- **THEN** 若预算不足，系统 MUST 阻止新的 worker fan-out 并将控制权交回 coordinator

### Requirement: Surface multi-agent runtime failures explicitly
系统 MUST 在 multi-agent Deep Research runtime 发生不可恢复错误时显式报错，而不是自动回退到 legacy deepsearch runner。

#### Scenario: Multi-agent runtime initialization fails
- **WHEN** multi-agent Deep Research 子图在启动阶段发生不可恢复错误
- **THEN** 系统 MUST 记录失败原因
- **THEN** 系统 MUST 将错误透传到上层 Deep Research 错误处理链路

#### Scenario: Core orchestration becomes invalid during execution
- **WHEN** coordinator、artifact store、graph dispatch 或任务调度核心发生不可恢复错误
- **THEN** 系统 MUST 停止继续发放新的 multi-agent 任务
- **THEN** 系统 MUST 进入有界失败路径，而不能无限重试或静默切换 engine

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
