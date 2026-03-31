## MODIFIED Requirements

### Requirement: Structured research artifacts
系统 MUST 使用结构化且可序列化的 research artifacts 作为 multi-agent Deep Research runtime 的主要协作媒介，并允许这些 artifacts 表达 branch agent 的多步执行过程。

#### Scenario: Planner creates branch task artifacts
- **WHEN** planner 为研究主题生成初始计划或补充计划
- **THEN** 系统 MUST 将每个 branch 计划项保存为结构化 `ResearchTask`
- **THEN** 每个 `ResearchTask` MUST 至少包含唯一标识、`branch_id`、任务目标、任务类型、验收标准、允许工具类别、状态和上游 artifact 引用

#### Scenario: Researcher creates branch execution artifacts
- **WHEN** researcher 在执行 branch objective 的过程中搜索、读取、抓取、抽取或总结信息
- **THEN** 系统 MUST 将关键中间产物表示为结构化 artifacts
- **THEN** 这些 artifacts MUST 能表达来源候选、抓取文档、证据片段和分支结论等可追溯结果

### Requirement: Evidence-backed synthesis
系统 MUST 基于结构化证据产物和验证结果完成质量判断与最终报告生成，而不是直接基于未经验证的中间摘要完成汇总。

#### Scenario: Verifier evaluates branch conclusions
- **WHEN** verifier 检查某个 branch synthesis 的 claim、citation 或 coverage
- **THEN** 系统 MUST 基于已有 `EvidencePassage`、抓取文档、来源元数据和 branch 任务状态执行判断
- **THEN** verifier 产出的验证结论 MUST 可被 coordinator 直接消费

#### Scenario: Reporter generates the final report
- **WHEN** reporter 生成最终研究报告
- **THEN** 系统 MUST 仅使用共享 artifact store 中已验证、可追溯的 branch 结论与证据作为事实依据
- **THEN** 系统 MUST 为报告输出可关联到分支证据来源的引用信息

## ADDED Requirements

### Requirement: Verification artifacts are first-class handoff payloads
系统 MUST 将 branch-level 验证结果表示为结构化 artifacts 或等价结构化 payload，而不是仅以自由文本备注存在。

#### Scenario: Claim or citation validation completes
- **WHEN** verifier 完成一个 branch 的 claim/citation 检查
- **THEN** 系统 MUST 记录结构化验证结果
- **THEN** 该结果 MUST 能表达检查对象、结论状态、证据引用和后续建议动作

#### Scenario: Coverage validation requests follow-up work
- **WHEN** verifier 认定某个 branch 或整体研究仍存在 coverage gap
- **THEN** 系统 MUST 以结构化方式记录 gap 与建议的后续研究方向
- **THEN** coordinator MUST 能直接消费这些结果而不依赖重新解析自由文本
