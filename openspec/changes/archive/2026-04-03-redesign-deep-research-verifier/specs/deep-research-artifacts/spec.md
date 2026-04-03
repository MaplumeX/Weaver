## ADDED Requirements

### Requirement: Advisory research gaps are separate from authoritative evidence debt
系统 MUST 将 advisory research gaps 与 authoritative missing evidence / verification debt 分开建模，而不是把两者混写到同一个 blocking artifact 中。

#### Scenario: Heuristic gap analysis produces planning output
- **WHEN** heuristic gap planner 识别到可补充的研究方向
- **THEN** 系统 MAY 记录 `knowledge_gap` 或等价 advisory artifact
- **THEN** 该 artifact MUST 明确表示其用途是 planning / quality hint，而不是 final-report gate

## MODIFIED Requirements

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
