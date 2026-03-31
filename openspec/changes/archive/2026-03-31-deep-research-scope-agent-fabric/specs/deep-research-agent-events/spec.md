## MODIFIED Requirements

### Requirement: Agent lifecycle events
系统 MUST 为 multi-agent Deep Research runtime 发出可消费的 agent 生命周期事件，并为每次 graph-level 执行提供稳定的关联标识。

#### Scenario: Agent starts execution
- **WHEN** coordinator、planner、researcher、verifier 或 reporter 开始执行一个任务或阶段
- **THEN** 系统 MUST 发出包含 agent 标识、角色、关联任务和阶段信息的事件
- **THEN** 事件 MUST 具备足以关联 graph run、node、branch 或 attempt 的字段

#### Scenario: Agent completes execution
- **WHEN** 任一 Deep Research agent 完成、失败或被取消
- **THEN** 系统 MUST 发出对应状态事件
- **THEN** 事件 MUST 包含足够的关联字段以让前端将其映射到同一任务流

### Requirement: Task and decision progress events
系统 MUST 暴露任务队列和 coordinator 决策的关键进度事件，并使其能够表达 graph fan-out/fan-in 和分支归属。

#### Scenario: Task queue changes
- **WHEN** 研究任务被创建、领取、阻塞、完成、回退或重试
- **THEN** 系统 MUST 发出任务状态更新事件
- **THEN** 事件 MUST 能标识该任务属于哪个 graph run、研究线程和父任务

#### Scenario: Coordinator makes a loop decision
- **WHEN** coordinator 决定继续研究、触发 replan、开始汇总或结束
- **THEN** 系统 MUST 发出结构化决策事件
- **THEN** 事件 MUST 包含决策类型、简要原因和关联的 graph 阶段上下文

### Requirement: Event stream compatibility
系统 MUST 在增加 multi-agent 事件的同时保持现有流式消费链路兼容。

#### Scenario: Existing clients ignore new event types
- **WHEN** 客户端未识别新增的 multi-agent 事件类型或新增关联字段
- **THEN** 系统 MUST 仍然输出现有最终回答与基础 Deep Research 事件
- **THEN** 请求 MUST 不因新增事件而失去最终结果

#### Scenario: Frontend renders multi-agent progress
- **WHEN** 前端支持新增 multi-agent 事件
- **THEN** 前端 MUST 能将 agent、task、branch 和 decision 事件呈现为可理解的研究过程
- **THEN** 前端 MUST 不要求解析原始内部状态对象

## ADDED Requirements

### Requirement: Graph execution events are resume-safe
系统 MUST 让多 agent Deep Research 事件能够区分新执行、重试执行和 checkpoint 恢复后的继续执行。

#### Scenario: Graph resumes after checkpoint
- **WHEN** Deep Research 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 为恢复后的事件提供稳定的 graph run 标识和 attempt 信息
- **THEN** 前端或调试工具 MUST 能判断该事件属于继续执行还是新的独立研究流程

#### Scenario: Worker task is retried
- **WHEN** 某个 researcher task 因失败或恢复而被重新执行
- **THEN** 系统 MUST 发出可关联到同一任务标识的重试事件
- **THEN** 事件 MUST 不把该重试误表示为全新且无关的任务
