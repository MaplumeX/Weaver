## MODIFIED Requirements

### Requirement: Verification contracts are explicit and claim-addressable
系统 MUST 将 branch 级验证输入与输出表示为结构化、unit-addressable verification contracts，而不是只依赖自由文本 summary 作为权威检查对象。

#### Scenario: Researcher submits a verification-ready branch bundle
- **WHEN** `researcher` 提交 branch research 或 revision 结果 bundle
- **THEN** 该 bundle MUST 包含结构化 `AnswerUnit` 列表，或显式声明该 branch 不产出可验证 answer units
- **THEN** 每个 `AnswerUnit` MUST 至少包含稳定标识、`branch_id`、`task_id`、`unit_type`、答案文本、provenance、关联 `obligation_ids` 和关联证据引用
- **THEN** 若某个答案单元是组合结论，它 MUST 声明其依赖的原子 answer unit 标识，而 MUST NOT 只以自由文本 summary 形式提交

#### Scenario: Verifier consumes structured verification targets
- **WHEN** `verifier` 开始检查某个 branch bundle
- **THEN** 它 MUST 直接消费 `AnswerUnit` 与 `CoverageObligation` 作为权威检查目标
- **THEN** 系统 MUST NOT 通过重新解析 `branch_synthesis.summary`、`findings` 或等价摘要文本临时猜测需要验证的对象
- **THEN** 系统 MUST NOT 让启发式 gap analysis 覆盖、降格或重写已有的结构化 validation verdict

### Requirement: Coverage obligations are derived from the authoritative brief
系统 MUST 从权威 `research brief`、branch task 契约和经批准的 revision delta 派生 coverage obligations，并基于 obligation-to-answer-unit mapping 驱动覆盖判断。

#### Scenario: Supervisor creates or revises a branch contract
- **WHEN** `supervisor` 创建初始 branch task，或批准某次 branch revision
- **THEN** 系统 MUST 生成或刷新该 branch 的结构化 `CoverageObligation`
- **THEN** 每个 obligation MUST 能表达 obligation 标识、来源、目标问题或维度、完成标准和关联 branch

#### Scenario: Verifier evaluates obligation fulfillment
- **WHEN** `verifier` 执行 coverage 评估
- **THEN** 它 MUST 为每个 obligation 产出结构化 fulfillment 结果
- **THEN** 结果 MUST 能表达 `satisfied`、`partially_satisfied`、`unsatisfied` 或 `unresolved` 状态，以及对应的证据引用、相关 `AnswerUnit` 标识和缺失标准
- **THEN** 系统 MUST 基于 obligation 映射、已支持的 `AnswerUnit`、`EvidencePassage` 和 completion criteria 做出该判定，而 MUST NOT 仅依赖 topic overlap、summary 关键词或 token overlap

### Requirement: Heuristic gap analysis is advisory only
系统 MUST 将 topic-level 或 heuristic gap analysis 视为 research planning 的辅助信号，而不是 Deep Research validation 的权威裁决来源。

#### Scenario: Reflection pass runs after validation
- **WHEN** 系统在一次 validation pass 之后运行 heuristic gap analysis 或等价 reflection
- **THEN** 它 MUST 只产出 advisory `suggested_queries`、reflection notes 或 coverage hints
- **THEN** 这些输出 MUST NOT 在没有映射到 `AnswerUnit`、`CoverageObligation`、`ConsistencyResult` 或正式 revision issue 的前提下直接创建 blocking debt

#### Scenario: Advisory gap conflicts with satisfied obligations
- **WHEN** 某个 heuristic gap 仍声称研究 coverage 不完整，但相关 `CoverageObligation` 已被结构化 verifier 判定为 `satisfied`
- **THEN** 系统 MUST 保留已满足的 obligation verdict 作为权威结果
- **THEN** heuristic gap MUST 只作为后续搜索建议保留，而 MUST NOT 重新打开 blocking validation debt

### Requirement: Verification findings are evidence-backed and issue-oriented
系统 MUST 将验证失败、未决与矛盾结果表示为结构化 findings 与 revision issues，使 `supervisor` 可直接据此决策。

