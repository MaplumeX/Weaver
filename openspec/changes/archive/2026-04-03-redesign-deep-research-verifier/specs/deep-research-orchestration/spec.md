## ADDED Requirements

### Requirement: Advisory gap planning is non-gating
系统 MAY 在 Deep Research runtime 中保留 heuristic gap planning，但该能力 MUST 作为非权威的 planning pass 存在，而不是 verification gate 的一部分。

#### Scenario: Verify stage emits planning hints
- **WHEN** verify 或其后置质量分析阶段识别到可补强的研究方向
- **THEN** 系统 MAY 记录 advisory `suggested_queries` 或 equivalent planning hints
- **THEN** 这些 hints MUST NOT 单独阻止流程进入 `outline_gate` 或 `report`

## MODIFIED Requirements

### Requirement: Supervisor-controlled research loop
系统 MUST 由 `supervisor` 独占 multi-agent Deep Research 的规划与循环控制语义，并通过显式 graph 转移驱动 clarify、scope、scope review、`research brief` handoff、branch dispatch、验证、outline gate、汇总和结束阶段；系统 MUST NOT 再公开或保留独立 `coordinator` 角色、outer hierarchical path 或等价兼容控制面。

#### Scenario: Supervisor waits for approved brief before dispatch
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** 系统 MUST 先完成 clarify/scoping、scope review 和 `research brief` 生成
- **THEN** `supervisor` MUST 只在权威 `research brief` 就绪后，才将 branch 级任务写入可调度队列并分配唯一任务标识

#### Scenario: Supervisor replans from verifier or outline feedback
- **WHEN** `verifier` 产出了新的 blocking revision issues、未解决的 obligation debt、矛盾记录、缺失证据列表或 `outline gate` 产出了 `outline_gap` 请求且预算仍允许继续研究
- **THEN** `supervisor` MUST 基于当前 brief、ledger 和权威 verification 结果决定是否触发 replan
- **THEN** 系统 MAY 使用 advisory gap hints 辅助决定后续搜索方向，但 MUST NOT 仅凭 advisory gaps 把流程判定为仍不可报告

#### Scenario: Supervisor owns orchestration decisions directly
- **WHEN** runtime 需要决定继续研究、触发 replan、重试 branch、开始 outline 生成、开始汇总或停止
- **THEN** 系统 MUST 由 `supervisor` 直接产出这些决策
- **THEN** 系统 MUST NOT 再暴露 `coordinator` 角色、`coordinator_action` 状态或等价兼容决策分支

### Requirement: Verification is a structured multi-pass pipeline
系统 MUST 将 `verify` 实现为结构化多阶段流水线，至少覆盖 claim grounding、coverage obligation evaluation、cross-branch consistency evaluation 和 revision issue aggregation。

#### Scenario: Verify stage runs after branch merge
- **WHEN** 一个或多个 branch bundle 被 graph merge 接收后进入 `verify`
- **THEN** 系统 MUST 运行结构化的 grounding、coverage、consistency 和 issue aggregation 阶段，或与之等价的 graph-controlled 子阶段
- **THEN** `supervisor` 接收到的输入 MUST 不只是 summary 文本、gap 数量或粗粒度 pass/fail 状态
- **THEN** 若系统运行了额外的 heuristic gap planning，该 planning pass MUST 只产出 advisory hints，而 MUST NOT 替代上述权威阶段

#### Scenario: Verify stage remains checkpoint-safe
- **WHEN** 验证流水线在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 能恢复当前验证子阶段、待处理的 claim / obligation / issue 上下文和已完成的验证结果
- **THEN** 恢复后的验证 MUST 不会把同一 branch 误表示为一轮全新的无关检查

### Requirement: Blocking revision issues gate outline and report
系统 MUST 在存在未解决 blocking revision issues 时阻止流程直接进入 outline gate 或 final report，除非 `supervisor` 明确给出 bounded stop 或风险接受决策。

#### Scenario: Supervisor receives blocking issues
- **WHEN** `supervisor` 决策输入中存在 blocking 的 revision issues
- **THEN** 系统 MUST 优先回到 patch / follow-up / counterevidence 路径
- **THEN** 系统 MUST NOT 在这些 issues 仍未解决时直接把控制权交给 `reporter`

#### Scenario: Outline gate sees unresolved verification debt
- **WHEN** `outline gate` 启动时仍存在未解决的 blocking verification issues
- **THEN** 系统 MUST 将这些 issues 视为阻塞性结构前提问题或等价阻塞状态
- **THEN** `outline gate` MUST 不将其静默忽略并直接生成可写作的最终 outline

#### Scenario: Outline gate receives advisory gaps only
- **WHEN** `outline gate` 看到的剩余缺口仅来自 heuristic planning、弱覆盖建议或其他未映射到正式 issue 的 advisory signal
- **THEN** 它 MUST NOT 将这些信号直接视为 blocking verification debt
- **THEN** 系统 MAY 将这些信号传递给 `supervisor` 或 UI 作为补强建议，但 MUST 允许流程继续进入最终报告
