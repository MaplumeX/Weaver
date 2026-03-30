## Purpose
定义 multi-agent Deep Research 的事件模型与流式兼容约束。

## Requirements

### Requirement: Agent lifecycle events
系统 MUST 为 multi-agent Deep Research runtime 发出可消费的 agent 生命周期事件。

#### Scenario: Agent starts execution
- **WHEN** coordinator、planner、researcher、verifier 或 reporter 开始执行一个任务或阶段
- **THEN** 系统 MUST 发出包含 agent 标识、角色、关联任务和阶段信息的事件

#### Scenario: Agent completes execution
- **WHEN** 任一 Deep Research agent 完成、失败或被取消
- **THEN** 系统 MUST 发出对应状态事件
- **THEN** 事件 MUST 包含足够的关联字段以让前端将其映射到同一任务流

### Requirement: Task and decision progress events
系统 MUST 暴露任务队列和 coordinator 决策的关键进度事件。

#### Scenario: Task queue changes
- **WHEN** 研究任务被创建、领取、阻塞、完成或回退
- **THEN** 系统 MUST 发出任务状态更新事件
- **THEN** 事件 MUST 能标识该任务属于哪个研究线程和父任务

#### Scenario: Coordinator makes a loop decision
- **WHEN** coordinator 决定继续研究、触发 replan、开始汇总或结束
- **THEN** 系统 MUST 发出结构化决策事件
- **THEN** 事件 MUST 包含决策类型和简要原因

### Requirement: Event stream compatibility
系统 MUST 在增加 multi-agent 事件的同时保持现有流式消费链路兼容。

#### Scenario: Existing clients ignore new event types
- **WHEN** 客户端未识别新增的 multi-agent 事件类型
- **THEN** 系统 MUST 仍然输出现有最终回答与基础 Deep Research 事件
- **THEN** 请求 MUST 不因新增事件而失去最终结果

#### Scenario: Frontend renders multi-agent progress
- **WHEN** 前端支持新增 multi-agent 事件
- **THEN** 前端 MUST 能将 agent、task 和 decision 事件呈现为可理解的研究过程
- **THEN** 前端 MUST 不要求解析原始内部状态对象
