## MODIFIED Requirements

### Requirement: Supervisor-controlled research loop
系统 MUST 由 `supervisor` 独占 multi-agent Deep Research 的规划与循环控制语义，并通过显式 graph 转移驱动 clarify、scope、scope review、`research brief` handoff、branch dispatch、验证、outline gate、汇总和结束阶段；系统 MUST NOT 再公开或保留独立 `coordinator` 角色、outer hierarchical path 或等价兼容控制面。

#### Scenario: Supervisor waits for approved brief before dispatch
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** 系统 MUST 先完成 clarify/scoping、scope review 和 `research brief` 生成
- **THEN** `supervisor` MUST 只在权威 `research brief` 就绪后，才将 branch 级任务写入可调度队列并分配唯一任务标识

#### Scenario: Supervisor replans from verifier or outline feedback
- **WHEN** `verifier` 产出了新的 coverage 缺口、矛盾记录、缺失证据列表或 `outline gate` 产出了 `outline_gap` 请求且预算仍允许继续研究
- **THEN** `supervisor` MUST 基于当前 brief、ledger 和验证结果决定是否触发 replan
- **THEN** 系统 MUST 只将被 `supervisor` 批准的新 branch 任务加入任务队列

#### Scenario: Supervisor owns orchestration decisions directly
- **WHEN** runtime 需要决定继续研究、触发 replan、重试 branch、开始 outline 生成、开始汇总或停止
- **THEN** 系统 MUST 由 `supervisor` 直接产出这些决策
- **THEN** 系统 MUST NOT 再暴露 `coordinator` 角色、`coordinator_action` 状态或等价兼容决策分支

### Requirement: Multi-agent graph execution is checkpoint-aware
系统 MUST 让 multi-agent Deep Research 的权威执行状态落在 LangGraph 可 checkpoint 和恢复的边界上，而不是只存在于进程内循环，并在恢复后继续向调用方暴露 branch 级执行进度、`supervisor` 决策上下文、brief/ledger 状态和 outline gate 阶段。

#### Scenario: Deep research pauses or resumes
- **WHEN** multi-agent Deep Research 因 interrupt、暂停或进程恢复而需要继续执行
- **THEN** 系统 MUST 能从已持久化的 graph 状态恢复任务队列、artifacts、当前阶段、权威 `research brief` 和最近的 `supervisor` 决策上下文
- **THEN** 系统 MUST 不要求重新从头执行整个研究流程

#### Scenario: Outline stage resumes after checkpoint
- **WHEN** `outline gate` 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 保留稳定的研究主题、已验证 branch synthesis、coverage/contradiction 输入和待处理 `outline_gap` 状态
- **THEN** `reporter` MUST 能基于恢复后的 outline 状态继续执行，而不会把该恢复错误地表示为一次全新的报告生成

## ADDED Requirements

### Requirement: Outline gate blocks final report until structure is ready
系统 MUST 在最终 `report` 前执行一个独立的 `outline gate`，并要求该 gate 只消费已验证 branch synthesis 与验证 artifacts 来生成最终报告大纲。

#### Scenario: Outline is generated from verified inputs
- **WHEN** `supervisor` 判断研究事实层面已经具备进入写作准备的条件
- **THEN** 系统 MUST 先运行 `outline gate` 生成结构化 outline artifact
- **THEN** `reporter` MUST NOT 在 outline artifact 尚未生成前直接开始最终报告汇总

#### Scenario: Outline gaps reopen the research loop
- **WHEN** `outline gate` 判断当前已验证 branch 结论不足以支撑完整报告结构
- **THEN** 系统 MUST 记录结构化 `outline_gap` request 并把控制权交回 `supervisor`
- **THEN** `supervisor` MUST 决定补充研究、重排现有任务，或停止继续推进报告生成
