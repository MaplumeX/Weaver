## ADDED Requirements

### Requirement: Coordination requests are blackboard artifacts
系统 MUST 将 follow-up request、retry hint、escalation 和报告就绪通知表示为 blackboard 上的一等结构化 payload，而不是仅以自由文本备注存在。

#### Scenario: Research agent requests follow-up work
- **WHEN** `researcher` 发现新的研究方向、阻塞条件或需要更多预算
- **THEN** 系统 MUST 记录结构化 coordination request
- **THEN** `supervisor` MUST 能直接消费该请求而不依赖重新解析自由文本

#### Scenario: Verifier requests additional evidence
- **WHEN** `verifier` 认定某个 branch 需要补充证据或改写结论
- **THEN** 系统 MUST 记录结构化 follow-up request 或 retry request
- **THEN** `supervisor` MUST 能基于该请求决定重试、replan 或停止

## MODIFIED Requirements

### Requirement: Structured research artifacts
系统 MUST 使用结构化且可序列化的 research artifacts 作为 multi-agent Deep Research runtime 的主要协作媒介，并允许这些 artifacts 表达 branch agent 的多步执行过程与 blackboard 提交动作。

#### Scenario: Supervisor creates branch task artifacts
- **WHEN** `supervisor` 为研究主题生成初始计划或补充计划
- **THEN** 系统 MUST 将每个 branch 计划项保存为结构化 `ResearchTask`
- **THEN** 每个 `ResearchTask` MUST 至少包含唯一标识、`branch_id`、任务目标、任务类型、验收标准、允许工具类别、状态和上游 artifact 引用

#### Scenario: Agents create execution artifacts
- **WHEN** `researcher`、`verifier` 或 `reporter` 在执行过程中搜索、读取、抓取、抽取、验证、总结或提交结果
- **THEN** 系统 MUST 将关键中间产物和提交结果表示为结构化 artifacts 或等价结构化 payload
- **THEN** 这些 artifacts MUST 能表达来源候选、抓取文档、证据片段、分支结论、验证结论和报告输入等可追溯结果

### Requirement: Evidence-backed synthesis
系统 MUST 基于结构化证据产物和验证结果完成质量判断与最终报告生成，而不是直接基于未经验证的中间摘要完成汇总。

#### Scenario: Verifier evaluates branch conclusions
- **WHEN** `verifier` 检查某个 branch synthesis 的 claim、citation、coverage 或来源可信度
- **THEN** 系统 MUST 基于已有 `EvidencePassage`、抓取文档、来源元数据和 branch 任务状态执行判断
- **THEN** verifier 产出的验证结论 MUST 可被 `supervisor` 直接消费

#### Scenario: Reporter generates the final report
- **WHEN** `reporter` 生成最终研究报告
- **THEN** 系统 MUST 仅使用共享 artifact store 中已验证、可追溯的 branch 结论与证据作为事实依据
- **THEN** 系统 MUST 为报告输出可关联到分支证据来源的引用信息

### Requirement: Verification artifacts are first-class handoff payloads
系统 MUST 将 branch-level 验证结果表示为结构化 artifacts 或等价结构化 payload，而不是仅以自由文本备注存在。

#### Scenario: Claim or citation validation completes
- **WHEN** `verifier` 完成一个 branch 的 claim/citation 检查
- **THEN** 系统 MUST 记录结构化验证结果
- **THEN** 该结果 MUST 能表达检查对象、结论状态、证据引用和后续建议动作

#### Scenario: Coverage validation requests follow-up work
- **WHEN** `verifier` 认定某个 branch 或整体研究仍存在 coverage gap
- **THEN** 系统 MUST 以结构化方式记录 gap 与建议的后续研究方向
- **THEN** `supervisor` MUST 能直接消费这些结果而不依赖重新解析自由文本

### Requirement: Artifact merge is graph-mediated
系统 MUST 在明确的 graph merge 或 reduce 阶段合并 agent 产物，而不是允许 agent 直接改写共享权威状态。

#### Scenario: Agent returns a result payload
- **WHEN** 任一 Deep Research agent 返回证据、摘要、来源、验证结果、协调请求或错误信息
- **THEN** 系统 MUST 先将该结果表示为结构化返回 payload
- **THEN** 只有 graph 统一 merge 阶段 MAY 将这些结果写入共享 artifacts 和任务状态

#### Scenario: Multiple agents finish concurrently
- **WHEN** 多个 Deep Research agents 在同一 fan-out 周期内完成
- **THEN** 系统 MUST 通过确定性的 merge 规则合并其产物
- **THEN** 系统 MUST 避免依赖并发时序决定最终 artifact 状态
