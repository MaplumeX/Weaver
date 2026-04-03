## ADDED Requirements

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
