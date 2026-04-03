## ADDED Requirements

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
