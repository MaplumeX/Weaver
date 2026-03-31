## MODIFIED Requirements

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
