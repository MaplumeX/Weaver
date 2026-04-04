## MODIFIED Requirements

### Requirement: Deep research roles are exposed as bounded tool agents
系统 MUST 将 Deep Research 角色统一收敛为 bounded tool agents，但角色类型 MUST 分为 control-plane handoff agents 与 execution subagents 两类：`clarify`、`scope`、`supervisor` 属于前者，`researcher`、`verifier`、`reporter` 属于后者。

#### Scenario: Clarify and scope use fabric-only tools
- **WHEN** `clarify` 或 `scope` agent 执行 intake、范围整理或审阅交接
- **THEN** 系统 MUST 仅向它们暴露与用户上下文、scope 草案、handoff 和审阅动作相关的 fabric tools
- **THEN** 系统 MUST NOT 向它们暴露 world-facing 的搜索、浏览、抓取或抽取工具

#### Scenario: Supervisor uses control-plane-only tools
- **WHEN** `supervisor` agent 启动
- **THEN** 系统 MUST 向它暴露读取 brief/ledger/artifact、提交决策、提交 handoff 和派发 subagent 所需的受限工具表面
- **THEN** `supervisor` MUST NOT 因为持有全局控制权而自动获得不受约束的 world-facing 工具权限

#### Scenario: Execution agents use role-specific world tools
- **WHEN** `researcher`、`verifier` 或 `reporter` agent 启动
- **THEN** 系统 MUST 根据该角色注入受限且可审计的工具集合
- **THEN** 任何不在该角色允许集合中的工具 MUST 不可用或被策略层显式拒绝

### Requirement: Fabric tools mediate agent coordination
系统 MUST 提供一组 fabric tools，使 Deep Research agents 通过结构化读取、提交、handoff 和 request 动作协作，而不是直接改写共享权威状态；这些 tools MUST 能同时表达 control-plane handoff 与 execution feedback。

#### Scenario: Control-plane agents submit structured handoffs
- **WHEN** `clarify`、`scope` 或 `supervisor` 需要把控制权移交给下一个 control-plane role
- **THEN** 它们 MUST 通过 fabric tools 提交结构化 handoff payload，而不是只改写裸 `next_step`
- **THEN** graph MUST 在受控阶段应用该 handoff 到权威 runtime state

#### Scenario: Supervisor dispatches branch work
- **WHEN** `supervisor` 需要基于 `research brief`、ledger 或验证反馈创建、更新或重排 branch 任务
- **THEN** 系统 MUST 通过 fabric tools 读取当前 blackboard 状态并提交结构化任务动作
- **THEN** graph MUST 在受控阶段应用这些动作到权威 task queue 和 artifact store

#### Scenario: Execution agents submit only registered request types
- **WHEN** `researcher`、`verifier` 或报告准备阶段需要提交 follow-up、反证、矛盾、结构缺口或工具阻塞请求
- **THEN** 它们 MUST 通过 fabric tools 提交结构化 coordination request，且 request type MUST 属于权威允许集合
- **THEN** 它们 MUST NOT 直接创建新的 sibling branch、直接重排任务队列、直接改写其他 agent 的状态，或直接发起新的 control-plane handoff

### Requirement: Reporting tools are outline-gated
系统 MUST 让 `reporter` 作为 `supervisor` 调用的 reporting subagent，只在 outline artifact 已就绪且不存在阻塞性 `outline_gap` 时进入最终报告生成。

#### Scenario: Reporter receives outline-backed inputs
- **WHEN** `reporter` agent 启动
- **THEN** 系统 MUST 向它暴露 outline artifact 及其引用的已验证 branch artifacts
- **THEN** `supervisor` MUST NOT 在缺少 outline artifact 时调用 `reporter` 对未结构化的 branch synthesis 执行最终成文

#### Scenario: Outline gaps return through the fabric
- **WHEN** 报告准备阶段发现当前结构仍不足以支撑目标输出
- **THEN** 系统 MUST 通过 fabric tools 提交结构化 `outline_gap` request 并把控制权保留在 `supervisor` 路径
- **THEN** 调用方 MUST 不需要重新解析完整原始工具对话，才能理解为什么报告尚未进入最终生成

## ADDED Requirements

### Requirement: Control-plane handoff tools are owner-gated
系统 MUST 只允许当前 `active_agent` 调用 control-plane handoff tools，并拒绝任何非 owner 角色尝试改写当前控制平面所有权。

#### Scenario: Non-owner cannot emit a control-plane handoff
- **WHEN** 非当前 `active_agent` 的 control-plane role，或任意 execution subagent，尝试提交新的 handoff payload
- **THEN** 系统 MUST 阻止该调用并返回结构化失败原因
- **THEN** runtime MUST 不会因为该失败调用而改变当前权威 owner

#### Scenario: Current owner can hand off to the next control-plane role
- **WHEN** 当前 `active_agent` 满足其阶段退出条件并需要推进研究流程
- **THEN** 系统 MUST 允许其调用 handoff tool 把控制权移交给下一个允许的 control-plane role
- **THEN** 该移交 MUST 被记录为可恢复、可观测的结构化状态变更

