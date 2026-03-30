## ADDED Requirements

### Requirement: Structured research artifacts
系统 MUST 使用结构化 research artifacts 作为 multi-agent Deep Research runtime 的主要协作媒介。

#### Scenario: Planner creates task artifacts
- **WHEN** planner 为研究主题生成初始计划或补充计划
- **THEN** 系统 MUST 将每个计划项保存为结构化 `ResearchTask`
- **THEN** 每个 `ResearchTask` MUST 至少包含唯一标识、任务目标、优先级、状态和父上下文引用

#### Scenario: Researcher creates evidence artifacts
- **WHEN** researcher 完成一个研究任务或阶段性搜索
- **THEN** 系统 MUST 将关键发现保存为结构化 `EvidenceCard`
- **THEN** 每个 `EvidenceCard` MUST 绑定来源、产生它的任务、摘要内容和可追溯元数据

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
系统 MUST 基于结构化证据产物完成质量判断和最终报告生成。

#### Scenario: Verifier evaluates coverage
- **WHEN** verifier 检查当前研究覆盖度
- **THEN** 系统 MUST 基于已有 `EvidenceCard`、`KnowledgeGap` 和任务状态执行判断
- **THEN** verifier 产出的缺口结论 MUST 可被 coordinator 直接消费

#### Scenario: Reporter generates the final report
- **WHEN** reporter 生成最终研究报告
- **THEN** 系统 MUST 仅使用共享 artifact store 中可追溯的研究证据作为事实依据
- **THEN** 系统 MUST 为报告输出可关联到证据来源的引用信息

### Requirement: Artifact lifecycle tracking
系统 MUST 追踪 artifacts 的创建、更新、归属和完成状态，以支持调试、测试和恢复。

#### Scenario: Artifact state changes
- **WHEN** 任意 task 或 artifact 被创建、更新、完成或废弃
- **THEN** 系统 MUST 记录其当前状态和关联实体
- **THEN** 后续 agent MUST 能够基于这些状态读取最新的有效 artifacts
