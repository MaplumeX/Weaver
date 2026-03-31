## Purpose
定义 multi-agent Deep Research 在任务协作、证据沉淀和最终汇总中的结构化 artifacts 契约。

## Requirements

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

### Requirement: Isolated worker context
系统 MUST 为每个 researcher worker 提供独立上下文，而不是共享 sibling 的完整消息历史。

#### Scenario: Worker starts a task
- **WHEN** researcher worker 领取一个任务
- **THEN** 系统 MUST 仅向该 worker 注入共享研究 brief、任务上下文和与该任务相关的 artifacts
- **THEN** 系统 MUST NOT 默认注入其他 sibling worker 的完整消息历史

#### Scenario: Worker finishes a task
- **WHEN** researcher worker 完成任务并提交结果
- **THEN** 系统 MUST 只合并该任务产出的结构化 artifacts 和必要摘要
- **THEN** 系统 MUST NOT 将该 worker 的完整临时上下文无差别写回共享状态

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

### Requirement: Artifact lifecycle tracking
系统 MUST 追踪 artifacts 的创建、更新、归属和完成状态，以支持调试、测试和恢复。

#### Scenario: Artifact state changes
- **WHEN** 任意 task 或 artifact 被创建、更新、完成或废弃
- **THEN** 系统 MUST 记录其当前状态和关联实体
- **THEN** 后续 agent MUST 能够基于这些状态读取最新的有效 artifacts

### Requirement: Artifact snapshots are checkpoint-safe
系统 MUST 将 Deep Research 的权威 artifacts 表达为可 checkpoint、可恢复的序列化快照，而不是只依赖进程内对象身份。

#### Scenario: Persisting artifact state at graph boundaries
- **WHEN** Deep Research 子图到达可 checkpoint 的阶段边界
- **THEN** 系统 MUST 能持久化任务队列、artifact store 和 agent run ledger 的当前快照
- **THEN** 这些快照 MUST 足以在恢复时重建权威研究状态

#### Scenario: Rebuilding store views after resume
- **WHEN** 多 agent Deep Research 从 checkpoint 恢复
- **THEN** 系统 MUST 能依据持久化快照重建 artifacts 的读取视图或 facade
- **THEN** verifier、coordinator 和 reporter MUST 不依赖历史进程中的对象引用才能继续工作

### Requirement: Artifact merge is graph-mediated
系统 MUST 在明确的 graph merge 或 reduce 阶段合并 worker 产物，而不是允许 worker 直接改写共享权威状态。

#### Scenario: Worker returns a result payload
- **WHEN** researcher worker 返回证据、摘要、来源或错误信息
- **THEN** 系统 MUST 先将该结果表示为结构化返回 payload
- **THEN** 只有 graph 统一 merge 阶段 MAY 将这些结果写入共享 artifacts 和任务状态

#### Scenario: Multiple workers finish concurrently
- **WHEN** 多个 researcher worker 在同一 fan-out 周期内完成
- **THEN** 系统 MUST 通过确定性的 merge 规则合并其产物
- **THEN** 系统 MUST 避免依赖线程时序决定最终 artifact 状态
