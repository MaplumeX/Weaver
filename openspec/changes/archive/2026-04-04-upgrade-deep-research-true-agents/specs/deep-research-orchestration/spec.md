## MODIFIED Requirements

### Requirement: Supervisor-controlled research loop
系统 MUST 由 `supervisor` 独占 multi-agent Deep Research 的全局控制平面语义，并通过显式 handoff 驱动 `clarify`、`scope`、`research brief` handoff、branch dispatch、验证、outline gate、汇总和结束阶段；系统 MUST NOT 再让 execution role 取得与 `supervisor` 等价的控制权。

#### Scenario: Supervisor waits for approved brief before dispatch
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** 系统 MUST 先完成由 `clarify -> scope -> supervisor` 组成的 control-plane handoff 链、scope review 和 `research brief` 生成
- **THEN** `supervisor` MUST 只在收到权威 `research brief` handoff 后，才将 branch 级任务写入可调度队列并分配唯一任务标识

#### Scenario: Supervisor replans from verifier or outline feedback
- **WHEN** `verifier` 产出了新的 blocking revision issues、未解决的 obligation debt、矛盾记录、缺失证据列表或 `outline gate` 产出了 `outline_gap` 请求且预算仍允许继续研究
- **THEN** `supervisor` MUST 基于当前 brief、ledger 和权威 verification 结果决定是否触发 replan、dispatch 或新的 control-plane handoff
- **THEN** 系统 MAY 使用 advisory gap hints 辅助决定后续搜索方向，但 MUST NOT 仅凭 advisory gaps 把流程判定为仍不可报告

#### Scenario: Supervisor owns orchestration decisions directly
- **WHEN** runtime 需要决定继续研究、触发 replan、重试 branch、开始 outline 生成、开始汇总或停止
- **THEN** 系统 MUST 由 `supervisor` 直接产出这些决策
- **THEN** 系统 MUST NOT 再暴露 `coordinator` 角色、execution role 的等价决策分支，或让 `researcher`、`verifier`、`reporter` 直接改变全局控制平面 owner

### Requirement: Parallel branch tool-agent dispatch
系统 MUST 支持多个 `researcher` 与 `verifier` subagents 在 `supervisor` 调度下并发执行 branch 级任务，并通过 graph-native fan-out/fan-in 统一控制并发数、预算和任务状态。

#### Scenario: Multiple branch tasks are ready
- **WHEN** 任务队列中存在多个 `ready` 状态的 branch 级研究任务且未超过并发上限
- **THEN** 系统 MUST 通过 graph 分发机制为不同任务创建独立的 `researcher` subagent 执行路径
- **THEN** 同一 branch 任务 MUST NOT 被多个 subagent 同时执行，且这些 subagent MUST 不获得独立 control-plane 所有权

#### Scenario: Branch execution is budget-gated
- **WHEN** `researcher` 或 `verifier` subagent 尝试领取或继续执行任务
- **THEN** 系统 MUST 在 graph 分发前检查时间、搜索次数、token、步骤数或其他预算限制
- **THEN** 若预算不足，系统 MUST 阻止新的 branch fan-out 并将决策权交回 `supervisor`

### Requirement: Multi-agent graph execution is checkpoint-aware
系统 MUST 让 multi-agent Deep Research 的权威执行状态落在 LangGraph 可 checkpoint 和恢复的边界上，并在恢复后继续暴露 `active_agent`、handoff payload、branch 级执行进度、`supervisor` 决策上下文、brief/ledger 状态和 outline gate 阶段。

#### Scenario: Deep research pauses or resumes
- **WHEN** multi-agent Deep Research 因 interrupt、暂停或进程恢复而需要继续执行
- **THEN** 系统 MUST 能从已持久化的 graph 状态恢复任务队列、artifacts、当前 control-plane owner、权威 `research brief` 和最近的 `supervisor` 决策上下文
- **THEN** 系统 MUST 不要求重新从头执行整个研究流程

#### Scenario: Control-plane handoff resumes after checkpoint
- **WHEN** runtime 在 `clarify`、`scope` 或 `supervisor` 之间完成 handoff 后发生 checkpoint 恢复
- **THEN** 系统 MUST 恢复最近一次 handoff 对应的 `active_agent` 与结构化 payload
- **THEN** 恢复后的流程 MUST 不会把该 handoff 错误表示为新的无关 intake/scoping 会话

#### Scenario: Branch execution resumes after checkpoint
- **WHEN** 某个 branch `researcher` 或 `verifier` subagent 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 恢复该 branch 任务的当前阶段、已提交的中间产物、follow-up request 和重试上下文
- **THEN** 系统 MUST 不把该恢复错误地表示为一个全新的无关 branch

