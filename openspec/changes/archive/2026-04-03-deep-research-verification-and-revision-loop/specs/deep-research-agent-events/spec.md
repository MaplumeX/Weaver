## ADDED Requirements

### Requirement: Verification and revision events are issue-addressable
系统 MUST 让公开 Deep Research 事件能够表达 claim-level verification、obligation evaluation、consistency findings 和 revision issue 生命周期。

#### Scenario: Verification produces structured progress
- **WHEN** `verifier` 完成 claim grounding、coverage evaluation 或 consistency evaluation
- **THEN** 系统 MUST 通过公开事件暴露关联的 claim、obligation、issue 或 consistency finding 标识
- **THEN** 客户端 MUST 能理解“哪条问题导致 branch 被打回”而不需要解析自由文本摘要

#### Scenario: Revision issue lifecycle changes
- **WHEN** 某个 revision issue 被创建、接受、解决、superseded 或 waived
- **THEN** 系统 MUST 发出包含 issue 标识、branch / task 上下文和状态变化的事件
- **THEN** timeline 与调试工具 MUST 能直接呈现问题处理进展

### Requirement: Revision lineage remains observable across retries and patches
系统 MUST 在 branch patch、follow-up branch、counterevidence branch 和 resume/retry 路径中保留稳定的 lineage 事件语义。

#### Scenario: Existing branch is patched
- **WHEN** 某个 branch 因 unresolved issues 被原地修订
- **THEN** 相关 `research_task_update`、`research_artifact_update` 和 `research_decision` 事件 MUST 保留稳定的 target branch、issue ids、iteration 和 attempt 语义
- **THEN** 客户端 MUST 能把这次 patch 识别为同一 branch 历史的继续阶段

#### Scenario: Follow-up work supersedes prior findings
- **WHEN** `supervisor` 派生 follow-up 或 counterevidence branch 来处理既有问题
- **THEN** 相关公开事件 MUST 暴露 parent / target lineage、来源 issue ids 和 resolution 关系
- **THEN** 客户端 MUST 不会把该进展误认为完全无关的新研究流程
