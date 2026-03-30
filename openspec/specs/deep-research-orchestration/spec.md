## Purpose
定义 Deep Research 在 `legacy` 与 `multi_agent` 运行时之间的选择规则，以及 multi-agent 编排循环的核心行为。

## Requirements

### Requirement: Deep Research engine selection
系统 MUST 为 Deep Research 提供可配置的运行时引擎选择，并支持在 `legacy` 与 `multi_agent` 引擎之间切换。

#### Scenario: Multi-agent engine is selected for deep research
- **WHEN** 请求被路由到 `deep` 模式且运行配置选择 `multi_agent` 引擎
- **THEN** 系统 MUST 在 `deepsearch_node` 内启动 multi-agent Deep Research runtime
- **THEN** 系统 MUST 保持现有 Deep Research 入口、取消语义和最终报告输出契约不变

#### Scenario: Legacy engine remains available
- **WHEN** 请求被路由到 `deep` 模式且运行配置选择 `legacy` 引擎
- **THEN** 系统 MUST 继续使用现有 legacy deepsearch runner
- **THEN** 系统 MUST 不要求前端或 API 调用方更改请求格式

### Requirement: Coordinator-controlled research loop
系统 MUST 由 coordinator 统一控制 multi-agent Deep Research 的研究循环，而不是由 researcher worker 自主无限扩展任务。

#### Scenario: Coordinator initializes research plan
- **WHEN** multi-agent Deep Research runtime 接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** coordinator MUST 触发 planner 生成初始研究任务集合
- **THEN** 系统 MUST 将这些任务写入可调度的任务队列并分配唯一任务标识

#### Scenario: Coordinator triggers replan from gaps
- **WHEN** verifier 或 researcher 产出了新的 `KnowledgeGap` 且预算仍允许继续研究
- **THEN** coordinator MUST 基于当前证据和缺口决定是否触发 replan
- **THEN** 系统 MUST 只将被批准的新任务加入任务队列

#### Scenario: Coordinator terminates the loop
- **WHEN** coordinator 判断覆盖度已满足完成条件或剩余预算不足以继续研究
- **THEN** 系统 MUST 停止发放新的 researcher 任务
- **THEN** 系统 MUST 转入最终汇总与完成阶段

### Requirement: Parallel researcher worker dispatch
系统 MUST 支持多个 researcher worker 并发执行研究任务，并对并发数、预算和任务状态进行统一控制。

#### Scenario: Multiple research tasks are ready
- **WHEN** 任务队列中存在多个 `ready` 状态的研究任务且未超过并发上限
- **THEN** 系统 MUST 允许多个 researcher worker 并发领取不同任务
- **THEN** 同一任务 MUST NOT 被多个 worker 同时执行

#### Scenario: Worker execution is budget-gated
- **WHEN** researcher worker 尝试领取或继续执行任务
- **THEN** 系统 MUST 在执行前检查时间、搜索次数或 token 等预算限制
- **THEN** 若预算不足，系统 MUST 阻止新任务执行并将控制权交回 coordinator

### Requirement: Surface multi-agent runtime failures explicitly
系统 MUST 在 multi-agent Deep Research runtime 发生不可恢复错误时显式报错，而不是自动回退到 legacy deepsearch runner。

#### Scenario: Multi-agent runtime initialization fails
- **WHEN** multi-agent runtime 在启动阶段发生不可恢复错误
- **THEN** 系统 MUST 记录失败原因
- **THEN** 系统 MUST 将错误透传到上层 Deep Research 错误处理链路

#### Scenario: Core orchestration becomes invalid during execution
- **WHEN** coordinator、artifact store 或任务调度核心发生不可恢复错误
- **THEN** 系统 MUST 停止继续发放新的 multi-agent 任务
- **THEN** 系统 MUST 进入有界失败路径，而不能无限重试或静默切换 engine
