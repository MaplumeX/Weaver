## MODIFIED Requirements

### Requirement: Verification issues reopen bounded branch revision loops
系统 MUST 让结构化 verification issues 重新打开受控 branch revision loop，而不是把所有验证失败折叠为泛化的重试或全局 replan。

#### Scenario: Blocking verification issues require supervisor routing
- **WHEN** `verifier` 产出 blocking 的 revision issues 且预算仍允许继续研究
- **THEN** `supervisor` MUST 决定是 patch 现有 branch、派生 follow-up branch、派生 counterevidence branch，还是进入有界停止路径
- **THEN** 系统 MUST NOT 在缺少 issue-level 意图的情况下直接把该 branch 当作一次无差别重跑

#### Scenario: Advisory gaps do not reopen revision loops by themselves
- **WHEN** 剩余问题仅表现为 heuristic gap hints、coverage strengthening suggestions 或其他未映射到正式 issue 的 advisory signal
- **THEN** 系统 MUST NOT 仅凭这些信号重新打开 bounded branch revision loop
- **THEN** 若系统需要基于这些信号继续研究，必须先由 `supervisor` 将其转化为明确的 branch task 或 formal issue target

#### Scenario: Non-blocking issues do not reopen the full loop unnecessarily
- **WHEN** `verifier` 产出仅影响补充说明或弱证据的 non-blocking issues
- **THEN** `supervisor` MAY 选择记录待办、接受风险或继续进入后续阶段
- **THEN** 系统 MUST 不要求每个 non-blocking issue 都派生新的 branch 执行

### Requirement: Branch revision briefs define repair contracts
系统 MUST 用结构化 `BranchRevisionBrief` 定义每次 branch 修订需要解决的问题、允许复用的上下文和完成标准。

#### Scenario: Supervisor patches an existing branch
- **WHEN** `supervisor` 决定修补现有 branch
- **THEN** 系统 MUST 创建 `BranchRevisionBrief`
- **THEN** 该 brief MUST 至少包含 target branch、target task、issue ids、建议动作、允许复用的已有证据和修订完成标准

#### Scenario: Supervisor spawns counterevidence or follow-up work
- **WHEN** `supervisor` 决定为某个 issue 派生 counterevidence 或 follow-up branch
- **THEN** 系统 MUST 创建引用源 issue 的 `BranchRevisionBrief`
- **THEN** 下游 branch MUST 能基于该 brief 理解自己是对既有 branch 的补充、反证还是替代，而不是一个无上下文的新任务

#### Scenario: Partially satisfied coverage remains non-blocking by default
- **WHEN** 某个 `CoverageObligation` 被判定为 `partially_satisfied` 且不存在与之关联的 blocking contradiction 或 unresolved claim debt
- **THEN** 系统 MUST 默认将由此派生的 follow-up 视为 non-blocking revision work
- **THEN** 只有在 `supervisor` 明确升级该风险时，它才 MAY 阻断最终报告
