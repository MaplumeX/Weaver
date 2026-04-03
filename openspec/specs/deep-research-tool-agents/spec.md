## Purpose
定义 Deep Research bounded tool agents 的角色工具边界、fabric tools 协作契约与策略门控。

## Requirements

### Requirement: Deep research roles are exposed as bounded tool agents
系统 MUST 将 `clarify`、`scope`、`supervisor`、`researcher`、`verifier`、`reporter` 建模为具有显式工具表面的 bounded tool agents，并为每个角色定义独立的允许工具集合。

#### Scenario: Clarify and scope use fabric-only tools
- **WHEN** `clarify` 或 `scope` agent 执行 intake、范围整理或审阅交接
- **THEN** 系统 MUST 仅向它们暴露与用户上下文、scope 草案和审阅动作相关的 fabric tools
- **THEN** 系统 MUST NOT 向它们暴露 world-facing 的搜索、浏览、抓取或抽取工具

#### Scenario: Execution agents use role-specific world tools
- **WHEN** `researcher`、`verifier` 或 `reporter` agent 启动
- **THEN** 系统 MUST 根据该角色注入受限且可审计的工具集合
- **THEN** 任何不在该角色允许集合中的工具 MUST 不可用或被策略层显式拒绝

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

### Requirement: Tool agent execution is policy-gated
系统 MUST 对每个 Deep Research tool agent 执行步骤限制、预算限制、审批策略和失败回传约束。

#### Scenario: Tool use exceeds role or budget policy
- **WHEN** 任一 Deep Research tool agent 尝试调用超出角色权限或超出预算边界的工具
- **THEN** 系统 MUST 阻止该调用并保留结构化失败原因
- **THEN** graph 或 `supervisor` MUST 能基于该失败原因决定重试、降级、replan 或停止

#### Scenario: Tool agent run completes with partial progress
- **WHEN** tool agent 在预算、来源或审批限制下只能部分完成任务
- **THEN** 系统 MUST 要求它返回结构化的部分完成状态、已提交产物和建议的后续动作
- **THEN** 调用方 MUST 不需要重新解析完整原始工具对话，才能理解这次执行结果

### Requirement: Fabric tools expose verification contracts and revision context
系统 MUST 为 `researcher` 与 `verifier` bounded tool agents 暴露结构化 verification contracts 与 revision context，而不是只暴露 summary 文本和松散 artifact 列表。

#### Scenario: Revision-oriented researcher starts
- **WHEN** revision-oriented `researcher` tool agent 启动
- **THEN** fabric tools MUST 让它读取当前 branch 的 unresolved issues、prior answer units、prior evidence、obligations 和 revision brief
- **THEN** 它 MUST 不需要从自由文本 summary 中重新推断当前修订目标

#### Scenario: Verifier tool agent adjudicates a boundary case
- **WHEN** `verifier` tool agent 被调用处理证据不足、反证冲突或一致性边界 case
- **THEN** fabric tools MUST 提供 answer unit ids、obligation ids、issue ids、相关 evidence passage 引用和最小上下文范围
- **THEN** tool agent MUST 围绕这些结构化对象返回结果，而不是只提交新的自由文本解释

### Requirement: Tool-agent submissions are issue-addressable
系统 MUST 要求 verifier 与 revision-oriented researcher 的 tool-agent 提交结果引用稳定的 verification object identifiers。

#### Scenario: Verifier submits a verification bundle
- **WHEN** `verifier` tool agent 提交 grounding、coverage 或 consistency 结果
- **THEN** submission MUST 在适用时引用 answer unit ids、obligation ids、consistency finding ids 或 issue ids
- **THEN** submission MUST 同时声明相关 `evidence_passage_ids`
- **THEN** graph merge MUST 能据此确定性地更新 artifact store 和 ledgers

#### Scenario: Researcher submits a revision bundle
- **WHEN** revision-oriented `researcher` tool agent 提交补证据或反证结果
- **THEN** submission MUST 在适用时声明其试图解决的 issue ids 与实际解决状态
- **THEN** `supervisor` MUST 能基于该 submission 判断本轮修订是否已满足继续推进条件

### Requirement: Verifier tools are unit-addressable and summary-free
系统 MUST 将 verifier bounded tool-agent 的权威工具表面设计为 unit / obligation 可寻址接口，而不是 summary-oriented challenge tools。

#### Scenario: Verifier tool agent starts a validation pass
- **WHEN** `verifier` tool agent 启动
- **THEN** 系统 MUST 向它暴露可枚举 answer units、读取 obligations、读取 evidence passages、验证单个 unit、验证单个 obligation 和提交验证结果的工具，或与其等价的结构化接口
- **THEN** 系统 MUST NOT 把 `summary` challenge、summary coverage compare 或等价的自由文本工具作为 authoritative validation path

#### Scenario: Verifier tool agent returns a verdict
- **WHEN** `verifier` tool agent 对某个边界 case 返回 verdict
- **THEN** 每个 verdict MUST 显式绑定它 adjudicate 的 answer unit 或 obligation
- **THEN** 系统 MUST NOT 因为一个 branch-level outcome 就把相同 verdict 自动扩散到整批 answer units 或 obligations
