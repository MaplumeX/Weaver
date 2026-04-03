## ADDED Requirements

### Requirement: Deep Research thinking timeline is phase-oriented by default
系统 MUST 将 Deep Research 的 thinking 过程投影为稳定的用户级阶段视图，而不是直接平铺原始事件日志。

#### Scenario: Default timeline renders Deep Research phases
- **WHEN** assistant message 包含 Deep Research 过程事件
- **THEN** 客户端 MUST 将默认视图组织为稳定的阶段分组，至少覆盖 `intake`、`scope`、`planning`、`branch research`、`verify` 和 `report`
- **THEN** 默认视图 MUST 展示用户可理解的阶段标题和状态，而不是原始事件类型名

#### Scenario: Low-level event bursts do not create top-level noise
- **WHEN** 同一阶段在短时间内收到多条底层进度事件
- **THEN** 客户端 MUST 将这些事件折叠到同一阶段摘要中
- **THEN** 默认视图 MUST NOT 为每条低层事件创建一条新的顶层步骤

### Requirement: Research phase is grouped by branch
系统 MUST 将 Deep Research 研究阶段的公开进度按 `branch` 聚组，并以分支摘要作为默认展示单元。

#### Scenario: Branch-scoped progress updates are grouped together
- **WHEN** 多条 `research_*` 事件共享同一 `branch_id`
- **THEN** 客户端 MUST 将这些事件归入同一分支摘要，而不是分散显示为多个无关步骤
- **THEN** 分支摘要 MUST 能表达该分支的最新状态、研究阶段或验证状态

#### Scenario: Internal identifiers stay secondary
- **WHEN** thinking timeline 渲染分支摘要
- **THEN** 默认视图 MUST NOT 直接把 `branch_id`、`task_id` 或 `node_id` 当作主要用户文案
- **THEN** 这些内部标识 MUST 仅出现在展开详情或 raw event drilldown 中

### Requirement: Multi-iteration progress remains distinguishable
系统 MUST 在 thinking timeline 中保留多轮次 Deep Research 的连续性，并防止不同轮次的分支进展被错误合并。

#### Scenario: Timeline enters a new formal iteration
- **WHEN** Deep Research 开始新的正式研究轮次
- **THEN** timeline MUST 展示当前轮次，并保留先前轮次的阶段或分支摘要
- **THEN** 来自不同轮次的进度 MUST NOT 被合并成一个无法区分的单一研究步骤

#### Scenario: Branch retry or resume stays attached to branch history
- **WHEN** 同一 branch 在后续轮次中被重试，或在 checkpoint 恢复后继续执行
- **THEN** timeline MUST 将该进展显示为同一 branch 历史的继续阶段
- **THEN** timeline MUST 同时保留其新的 `iteration` 或 `attempt` 语义

### Requirement: Thinking header uses aggregate progress metrics
系统 MUST 使用聚合后的 Deep Research 进度指标构建 thinking header，而不是直接把原始事件数量当作用户级步骤数。

#### Scenario: Header summarizes projected progress
- **WHEN** Deep Research thinking header 被渲染
- **THEN** header MUST 优先展示聚合指标，例如阶段数、branch 数、来源数或当前轮次
- **THEN** header MUST NOT 仅以原始 `processEvents` 数量作为主要进度文案

### Requirement: Raw event drilldown remains available but secondary
系统 MUST 保留原始 Deep Research 事件的可观察性，同时让原始事件降级为二级信息层。

#### Scenario: User drills into raw process details
- **WHEN** 用户展开更细粒度的过程详情
- **THEN** 客户端 MUST 能访问与同一研究流程关联的原始事件明细
- **THEN** raw events MUST 作为摘要视图的补充信息，而不是默认主视图

### Requirement: Duplicate companion events are suppressed in default view
系统 MUST 在 Deep Research 默认视图中抑制重复或低价值的 companion events，避免同一语义出现两次。

#### Scenario: Canonical structured event already describes a task step
- **WHEN** 某个 Deep Research 任务生命周期步骤已经由 `research_task_update` 或其他 canonical structured event 表达
- **THEN** 默认 timeline MUST 使用该 structured event 作为主显示来源
- **THEN** companion generic event MUST NOT 再生成一条新的顶层步骤

#### Scenario: Topology or search chatter does not overwhelm the timeline
- **WHEN** runtime 连续发出 topology 更新或连续 search 事件，但没有改变用户可感知的阶段或分支状态
- **THEN** 默认 timeline MUST 将这些事件折叠为摘要或次级信息
- **THEN** 它们 MUST NOT 淹没阶段摘要和分支摘要
