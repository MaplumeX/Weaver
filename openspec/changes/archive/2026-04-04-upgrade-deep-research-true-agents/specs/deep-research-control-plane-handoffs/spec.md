## ADDED Requirements

### Requirement: Control-plane ownership is explicit
系统 MUST 将 Deep Research 控制平面的当前 owner 建模为显式状态，而不是只通过隐式 graph 节点或 `next_step` 推断。

#### Scenario: Intake starts with an active control-plane agent
- **WHEN** 一个新的 `multi_agent` Deep Research 请求进入 runtime
- **THEN** 系统 MUST 将 `clarify` 记录为当前 `active_agent`，或在已有充分 intake 上下文时将 `scope` / `supervisor` 记录为当前 `active_agent`
- **THEN** 系统 MUST 能从权威状态中直接读取当前由哪个 control-plane agent 持有控制权

#### Scenario: Scope revision changes control-plane ownership
- **WHEN** `supervisor` 决定当前 scope 仍需修改并将流程退回范围整理阶段
- **THEN** 系统 MUST 将控制权显式 handoff 给 `scope`
- **THEN** 该次移交 MUST 不依赖重新解析自由文本历史才能理解是谁发起了移交以及为什么退回

### Requirement: Handoff payloads are structured and checkpoint-safe
系统 MUST 为每次 control-plane handoff 生成结构化 payload，并在 checkpoint/resume 后恢复最新 owner 与移交上下文。

#### Scenario: Handoff records structured context references
- **WHEN** `clarify`、`scope` 或 `supervisor` 发起 control-plane handoff
- **THEN** payload MUST 至少包含 `from_agent`、`to_agent`、`reason`、`context_refs` 和时间戳，且在适用时引用 scope draft、research brief、review 状态或相关 artifact
- **THEN** 下游 control-plane agent MUST 不需要从完整原始消息历史中重新推断本次 handoff 的最小上下文

#### Scenario: Resume restores the latest handoff owner
- **WHEN** runtime 在 handoff 之后发生 interrupt、checkpoint 恢复或进程重启
- **THEN** 系统 MUST 恢复最近一次权威 handoff 对应的 `active_agent` 与 payload
- **THEN** 恢复后的执行 MUST 不会把同一研究错误表示为新的无关 control-plane 会话

### Requirement: Supervisor remains the canonical global control-plane owner
系统 MUST 让 `supervisor` 成为唯一可以接入执行平面、进入报告收敛回路或把执行反馈升级为新的 control-plane handoff 的全局 owner。

#### Scenario: Intake roles return control to supervisor
- **WHEN** `clarify` 确认 intake 足够进入 scope，或 `scope` 产生已批准范围与 brief handoff
- **THEN** 控制权 MUST 依次 handoff 到下一个 control-plane role，并最终回到 `supervisor`
- **THEN** 只有 `supervisor` MAY 继续进入计划、调度、outline gate 或报告阶段

#### Scenario: Execution feedback cannot bypass supervisor ownership
- **WHEN** `researcher`、`verifier` 或 `reporter` 发现需要补充研究、修订或结构回退
- **THEN** 它们 MUST 通过 request、issue、bundle 或 report artifact 提交结构化反馈
- **THEN** 只有 `supervisor` MAY 决定是否将该反馈转换为新的 control-plane handoff

