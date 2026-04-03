## ADDED Requirements

### Requirement: Verification contracts are explicit and claim-addressable
系统 MUST 将 branch 级验证输入与输出表示为结构化 verification contracts，而不是只依赖自由文本 summary 作为权威检查对象。

#### Scenario: Researcher submits a verification-ready branch bundle
- **WHEN** `researcher` 提交 branch research 或 revision 结果 bundle
- **THEN** 该 bundle MUST 包含结构化 `ClaimUnit` 列表，或显式声明该 branch 不产出可验证 claim
- **THEN** 每个 `ClaimUnit` MUST 至少包含稳定标识、`branch_id`、`task_id`、claim 文本、claim provenance 和关联证据引用

#### Scenario: Verifier consumes structured verification targets
- **WHEN** `verifier` 开始检查某个 branch bundle
- **THEN** 它 MUST 直接消费 `ClaimUnit` 与 `CoverageObligation` 作为权威检查目标
- **THEN** 系统 MUST NOT 仅通过重新解析 `branch_synthesis.summary` 临时猜测需要验证的 claim 或 coverage 维度

### Requirement: Coverage obligations are derived from the authoritative brief
系统 MUST 从权威 `research brief`、branch task 契约和经批准的 revision delta 派生 coverage obligations，并用这些 obligations 驱动覆盖判断。

#### Scenario: Supervisor creates or revises a branch contract
- **WHEN** `supervisor` 创建初始 branch task，或批准某次 branch revision
- **THEN** 系统 MUST 生成或刷新该 branch 的结构化 `CoverageObligation`
- **THEN** 每个 obligation MUST 能表达 obligation 标识、来源、目标问题或维度、完成标准和关联 branch

#### Scenario: Verifier evaluates obligation fulfillment
- **WHEN** `verifier` 执行 coverage 评估
- **THEN** 它 MUST 为每个 obligation 产出结构化 fulfillment 结果
- **THEN** 结果 MUST 能表达 satisfied、partially_satisfied、unsatisfied 或 unresolved 等状态，以及对应的证据引用

### Requirement: Verification findings are evidence-backed and issue-oriented
系统 MUST 将验证失败、未决与矛盾结果表示为结构化 findings 与 revision issues，使 `supervisor` 可直接据此决策。

#### Scenario: Claim grounding produces a corrective issue
- **WHEN** 某个 claim 被判定为 contradicted、unsupported 或 unresolved
- **THEN** 系统 MUST 生成结构化 finding 与对应 revision issue
- **THEN** 该 issue MUST 至少包含 issue 标识、issue 类型、受影响的 claim 标识、相关证据引用、严重级别和建议动作

#### Scenario: Coverage evaluation produces a corrective issue
- **WHEN** 某个 coverage obligation 未满足或只有部分满足
- **THEN** 系统 MUST 生成结构化 finding 与对应 revision issue
- **THEN** `supervisor` MUST 能在不重新解析自然语言摘要的情况下知道缺失的 obligation、建议补证据方向和影响范围

### Requirement: Cross-branch consistency is checked before final reporting
系统 MUST 在最终进入 outline/report 之前执行 cross-branch consistency evaluation，并把 branch 之间的冲突显式沉淀为结构化结果。

#### Scenario: Multiple branches make overlapping claims
- **WHEN** 两个或更多 branch 对同一研究问题、比较维度或结论范围提交了可比较的 claims
- **THEN** 系统 MUST 执行一致性检查并生成结构化 `ConsistencyResult`
- **THEN** 若发现冲突，系统 MUST 将其记录为 blocking revision issue 或等价阻塞状态

#### Scenario: Reporter waits for consistency resolution
- **WHEN** 当前研究仍存在未解决的 blocking consistency findings
- **THEN** 系统 MUST 阻止这些 findings 被直接提升为最终报告事实依据
- **THEN** `reporter` MUST 只消费已解决、被 `supervisor` 接受，或被明确标记为可保留争议的结果