#### Scenario: Answer-unit validation produces a corrective issue
- **WHEN** 某个 `AnswerUnit` 被判定为 `contradicted`、`unsupported` 或 `unresolved`
- **THEN** 系统 MUST 生成结构化 finding 与对应 revision issue
- **THEN** 该 issue MUST 至少包含 issue 标识、issue 类型、受影响的 answer unit 标识、相关证据引用、严重级别和建议动作
- **THEN** issue 的 blocking 语义 MUST 由该 answer unit 的 required 性和明确 severity 决定，而 MUST NOT 因为存在未映射的 heuristic gap 自动升级

#### Scenario: Coverage evaluation produces a corrective issue
- **WHEN** 某个 coverage obligation 未满足或只有部分满足
- **THEN** 系统 MUST 生成结构化 finding 与对应 revision issue
- **THEN** `supervisor` MUST 能在不重新解析自然语言摘要的情况下知道缺失的 obligation、未支持的 answer units、建议补证据方向和影响范围

### Requirement: Cross-branch consistency is checked before final reporting
系统 MUST 在最终进入 outline/report 之前执行 cross-branch consistency evaluation，并把 branch 之间的冲突显式沉淀为结构化结果。

#### Scenario: Multiple branches make comparable answer units
- **WHEN** 两个或更多 branch 对同一实体、时间范围、比较维度或 obligation 范围提交了可比较的 answer units
- **THEN** 系统 MUST 执行 scoped consistency check 并生成结构化 `ConsistencyResult`
- **THEN** 若发现冲突，系统 MUST 将其记录为 blocking revision issue 或等价阻塞状态
- **THEN** 系统 MUST NOT 仅因词面相似就把无共同实体、范围或 obligation 的 answer units 判为冲突

#### Scenario: Reporter waits for consistency resolution
- **WHEN** 当前研究仍存在未解决的 blocking consistency findings
- **THEN** 系统 MUST 阻止这些 findings 被直接提升为最终报告事实依据
- **THEN** `reporter` MUST 只消费已解决、被 `supervisor` 接受，或被明确标记为可保留争议的结果

## ADDED Requirements

### Requirement: Authoritative evidence is passage-based and admissible
系统 MUST 将权威验证证据限制为稳定、可追溯的 `EvidencePassage`，而不是搜索结果 snippet 或自由文本摘要。

#### Scenario: Verifier receives candidate evidence
- **WHEN** 任一 branch 向 `verifier` 提交用于 grounding 的证据
- **THEN** 每条权威证据 MUST 具有稳定的 passage 标识、来源文档或来源 URL、原文文本或引文、来源标题以及最小 locator metadata
- **THEN** verifier MUST 拒绝仅包含 `summary`、`snippet`、`raw_excerpt` 或其他不稳定摘录且缺少稳定 passage metadata 的证据作为 authoritative grounding 输入

#### Scenario: Search results are available before extraction
- **WHEN** 系统刚完成搜索但尚未提取稳定 passage
- **THEN** 系统 MUST 将这些结果视为搜索线索或 source candidate
- **THEN** 系统 MUST NOT 直接用这些线索生成 authoritative validation verdict

### Requirement: Validation verdicts are unit-scoped and non-broadcast
系统 MUST 让 validation verdict 与具体 answer units、obligations 或 consistency findings 一一对应，而不是把单个 verdict 广播到整批 branch 对象。

#### Scenario: Verifier or tool-agent submits a verdict
- **WHEN** `verifier` 或 verifier tool-agent 提交 grounding、coverage 或 consistency 结果
- **THEN** 该结果 MUST 显式引用适用的 `AnswerUnit` 标识、`CoverageObligation` 标识或 `ConsistencyResult` 标识
- **THEN** 系统 MUST NOT 因为一个 branch 级 outcome 就把相同 verdict 自动应用到未被显式引用的对象

#### Scenario: Branch-level summary is produced
- **WHEN** 系统生成 branch 级验证摘要
- **THEN** 该摘要 MUST 由 unit-scoped 结果聚合得到
- **THEN** 系统 MUST NOT 倒过来根据 branch summary 去推断或重写 unit-level verdict
