## ADDED Requirements

### Requirement: Research brief and supervisor ledgers are first-class artifacts
系统 MUST 将 `research brief`、`task ledger` 和 `progress ledger` 表示为 Deep Research blackboard 上的一等结构化 artifacts，而不是只存在于 prompt 拼接或 runtime 临时字段中。

#### Scenario: Approved scope produces a canonical research brief
- **WHEN** 用户批准当前 scope draft
- **THEN** 系统 MUST 生成结构化 `research brief` artifact
- **THEN** 该 artifact MUST 能表达研究目标、覆盖维度、纳入/排除范围、交付约束、来源偏好和时间边界

#### Scenario: Supervisor updates ledgers during planning and replan
- **WHEN** `supervisor` 生成初始计划、重排 branch 或决定停止/汇总
- **THEN** 系统 MUST 更新对应的 `task ledger` 与 `progress ledger`
- **THEN** 后续角色 MUST 能直接读取这些 ledger 来理解当前控制面状态，而不依赖重新解析自由文本摘要

### Requirement: Outline artifacts gate final reporting
系统 MUST 将最终报告前的大纲整理结果表示为结构化 artifact，并让该 artifact 成为 `reporter` 进入最终成文阶段的必经 handoff。

#### Scenario: Outline artifact is created from verified research
- **WHEN** 系统进入最终写作准备阶段
- **THEN** 系统 MUST 记录结构化 outline artifact
- **THEN** 该 artifact MUST 能表达章节结构、每节对应的 branch/证据引用和仍待补足的结构缺口

#### Scenario: Outline gap blocks final report
- **WHEN** outline artifact 仍标记存在阻塞性的结构缺口
- **THEN** 系统 MUST 将该缺口记录为 `outline_gap` request
- **THEN** `reporter` MUST NOT 在该阻塞缺口未解决前进入最终报告生成

## MODIFIED Requirements

### Requirement: Coordination requests are blackboard artifacts
系统 MUST 将 follow-up request、retry hint、反证请求、结构缺口通知和工具阻塞通知表示为 blackboard 上的一等结构化 payload，而不是仅以自由文本备注存在；允许的权威 request type MUST 仅包括 `retry_branch`、`need_counterevidence`、`contradiction_found`、`outline_gap`、`blocked_by_tooling`。

#### Scenario: Research agent requests follow-up work
- **WHEN** `researcher` 发现新的研究方向、阻塞条件或需要更多预算
- **THEN** 系统 MUST 记录结构化 coordination request，且其 request type MUST 属于允许集合
- **THEN** `supervisor` MUST 能直接消费该请求而不依赖重新解析自由文本

#### Scenario: Verifier or outline stage requests corrective work
- **WHEN** `verifier` 认定某个 branch 需要补充证据、补充反证、处理矛盾，或 `outline gate` 认定报告结构仍存在缺口
- **THEN** 系统 MUST 记录结构化 coordination request，且其 request type MUST 属于允许集合
- **THEN** 系统 MUST NOT 记录开放式或未注册的 request type，也 MUST NOT 使用 `needs_human_decision` 作为本次变更的一部分

### Requirement: Verification artifacts are first-class handoff payloads
系统 MUST 将 branch-level 验证结果表示为结构化 artifacts 或等价结构化 payload，而不是仅以自由文本备注存在；这些结果 MUST 能显式表达 coverage、矛盾和缺失证据，而不是只给出单一摘要。

#### Scenario: Claim or citation validation completes
- **WHEN** `verifier` 完成一个 branch 的 claim/citation 检查
- **THEN** 系统 MUST 记录结构化验证结果
- **THEN** 该结果 MUST 能表达检查对象、结论状态、证据引用和后续建议动作

#### Scenario: Verification produces coverage and contradiction artifacts
- **WHEN** `verifier` 完成对 branch 或整体研究的覆盖度检查
- **THEN** 系统 MUST 记录结构化 `coverage matrix`、`contradiction registry` 和 `missing evidence list`，或与其等价的正式 artifacts
- **THEN** `supervisor` 与 `outline gate` MUST 能直接消费这些 artifacts，而不依赖重新解析自然语言摘要
