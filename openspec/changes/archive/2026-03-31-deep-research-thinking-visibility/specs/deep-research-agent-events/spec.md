## MODIFIED Requirements

### Requirement: Task and decision progress events
系统 MUST 暴露任务队列、scope 草案流转和 coordinator 决策的关键进度事件，并使其能够表达 graph fan-out/fan-in、用户审阅状态和启动阶段的稳定 phase 语义。

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

#### Scenario: Startup phase uses stable structured progress semantics
- **WHEN** multi-agent Deep Research 进入 clarify、scope、scope review handoff 或 initial plan 阶段
- **THEN** 系统 MUST 发出足够的结构化 phase 上下文字段，让前端可以直接基于 Deep Research 事件呈现当前阶段
- **THEN** 客户端 MUST NOT 被迫依赖重复的通用节点状态文案才能理解启动阶段正在发生什么

### Requirement: Event stream compatibility
系统 MUST 在增加 multi-agent 事件的同时保持现有流式消费链路兼容，并让恢复后的研究流程继续使用同一类流式契约。

#### Scenario: Existing clients ignore new event types
- **WHEN** 客户端未识别新增的 multi-agent 事件类型或新增关联字段
- **THEN** 系统 MUST 仍然输出现有最终回答与基础 Deep Research 事件
- **THEN** 请求 MUST 不因新增事件而失去最终结果

#### Scenario: Frontend renders multi-agent progress
- **WHEN** 前端支持新增 multi-agent 事件
- **THEN** 前端 MUST 能将 agent、task、branch 和 decision 事件呈现为可理解的研究过程
- **THEN** 前端 MUST 不要求解析原始内部状态对象

#### Scenario: Resume path uses the same streaming contract family
- **WHEN** 客户端在 interrupt 或 review 之后请求继续执行 Deep Research
- **THEN** 系统 MUST 通过与初始运行同一类的流式契约暴露恢复后的 agent、task、artifact 和 decision 事件
- **THEN** 已经支持初始 Deep Research 流式事件的客户端 MUST 能在不切换到结果专用协议的情况下消费恢复后的过程

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

#### Scenario: Clients can associate resumed progress with the interrupted flow
- **WHEN** 恢复后的执行继续发出 planner、research、verify 或 report 阶段事件
- **THEN** 这些事件 MUST 保留稳定的 graph-level 关联字段和恢复上下文
- **THEN** 客户端 MUST 能把它们识别为同一研究流程在 checkpoint 之后的继续阶段，而不是一条新的无关流程
