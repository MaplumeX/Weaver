## Purpose
定义 Deep Research 中 branch-scoped researcher agent 的执行合同、受控多步循环与结构化结果回传。

## Requirements

### Requirement: Branch research tasks define bounded execution contracts
系统 MUST 将 branch-scoped researcher 工作表示为有边界的 tool-agent execution contract，而不是仅表示为原始搜索 query。

#### Scenario: Supervisor creates a branch objective task
- **WHEN** `supervisor` 基于已批准 scope 或验证反馈生成正式研究任务
- **THEN** 系统 MUST 为每个 branch objective 创建结构化 `ResearchTask`
- **THEN** 该任务 MUST 至少包含唯一标识、`branch_id`、`task_kind`、研究目标、验收标准、允许的工具类别和上游 artifact 引用

#### Scenario: Follow-up branch task references prior work
- **WHEN** `supervisor` 产出 replacement 或 follow-up branch task
- **THEN** 新任务 MUST 能表达它与既有 branch、父任务或上游 artifacts 的关联
- **THEN** 系统 MUST NOT 要求通过读取旧 agent 的完整临时工具对话才能理解该任务

### Requirement: Branch researcher agents execute multi-step bounded loops
系统 MUST 允许 `researcher` 作为 branch-scoped true tool agent 在受控预算和工具边界内执行多步研究。

#### Scenario: Branch agent gathers evidence with tools
- **WHEN** 某个 branch objective 需要搜索、读取、抓取、抽取或轻量分析证据
- **THEN** `researcher` MUST 能在其允许的工具范围内执行多步工具调用
- **THEN** 该执行过程 MUST 受 graph 级预算、重试和 merge 边界控制

#### Scenario: Branch agent cannot expand the graph unilaterally
- **WHEN** `researcher` 在执行中发现新的研究线索
- **THEN** 它 MUST 通过结构化 result bundle、follow-up request 或 escalation 请求 `supervisor` 处理
- **THEN** 它 MUST NOT 直接自行创建不受控的 sibling branch 或无限派生任务

### Requirement: Branch agents return structured result bundles
系统 MUST 要求 branch `researcher` agent 将执行结果表示为结构化 bundle，并只在 graph merge 阶段写入共享权威状态。

#### Scenario: Branch agent completes successfully
- **WHEN** `researcher` 完成一个 branch objective
- **THEN** 它 MUST 返回结构化结果 bundle
- **THEN** 该 bundle MUST 能表达分支结论、证据引用、工具使用摘要、预算消耗和需要写入的 artifacts

#### Scenario: Branch agent completes partially or fails
- **WHEN** `researcher` 因预算、来源不足、审批限制或执行错误而未完成 branch objective
- **THEN** 它 MUST 返回结构化的失败或部分完成状态
- **THEN** graph 与 `supervisor` MUST 能基于该状态决定重试、replan、阻塞或终止，而不是依赖非结构化错误文本

### Requirement: Branch researchers support revision-oriented execution
系统 MUST 允许 `researcher` 除了执行初始 branch research 外，还能执行基于 `BranchRevisionBrief` 的定向修订任务。

#### Scenario: Researcher receives a branch revision brief
- **WHEN** `supervisor` 向 `researcher` 派发 revision-oriented branch task
- **THEN** 系统 MUST 同时提供 prior branch context、未解决 issue、允许复用的已有证据和新的完成标准
- **THEN** `researcher` MUST 把本次执行视为定向补证据、反证或修订工作，而不是一个无上下文的新搜索任务

#### Scenario: Revision execution remains bounded
- **WHEN** `researcher` 在修订过程中发现额外问题或新的支线
- **THEN** 它 MUST 通过结构化 bundle 或 follow-up request 报告这些发现
- **THEN** 它 MUST NOT 在未经过 `supervisor` 批准前无限扩张同一 revision scope

### Requirement: Branch result bundles are verification-ready
系统 MUST 要求 branch `researcher` 在成功或部分完成时返回可直接进入验证流水线的结构化 bundle。

#### Scenario: Initial or revision task completes
- **WHEN** `researcher` 完成任一 branch task
- **THEN** 返回 bundle MUST 同时包含 branch synthesis、claim units、证据引用和 issue resolution metadata（如适用）
- **THEN** `verifier` MUST 能基于该 bundle 直接判断哪些 issues 已解决、哪些 obligations 仍未满足，而不需要重新解析完整工具对话

#### Scenario: Task completes partially
- **WHEN** `researcher` 只能部分完成某个初始或 revision task
- **THEN** bundle MUST 显式标记未完成的 claim / obligation / issue 范围
- **THEN** `supervisor` MUST 能基于这些结构化范围决定继续 patch、派生 follow-up 还是停止
