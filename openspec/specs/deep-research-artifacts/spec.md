## Purpose
定义 multi-agent Deep Research 在任务协作、证据沉淀和最终汇总中的结构化 artifacts 契约。
## Requirements
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
- **THEN** `blocking_gaps` MUST 只引用 authoritative verification debt、consistency debt 或真实的 outline structure gap，而 MUST NOT 直接包含 advisory `knowledge_gap`

#### Scenario: Outline gap blocks final report
- **WHEN** outline artifact 仍标记存在阻塞性的结构缺口
- **THEN** 系统 MUST 将该缺口记录为 `outline_gap` request
- **THEN** `reporter` MUST NOT 在该阻塞缺口未解决前进入最终报告生成

### Requirement: Advisory research gaps are separate from authoritative evidence debt
系统 MUST 将 advisory research gaps 与 authoritative missing evidence / verification debt 分开建模，而不是把两者混写到同一个 blocking artifact 中。

#### Scenario: Heuristic gap analysis produces planning output
- **WHEN** heuristic gap planner 识别到可补充的研究方向
- **THEN** 系统 MAY 记录 `knowledge_gap` 或等价 advisory artifact
- **THEN** 该 artifact MUST 明确表示其用途是 planning / quality hint，而不是 final-report gate

### Requirement: Coordination requests are blackboard artifacts
系统 MUST 将 follow-up request、retry hint、反证请求、结构缺口通知和工具阻塞通知表示为 blackboard 上的一等结构化 payload，而不是仅以自由文本备注存在；允许的权威 request type MUST 仅包括 `retry_branch`、`need_counterevidence`、`contradiction_found`、`outline_gap`、`blocked_by_tooling`。

#### Scenario: Research agent requests follow-up work
- **WHEN** `researcher` 发现新的研究方向、阻塞条件或需要更多预算
- **THEN** 系统 MUST 记录结构化 coordination request
- **THEN** `supervisor` MUST 能直接消费该请求而不依赖重新解析自由文本

#### Scenario: Verifier or outline stage requests corrective work
- **WHEN** `verifier` 认定某个 branch 需要补充证据、补充反证、处理矛盾，或 `outline gate` 认定报告结构仍存在缺口
- **THEN** 系统 MUST 记录结构化 coordination request，且其 request type MUST 属于允许集合
- **THEN** 系统 MUST NOT 记录开放式或未注册的 request type，也 MUST NOT 使用 `needs_human_decision` 作为本次变更的一部分

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

### Requirement: Isolated worker context
系统 MUST 为每个 `researcher` branch agent 提供独立上下文，而不是共享 sibling 的完整消息历史。

#### Scenario: Worker starts a task
- **WHEN** `researcher` branch agent 领取一个任务
- **THEN** 系统 MUST 仅向该 agent 注入共享研究 brief、任务上下文和与该任务相关的 artifacts
- **THEN** 系统 MUST NOT 默认注入其他 sibling agents 的完整消息历史

#### Scenario: Worker finishes a task
- **WHEN** `researcher` branch agent 完成任务并提交结果
- **THEN** 系统 MUST 只合并该任务产出的结构化 artifacts 和必要摘要
- **THEN** 系统 MUST NOT 将该 agent 的完整临时上下文无差别写回共享状态

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
系统 MUST 将 branch-level 验证结果表示为结构化 artifacts 或等价结构化 payload，而不是仅以自由文本备注存在；这些结果 MUST 能显式表达 coverage、矛盾和缺失证据，而不是只给出单一摘要。

#### Scenario: Claim or citation validation completes
- **WHEN** `verifier` 完成一个 branch 的 claim/citation 检查
- **THEN** 系统 MUST 记录结构化验证结果
- **THEN** 该结果 MUST 能表达检查对象、结论状态、证据引用和后续建议动作

