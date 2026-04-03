## MODIFIED Requirements

### Requirement: Fabric tools mediate agent coordination
系统 MUST 提供一组 fabric tools，使 Deep Research agents 通过结构化读取、提交和请求动作协作，而不是直接改写共享权威状态；这些 tools MUST 能表达 `research brief`、ledger、增强验证 artifacts 和收敛后的 coordination request 类型。

#### Scenario: Supervisor dispatches branch work
- **WHEN** `supervisor` 需要基于 `research brief`、ledger 或验证反馈创建、更新或重排 branch 任务
- **THEN** 系统 MUST 通过 fabric tools 读取当前 blackboard 状态并提交结构化任务动作
- **THEN** graph MUST 在受控阶段应用这些动作到权威 task queue 和 artifact store

#### Scenario: Execution agents submit only registered request types
- **WHEN** `researcher`、`verifier` 或报告准备阶段需要提交 follow-up、反证、矛盾、结构缺口或工具阻塞请求
- **THEN** 它们 MUST 通过 fabric tools 提交结构化 coordination request，且 request type MUST 属于权威允许集合
- **THEN** 它们 MUST NOT 直接创建新的 sibling branch、直接重排任务队列、直接改写其他 agent 的状态，或提交未注册 request type

## ADDED Requirements

### Requirement: Reporting tools are outline-gated
系统 MUST 让报告相关 tool agents 只在 outline artifact 已就绪且不存在阻塞性 `outline_gap` 时进入最终报告生成。

#### Scenario: Reporter receives outline-backed inputs
- **WHEN** `reporter` agent 启动
- **THEN** 系统 MUST 向它暴露 outline artifact 及其引用的已验证 branch artifacts
- **THEN** 系统 MUST NOT 让 `reporter` 在缺少 outline artifact 时直接对未结构化的 branch synthesis 执行最终成文

#### Scenario: Outline gaps return through the fabric
- **WHEN** 报告准备阶段发现当前结构仍不足以支撑目标输出
- **THEN** 系统 MUST 通过 fabric tools 提交结构化 `outline_gap` request 并把控制权交回 `supervisor`
- **THEN** 调用方 MUST 不需要重新解析完整原始工具对话，才能理解为什么报告尚未进入最终生成
