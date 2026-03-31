## MODIFIED Requirements

### Requirement: Agent lifecycle events
系统 MUST 为 multi-agent Deep Research runtime 发出可消费的 agent 生命周期事件，并为每次 graph-level 执行提供稳定的关联标识。

#### Scenario: Agent starts execution
- **WHEN** clarify、scope、coordinator、planner、researcher、verifier 或 reporter 开始执行一个任务或阶段
- **THEN** 系统 MUST 发出包含 agent 标识、角色、关联任务或阶段信息的事件
- **THEN** 事件 MUST 具备足以关联 graph run、node、branch 或 attempt 的字段

#### Scenario: Agent completes execution
- **WHEN** 任一 Deep Research agent 完成、失败或被取消
- **THEN** 系统 MUST 发出对应状态事件
- **THEN** 事件 MUST 包含足够的关联字段以让前端将其映射到同一任务流

### Requirement: Task and decision progress events
系统 MUST 暴露任务队列、scope 草案流转和 coordinator 决策的关键进度事件，并使其能够表达 graph fan-out/fan-in 和用户审阅状态。

#### Scenario: Scope draft is produced or revised
- **WHEN** scope agent 生成新的 scope draft，或基于用户反馈重写 scope draft
- **THEN** 系统 MUST 发出可标识当前草案版本和阶段上下文的进度事件
- **THEN** 前端 MUST 无需解析完整内部状态对象即可判断该草案处于待审阅、待修订还是已批准状态

#### Scenario: Task queue changes
- **WHEN** 研究任务被创建、领取、阻塞、完成、回退或重试
- **THEN** 系统 MUST 发出任务状态更新事件
- **THEN** 事件 MUST 能标识该任务属于哪个 graph run、研究线程和父任务

#### Scenario: Coordinator or scope review makes a decision
- **WHEN** coordinator 决定继续研究、触发 replan、开始汇总、结束，或 scope 审阅阶段收到批准/修订决定
- **THEN** 系统 MUST 发出结构化决策事件
- **THEN** 事件 MUST 包含决策类型、简要原因和关联的 graph 阶段上下文

### Requirement: Graph execution events are resume-safe
系统 MUST 让多 agent Deep Research 事件能够区分新执行、重试执行和 checkpoint 恢复后的继续执行。

#### Scenario: Graph resumes after checkpoint
- **WHEN** Deep Research 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 为恢复后的事件提供稳定的 graph run 标识和 attempt 信息
- **THEN** 前端或调试工具 MUST 能判断该事件属于继续执行还是新的独立研究流程

#### Scenario: Scope review resumes after checkpoint
- **WHEN** scope 审阅阶段在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 发出能关联到同一 scope draft 版本或修订链路的恢复后事件
- **THEN** 事件 MUST 不把恢复后的审阅错误地表示为一个全新且无关的 scope 流程

#### Scenario: Worker task is retried
- **WHEN** 某个 researcher task 因失败或恢复而被重新执行
- **THEN** 系统 MUST 发出可关联到同一任务标识的重试事件
- **THEN** 事件 MUST 不把该重试误表示为全新且无关的任务