#### Scenario: Verification produces coverage and contradiction artifacts
- **WHEN** `verifier` 完成对 branch 或整体研究的覆盖度检查
- **THEN** 系统 MUST 记录结构化 `coverage matrix`、`contradiction registry` 和 `missing evidence list`，或与其等价的正式 artifacts
- **THEN** `missing evidence list` 中的条目 MUST 能映射到未解决的 claim、obligation、consistency finding 或 revision issue，而 MUST NOT 仅来自 heuristic topic gap
- **THEN** `supervisor` 与 `outline gate` MUST 能直接消费这些 artifacts，而不依赖重新解析自然语言摘要

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
- **THEN** `verifier`、`supervisor` 和 `reporter` MUST 不依赖历史进程中的对象引用才能继续工作

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

### Requirement: Public deep research artifacts are derived from the multi-agent store
系统 MUST 从 canonical Deep Research runtime 的权威 task queue、artifact store、topology 快照和 final report 快照生成公开的 Deep Research artifacts 视图，而 MUST NOT 再依赖 `deepsearch_artifacts`、`research_plan`、`research_tree` 或其他旧顶层 fallback 字段做兼容拼装。

#### Scenario: Session or API exports public deep research artifacts
- **WHEN** `SessionManager`、API 响应或导出逻辑需要读取公开 Deep Research artifacts
- **THEN** 系统 MUST 输出 canonical artifact payload，并暴露客户端仍依赖的 `sources`、`fetched_pages`、`passages`、`claims`、`quality_summary`、最终报告和 topology 信息
- **THEN** 调用方 MUST NOT 需要解析 `deepsearch_artifacts`、`research_plan` 或 `research_tree` 才能恢复当前 Deep Research 结果

#### Scenario: Resume path rebuilds from canonical artifacts only
- **WHEN** 调用方在 interrupt、暂停或会话恢复后继续执行 Deep Research
- **THEN** 系统 MUST 仅基于 canonical public artifacts 与权威 runtime snapshot 恢复执行上下文
- **THEN** 系统 MUST NOT 再把旧的 `deepsearch_artifacts`、`research_plan`、`research_tree` 或其他兼容字段回填到顶层 state

### Requirement: Verification contracts are first-class artifacts
系统 MUST 将 claims、coverage obligations、grounding results、consistency results 和 branch revision briefs 持久化为 canonical Deep Research artifacts，而不是仅保存在 prompt、摘要文本或进程内局部变量中。

#### Scenario: Verification artifacts are persisted
- **WHEN** `researcher`、`verifier` 或 `supervisor` 创建新的 verification contract 或 revision contract
- **THEN** artifact store MUST 为其分配稳定标识并持久化其 branch / task 归属
- **THEN** checkpoint/resume MUST 能直接恢复这些 artifacts，而不需要重新从 summary 或事件日志中重建

#### Scenario: Public artifacts derive from canonical verification state
- **WHEN** Session、API 或调试工具读取公开 Deep Research artifacts
- **THEN** 系统 MUST 能从权威 artifact store 派生 claim、coverage、consistency 和 revision 相关的公开视图
- **THEN** 调用方 MUST 不需要回退到旧的自由文本摘要才能理解当前验证状态

### Requirement: Revision issue lifecycle is tracked in ledgers
系统 MUST 在 `task ledger` 与 `progress ledger` 中跟踪 revision issue 的创建、分派、解决、替代、忽略和阻塞状态。

#### Scenario: Revision issue opens or changes status
- **WHEN** 某个 revision issue 被创建、接受、解决、superseded 或 waived
- **THEN** ledgers MUST 记录其 issue 标识、目标 branch、状态和关联 artifact
- **THEN** `supervisor`、恢复逻辑和调试工具 MUST 能直接读取该状态而不依赖重新推断

#### Scenario: Revision lineage is visible from branch artifacts
- **WHEN** 某个 branch 进入修订或派生 follow-up branch
- **THEN** 相关 branch brief、task、verification artifact 和 revision brief MUST 记录 lineage 关系
- **THEN** 系统 MUST 能回答“哪个问题由哪次修订解决”而不依赖历史 agent transcript
