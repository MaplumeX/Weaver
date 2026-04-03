## ADDED Requirements

### Requirement: Verification is a structured multi-pass pipeline
系统 MUST 将 `verify` 实现为结构化多阶段流水线，至少覆盖 claim grounding、coverage obligation evaluation、cross-branch consistency evaluation 和 revision issue aggregation。

#### Scenario: Verify stage runs after branch merge
- **WHEN** 一个或多个 branch bundle 被 graph merge 接收后进入 `verify`
- **THEN** 系统 MUST 运行结构化的 grounding、coverage、consistency 和 issue aggregation 阶段，或与之等价的 graph-controlled 子阶段
- **THEN** `supervisor` 接收到的输入 MUST 不只是 summary 文本、gap 数量或粗粒度 pass/fail 状态

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
