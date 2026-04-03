## MODIFIED Requirements

### Requirement: Outline artifacts gate final reporting
系统 MUST 将最终报告前的大纲整理结果表示为结构化 artifact，并让该 artifact 成为 `reporter` 进入最终成文阶段的必经 handoff。

#### Scenario: Outline artifact is created from verified research
- **WHEN** 系统进入最终写作准备阶段
- **THEN** 系统 MUST 记录结构化 outline artifact
- **THEN** 该 artifact MUST 能表达章节结构、每节对应的 branch/证据引用和仍待补足的结构缺口
- **THEN** `blocking_gaps` MUST 只引用 `BranchValidationSummary` 中的 authoritative validation debt、已确认的 consistency debt 或真实的 outline structure gap，而 MUST NOT 直接包含 advisory reflection artifact 或重复聚合的 blocker 视图

#### Scenario: Outline gap blocks final report
- **WHEN** outline artifact 仍标记存在阻塞性的结构缺口
- **THEN** 系统 MUST 将该缺口记录为 `outline_gap` request
- **THEN** `reporter` MUST NOT 在该阻塞缺口未解决前进入最终报告生成

### Requirement: Advisory research gaps are separate from authoritative evidence debt
系统 MUST 将 advisory research gaps 与 authoritative missing evidence / validation debt 分开建模，而不是把两者混写到同一个 blocking artifact 中。

#### Scenario: Heuristic gap analysis produces planning output
- **WHEN** heuristic gap planner 或等价 reflection 层识别到可补充的研究方向
- **THEN** 系统 MUST 将其记录为 advisory artifact
- **THEN** 该 artifact MUST 明确表示其用途是 planning / quality hint，而不是 final-report gate

#### Scenario: Validation debt is materialized for runtime gates
- **WHEN** 某个 branch 存在 required unsupported units、contradicted units、未覆盖 obligations 或未解决 consistency findings
- **THEN** 系统 MUST 将这些问题记录为 authoritative validation debt
- **THEN** outline gate 和 reporter MUST 只基于这些权威 debt 判定是否阻塞，而 MUST NOT 把 advisory reflection 当作等价 blocker

### Requirement: Evidence-backed synthesis
系统 MUST 基于结构化证据产物和验证结果完成质量判断与最终报告生成，而不是直接基于未经验证的中间摘要完成汇总。

#### Scenario: Verifier evaluates branch conclusions
- **WHEN** `verifier` 检查某个 branch synthesis 的 claim、citation、coverage 或来源可信度
- **THEN** 系统 MUST 基于已有 `EvidencePassage`、抓取文档、来源元数据和 branch 任务状态执行判断
- **THEN** verifier 产出的验证结论 MUST 可被 `supervisor`、outline gate 和 `reporter` 直接消费

#### Scenario: Reporter generates the final report
- **WHEN** `reporter` 生成最终研究报告
- **THEN** 系统 MUST 仅使用共享 artifact store 中已验证、可追溯的 answer units、branch validation summary 和证据作为事实依据
- **THEN** 系统 MUST 为报告输出可关联到分支证据来源的引用信息

### Requirement: Verification artifacts are first-class handoff payloads
系统 MUST 将 branch-level 验证结果表示为结构化 artifacts 或等价结构化 payload，而不是仅以自由文本备注存在；这些结果 MUST 能显式表达 coverage、矛盾和缺失证据，而不是只给出单一摘要。

#### Scenario: Claim or citation validation completes
- **WHEN** `verifier` 完成一个 branch 的 answer-unit / citation 检查
- **THEN** 系统 MUST 记录结构化验证结果
- **THEN** 该结果 MUST 能表达检查对象、结论状态、证据引用和后续建议动作

#### Scenario: Verification produces coverage and contradiction artifacts
- **WHEN** `verifier` 完成对 branch 或整体研究的覆盖度检查
- **THEN** 系统 MUST 记录结构化 `coverage matrix`、`contradiction registry`、`missing evidence list` 和 `BranchValidationSummary`，或与其等价的正式 artifacts
- **THEN** `missing evidence list` 中的条目 MUST 能映射到未解决的 answer unit、obligation、consistency finding 或 revision issue，而 MUST NOT 仅来自 heuristic reflection
- **THEN** `supervisor`、outline gate 和 `reporter` MUST 能直接消费这些 artifacts，而不依赖重新解析自然语言摘要

## ADDED Requirements

### Requirement: Evidence artifacts distinguish search leads from admissible passages
系统 MUST 将搜索召回线索、抓取文档和权威证据 passage 分开建模，避免 snippet 直接进入验证层。

#### Scenario: Search results are persisted
- **WHEN** `researcher` 或 `verifier` 完成搜索
- **THEN** 系统 MUST 将搜索结果保存为 search leads 或 source candidates
- **THEN** 这些 artifacts MAY 包含摘要或 snippet，但 MUST NOT 被标记为 authoritative evidence

#### Scenario: Extracted passages are persisted
- **WHEN** 系统从来源文档中提取出用于验证的正文片段
- **THEN** 系统 MUST 将其记录为 `EvidencePassage`
- **THEN** 每个 `EvidencePassage` MUST 能追溯到来源文档、来源 URL 和最小 locator metadata

### Requirement: Branch validation summary is the canonical runtime handoff
系统 MUST 为每个 branch 产出唯一的 canonical `BranchValidationSummary`，作为 supervisor、outline gate 和 reporter 的权威读取入口。

#### Scenario: Branch validation finishes
- **WHEN** 某个 branch 的 validation pass 完成
- **THEN** 系统 MUST 生成或刷新该 branch 的 `BranchValidationSummary`
- **THEN** 该汇总 MUST 表达 supported / unsupported / contradicted answer units、obligation coverage 状态、consistency findings、blocking debt 和 advisory notes

#### Scenario: Downstream stages read validation state
- **WHEN** `supervisor`、outline gate 或 `reporter` 需要理解某个 branch 的当前验证状态
- **THEN** 它们 MUST 首先读取 `BranchValidationSummary`
- **THEN** 它们 MUST NOT 再从 `branch_synthesis.summary`、零散 issue 列表或重复 blocker 聚合中自行重建权威状态
