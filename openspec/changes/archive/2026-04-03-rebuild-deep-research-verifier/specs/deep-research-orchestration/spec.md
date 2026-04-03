## MODIFIED Requirements

### Requirement: Outline gate blocks final report until structure is ready
系统 MUST 在最终 `report` 前执行一个独立的 `outline gate`，并要求该 gate 只消费已验证 branch synthesis 与权威 validation 汇总来生成最终报告大纲。

#### Scenario: Outline is generated from verified inputs
- **WHEN** `supervisor` 判断研究事实层面已经具备进入写作准备的条件
- **THEN** 系统 MUST 先运行 `outline gate` 生成结构化 outline artifact
- **THEN** `outline gate` MUST 读取每个 branch 的 `BranchValidationSummary` 或等价权威 validation 汇总
- **THEN** `reporter` MUST NOT 在 outline artifact 尚未生成前直接开始最终报告汇总

#### Scenario: Outline gaps reopen the research loop
- **WHEN** `outline gate` 判断当前已验证 branch 结论不足以支撑完整报告结构
- **THEN** 系统 MUST 记录结构化 `outline_gap` request 并把控制权交回 `supervisor`
- **THEN** `supervisor` MUST 决定补充研究、重排现有任务，或停止继续推进报告生成

### Requirement: Advisory gap planning is non-gating
系统 MAY 在 Deep Research runtime 中保留 heuristic gap planning，但该能力 MUST 作为非权威的 reflection pass 存在，而不是 validation gate 的一部分。

#### Scenario: Verify stage emits planning hints
- **WHEN** validation 或其后置 reflection 阶段识别到可补强的研究方向
- **THEN** 系统 MAY 记录 advisory `suggested_queries`、reflection notes 或 equivalent planning hints
- **THEN** 这些 hints MUST NOT 单独阻止流程进入 `outline_gate` 或 `report`

### Requirement: Verification is a structured multi-pass pipeline
系统 MUST 将 `verify` 实现为结构化多阶段流水线，至少覆盖 contract check、evidence admissibility、answer-unit validation、obligation coverage evaluation、scoped consistency evaluation 和 branch validation summary aggregation。

#### Scenario: Verify stage runs after branch merge
- **WHEN** 一个或多个 branch bundle 被 graph merge 接收后进入 `verify`
- **THEN** 系统 MUST 运行结构化的 contract check、evidence admissibility、answer-unit validation、coverage、consistency 和 summary aggregation 阶段，或与之等价的 graph-controlled 子阶段
- **THEN** `supervisor` 接收到的输入 MUST 不只是 summary 文本、gap 数量或粗粒度 pass/fail 状态
- **THEN** 系统 MUST NOT 通过重新抽取 `branch_synthesis.summary` 作为权威 answer targets
- **THEN** 若系统运行了额外的 reflection pass，该 pass MUST 只产出 advisory hints，而 MUST NOT 替代上述权威阶段

#### Scenario: Verify stage remains checkpoint-safe
- **WHEN** 验证流水线在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 能恢复当前验证子阶段、待处理的 answer unit / obligation / issue 上下文和已完成的验证结果
- **THEN** 恢复后的验证 MUST 不会把同一 branch 误表示为一轮全新的无关检查

### Requirement: Blocking revision issues gate outline and report
系统 MUST 在存在未解决 blocking revision issues 时阻止流程直接进入 outline gate 或 final report，除非 `supervisor` 明确给出 bounded stop 或风险接受决策。

#### Scenario: Supervisor receives blocking issues
- **WHEN** `supervisor` 决策输入中存在 blocking 的 revision issues
- **THEN** 系统 MUST 优先回到 patch / follow-up / counterevidence 路径
- **THEN** 系统 MUST NOT 在这些 issues 仍未解决时直接把控制权交给 `reporter`

#### Scenario: Outline gate sees unresolved verification debt
- **WHEN** `outline gate` 启动时仍存在未解决的 blocking validation debt
- **THEN** 系统 MUST 将这些问题视为阻塞性结构前提问题或等价阻塞状态
- **THEN** `outline gate` MUST 不将其静默忽略并直接生成可写作的最终 outline
- **THEN** 系统 MUST NOT 因为 advisory reflection、派生 blocker 列表重复记录了同一问题，就重复升级阻塞状态

#### Scenario: Outline gate receives advisory gaps only
- **WHEN** `outline gate` 看到的剩余缺口仅来自 heuristic planning、弱覆盖建议或其他未映射到正式 issue 的 advisory signal
- **THEN** 它 MUST NOT 将这些信号直接视为 blocking validation debt
- **THEN** 系统 MAY 将这些信号传递给 `supervisor` 或 UI 作为补强建议，但 MUST 允许流程继续进入最终报告

## ADDED Requirements

### Requirement: Reflection, validation and evaluation are separated
系统 MUST 将 Deep Research 中的 reflection、runtime validation 和 final evaluation 视为三个职责不同的阶段，而不是让单个 verifier 同时承担 planning hint、事实裁决和最终报告评测。

#### Scenario: Runtime needs more research direction
- **WHEN** 系统在 branch 或全局层面识别到可补强的研究方向
- **THEN** 它 MUST 通过 reflection pass 产出 advisory hints
- **THEN** 这些 hints MUST 不直接改变已存在的 authoritative validation verdict

#### Scenario: Final report quality is assessed
- **WHEN** 系统需要对最终报告执行 citation、completeness 或 factuality 评估
- **THEN** 它 MUST 在 runtime validation 之后执行独立 evaluation pass，或暴露等价的离线评测入口
- **THEN** 该 evaluation pass MUST 不替代 branch-level authoritative validation contract
