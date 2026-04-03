## ADDED Requirements

### Requirement: Heuristic gap analysis is advisory only
系统 MUST 将 topic-level 或 heuristic gap analysis 视为 research planning 的辅助信号，而不是 Deep Research verification 的权威裁决来源。

#### Scenario: Gap planner runs after a verification pass
- **WHEN** 系统在 branch merge 后运行启发式 gap analysis
- **THEN** 它 MAY 生成 `suggested_queries`、coverage hints 或 quality notes
- **THEN** 这些输出 MUST NOT 在没有映射到结构化 claim、obligation、consistency finding 或 revision issue 的前提下直接降低 authoritative verification verdict

#### Scenario: Advisory gap conflicts with satisfied obligations
- **WHEN** 某个 heuristic gap 提示仍声称研究“coverage incomplete”，但相关 `CoverageObligation` 已被结构化 verifier 判定为 `satisfied`
- **THEN** 系统 MUST 保留已满足的 obligation verdict 作为权威结果
- **THEN** heuristic gap MUST 仅作为后续搜索建议保留，而 MUST NOT 重新打开 blocking verification debt

## MODIFIED Requirements

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
- **THEN** 系统 MUST NOT 让启发式 gap analyzer 覆盖、降格或重写已有的结构化 verification verdict

### Requirement: Coverage obligations are derived from the authoritative brief
系统 MUST 从权威 `research brief`、branch task 契约和经批准的 revision delta 派生 coverage obligations，并用这些 obligations 驱动覆盖判断。

#### Scenario: Supervisor creates or revises a branch contract
- **WHEN** `supervisor` 创建初始 branch task，或批准某次 branch revision
- **THEN** 系统 MUST 生成或刷新该 branch 的结构化 `CoverageObligation`
- **THEN** 每个 obligation MUST 能表达 obligation 标识、来源、目标问题或维度、完成标准和关联 branch

#### Scenario: Verifier evaluates obligation fulfillment
- **WHEN** `verifier` 执行 coverage 评估
- **THEN** 它 MUST 为每个 obligation 产出结构化 fulfillment 结果
- **THEN** 结果 MUST 能表达 `satisfied`、`partially_satisfied`、`unsatisfied` 或 `unresolved` 状态，以及对应的证据引用或缺失标准
- **THEN** 系统 MUST 基于 grounded claims、evidence passages、citations 和 completion criteria 做出该判定，而 MUST NOT 仅依赖 topic overlap、summary 关键词或通用 topic checklist

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
- **THEN** issue 的 blocking 语义 MUST 由 obligation status 与明确的 severity 决定，而 MUST NOT 因为存在未映射到 contract 的 heuristic gap 就自动升级为 blocking
