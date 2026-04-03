## ADDED Requirements

### Requirement: Verifier is a bounded adjudication role over structured contracts
系统 MUST 将 `verifier` 保持为 graph-controlled 的执行型角色，但其职责应围绕结构化 verification contracts 做裁决，而不是重新定义研究 scope 或 branch contract。

#### Scenario: Verifier executes on a branch bundle
- **WHEN** `verifier` 被触发检查某个 branch bundle
- **THEN** 它 MUST 读取该 branch 的 claims、obligations、grounding context 和 consistency context
- **THEN** 它 MUST NOT 通过自由文本 prompt 临时改写该 branch 的权威研究目标或 scope 边界

#### Scenario: Verifier requests corrective work
- **WHEN** `verifier` 认定需要补证据、反证或修订
- **THEN** 它 MUST 通过结构化 findings、issues 或受限 request 把控制权交回 `supervisor`
- **THEN** 它 MUST NOT 直接绕过 graph 创建新的 task topology

### Requirement: Supervisor owns revision routing decisions
系统 MUST 让 `supervisor` 成为唯一可以决定 patch existing branch、spawn follow-up branch、spawn counterevidence branch 或 bounded stop 的控制平面角色。

#### Scenario: Corrective work is required
- **WHEN** 当前研究存在 unresolved revision issues
- **THEN** 只有 `supervisor` MAY 决定这些 issues 由哪个 branch 或哪个新任务处理
- **THEN** `researcher` 与 `verifier` MUST NOT 直接修改任务拓扑或共享权威状态

#### Scenario: Reporter consumes resolved verification state
- **WHEN** `reporter` 进入 outline 或 final report handoff
- **THEN** 它 MUST 只消费已经过 `supervisor` 决策收敛的 verification state
- **THEN** 它 MUST NOT 自行解释 unresolved issues 为“可忽略”并绕过控制平面
