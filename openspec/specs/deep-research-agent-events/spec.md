## Purpose
定义 multi-agent Deep Research 的事件模型与流式兼容约束。

## Requirements

### Requirement: Agent lifecycle events
系统 MUST 为 multi-agent Deep Research runtime 发出可消费的 agent 生命周期事件，并为每次 graph-level 执行提供稳定的关联标识，同时使 `supervisor` 与 tool agents 的 branch 级阶段推进可被识别。

#### Scenario: Agent starts execution
- **WHEN** `clarify`、`scope`、`supervisor`、`researcher`、`verifier` 或 `reporter` 开始执行一个任务或阶段
- **THEN** 系统 MUST 发出包含 agent 标识、角色、关联任务或阶段信息的事件
- **THEN** 对于 branch tool agents，事件 MUST 额外具备足以标识 `branch_id`、`task_kind`、内部执行阶段和当前控制平面上下文的字段

#### Scenario: Agent completes execution
- **WHEN** 任一 Deep Research agent 完成、失败、部分完成或被取消
- **THEN** 系统 MUST 发出对应状态事件
- **THEN** 事件 MUST 包含足够的关联字段以让前端将其映射到同一 branch 任务流和同一 `supervisor` 决策周期

### Requirement: Task and decision progress events
系统 MUST 暴露任务队列、scope 草案流转、branch 执行推进、blackboard 提交和 `supervisor` 决策的关键进度事件，并使其能够表达 graph fan-out/fan-in、验证回流和启动阶段的稳定 phase 语义。

#### Scenario: Scope draft is produced or revised
- **WHEN** `scope agent` 生成新的 scope draft，或基于用户反馈重写 scope draft
- **THEN** 系统 MUST 发出可标识当前草案版本和阶段上下文的进度事件
- **THEN** 前端 MUST 无需解析完整内部状态对象即可判断该草案处于待审阅、待修订还是已批准状态

#### Scenario: Branch task queue changes
- **WHEN** 研究任务被创建、领取、阻塞、完成、回退、重试或被 `supervisor` 重新排序
- **THEN** 系统 MUST 发出任务状态更新事件
- **THEN** 事件 MUST 能标识该任务属于哪个 graph run、哪个 `branch_id`、何种 `task_kind` 以及其父任务或上游决策

#### Scenario: Supervisor or verifier makes a decision
- **WHEN** `supervisor` 决定继续研究、触发 replan、开始汇总、结束，或 `verifier` 给出通过、回退、补证据等结果
- **THEN** 系统 MUST 发出结构化决策事件
- **THEN** 事件 MUST 包含决策类型、简要原因和关联的 graph / branch 阶段上下文

#### Scenario: Startup phase uses stable structured progress semantics
- **WHEN** multi-agent Deep Research 进入 clarify、scope、scope review handoff 或 supervisor initial planning 阶段
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
系统 MUST 让多 agent Deep Research 事件能够区分新执行、重试执行和 checkpoint 恢复后的继续执行，并能正确关联 branch 级执行阶段。

#### Scenario: Graph resumes after checkpoint
- **WHEN** Deep Research 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 为恢复后的事件提供稳定的 graph run 标识和 attempt 信息
- **THEN** 前端或调试工具 MUST 能判断该事件属于继续执行还是新的独立研究流程

#### Scenario: Branch stage resumes after checkpoint
- **WHEN** 某个 researcher branch agent 或 verifier validation stage 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 发出能关联到同一 `branch_id`、任务标识和阶段链路的恢复后事件
- **THEN** 事件 MUST 不把恢复后的执行错误地表示为一个全新且无关的 branch 流程

#### Scenario: Worker task is retried
- **WHEN** 某个 researcher task 因失败或恢复而被重新执行
- **THEN** 系统 MUST 发出可关联到同一任务标识的重试事件
- **THEN** 事件 MUST 不把该重试误表示为全新且无关的任务

#### Scenario: Clients can associate resumed progress with the interrupted flow
- **WHEN** 恢复后的执行继续发出 `supervisor`、research、verify 或 report 阶段事件
- **THEN** 这些事件 MUST 保留稳定的 graph-level 关联字段和恢复上下文
- **THEN** 客户端 MUST 能把它们识别为同一研究流程在 checkpoint 之后的继续阶段，而不是一条新的无关流程

### Requirement: Branch execution stage progress is observable
系统 MUST 让前端和调试工具能够观察 branch `researcher` 与 `verifier` 的细分执行阶段，而不要求解析内部临时状态对象。

#### Scenario: Researcher advances execution stages
- **WHEN** `researcher` 在 branch 执行中进入搜索、读取、抽取、综合或提交结果等内部阶段
- **THEN** 系统 MUST 通过现有 Deep Research 事件家族暴露该阶段推进
- **THEN** 事件 MUST 保留稳定的 role 语义，而不是把每个内部阶段都伪装成新的顶层 agent

#### Scenario: Verifier advances validation stages
- **WHEN** `verifier` 进入 challenge、claim/citation 检查、coverage/gap 检查或提交 follow-up request 等内部阶段
- **THEN** 系统 MUST 通过结构化字段暴露当前验证阶段
- **THEN** 客户端 MUST 能把这些阶段识别为同一 verifier role 的不同执行阶段

### Requirement: Public role semantics match runtime roles
系统 MUST 让公开 Deep Research 事件流中的角色与阶段语义直接反映当前 `multi_agent` runtime 的真实角色，而不是继续暴露 `planner`、`coordinator` 等旧词汇。

#### Scenario: Planning and orchestration progress is emitted
- **WHEN** Deep Research 进入初始规划、replan、scope 审核后续动作或最终停机决策阶段
- **THEN** 系统 MUST 使用 `supervisor` 作为公开的 orchestration role
- **THEN** 事件 MUST 继续携带 phase、decision 和恢复上下文，使客户端无需 legacy 角色别名也能理解进度

#### Scenario: Frontend renders deep research progress
- **WHEN** 前端或测试消费 Deep Research 事件流
- **THEN** 它们 MUST 能基于 `supervisor`、`researcher`、`verifier` 和 `reporter` 角色直接渲染状态
- **THEN** 客户端 MUST NOT 依赖把同一事件再映射成 `planner` 或 `coordinator` 才能工作
