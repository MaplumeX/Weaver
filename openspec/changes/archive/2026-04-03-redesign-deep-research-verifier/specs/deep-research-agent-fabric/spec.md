## MODIFIED Requirements

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

#### Scenario: Verifier tool-agent submits contract-addressable verdicts
- **WHEN** bounded verifier tool-agent 提交 claim 或 coverage 裁决
- **THEN** 它 MUST 在提交中显式引用相关的 `claim_ids`、`obligation_ids`、`consistency_result_ids` 或 `issue_ids`
- **THEN** 若它声称某个 coverage 检查通过，系统 MUST 能追溯该通过结论对应了哪些 obligations 与哪些证据引用
- **THEN** 系统 MUST NOT 接受一个未绑定具体 contracts 的 blanket `passed` 裁决并据此把整条 branch 的 obligations 一次性改写为 satisfied
