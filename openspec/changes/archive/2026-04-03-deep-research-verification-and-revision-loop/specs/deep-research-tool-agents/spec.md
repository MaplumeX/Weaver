## ADDED Requirements

### Requirement: Fabric tools expose verification contracts and revision context
系统 MUST 为 `researcher` 与 `verifier` bounded tool agents 暴露结构化 verification contracts 与 revision context，而不是只暴露 summary 文本和松散 artifact 列表。

#### Scenario: Revision-oriented researcher starts
- **WHEN** revision-oriented `researcher` tool agent 启动
- **THEN** fabric tools MUST 让它读取当前 branch 的 unresolved issues、prior claims、prior evidence 和 revision brief
- **THEN** 它 MUST 不需要从自由文本 summary 中重新推断当前修订目标

#### Scenario: Verifier tool agent adjudicates a boundary case
- **WHEN** `verifier` tool agent 被调用处理证据不足、反证冲突或一致性边界 case
- **THEN** fabric tools MUST 提供 claim ids、obligation ids、issue ids 和相关证据引用
- **THEN** tool agent MUST 围绕这些结构化对象返回结果，而不是只提交新的自由文本解释

### Requirement: Tool-agent submissions are issue-addressable
系统 MUST 要求 verifier 与 revision-oriented researcher 的 tool-agent 提交结果引用稳定的 verification object identifiers。

#### Scenario: Verifier submits a verification bundle
- **WHEN** `verifier` tool agent 提交 grounding、coverage 或 consistency 结果
- **THEN** submission MUST 在适用时引用 claim ids、obligation ids、consistency finding ids 或 issue ids
- **THEN** graph merge MUST 能据此确定性地更新 artifact store 和 ledgers

#### Scenario: Researcher submits a revision bundle
- **WHEN** revision-oriented `researcher` tool agent 提交补证据或反证结果
- **THEN** submission MUST 在适用时声明其试图解决的 issue ids 与实际解决状态
- **THEN** `supervisor` MUST 能基于该 submission 判断本轮修订是否已满足继续推进条件
