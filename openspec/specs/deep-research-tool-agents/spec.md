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
系统 MUST 提供一组 fabric tools，使 Deep Research agents 通过结构化读取、提交和请求动作协作，而不是直接改写共享权威状态。

#### Scenario: Supervisor dispatches branch work
- **WHEN** `supervisor` 需要基于已批准 scope 或验证反馈创建、更新或重排 branch 任务
- **THEN** 系统 MUST 通过 fabric tools 读取当前 blackboard 状态并提交结构化任务动作
- **THEN** graph MUST 在受控阶段应用这些动作到权威 task queue 和 artifact store

#### Scenario: Research agent discovers follow-up work
- **WHEN** `researcher` 在 branch 执行中发现新的研究线索、阻塞原因或需要升级的风险
- **THEN** 它 MUST 通过 fabric tools 提交结构化 follow-up request、retry hint 或 escalation
- **THEN** 它 MUST NOT 直接创建新的 sibling branch、直接重排任务队列或直接改写其他 agent 的状态

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
