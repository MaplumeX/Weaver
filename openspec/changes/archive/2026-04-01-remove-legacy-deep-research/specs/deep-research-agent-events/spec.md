## ADDED Requirements

### Requirement: Public role semantics match runtime roles
系统 MUST 让公开 Deep Research 事件流中的角色与阶段语义直接反映当前 `multi_agent` runtime 的真实角色，而不是继续暴露 `planner`、`coordinator` 等旧词汇。

#### Scenario: Planning and orchestration progress is emitted
- **WHEN** Deep Research 进入初始规划、replan、scope 审核后续动作或最终停机决策阶段
- **THEN** 系统 MUST 使用 `supervisor` 作为公开的 orchestration role
- **THEN** 事件 MUST 继续携带 phase、decision 和恢复上下文，使客户端无需 legacy 角色别名也能理解进度

#### Scenario: Frontend renders deep research progress
- **WHEN** 前端或测试消费 Deep Research 事件流
- **THEN** 它们 MUST 能基于 `supervisor`、`researcher`、`verifier` 和 `reporter` 角色直接渲染状态
- **THEN** 客户端 MUST NOT 依赖把同一事件再映射成 `planner` 或 `coordinator` 才能工作
