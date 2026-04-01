## MODIFIED Requirements

### Requirement: Workflow internals are not treated as external API
系统 MUST 将 `agent.workflows.*` 和其他内部实现目录视为内部模块；当 `multi_agent` 成为唯一受支持的 Deep Research runtime 后，系统 MUST 移除 `agent.workflows.deepsearch_*` 兼容入口，而不是继续把它们当作公开 API。

#### Scenario: External module imports workflow internals
- **WHEN** 外围模块需要调用 Deep Research 相关能力、事件或 artifact contract
- **THEN** 系统 MUST 提供 facade 或公开契约替代对 `agent.workflows.deepsearch_*` 的直接依赖
- **THEN** 外围调用方 MUST 迁移离开 workflow internals 路径

#### Scenario: Post-migration deep research compatibility exports are removed
- **WHEN** `multi_agent` 已经成为唯一的 Deep Research runtime
- **THEN** 系统 MUST NOT 继续保留 `agent.workflows.deepsearch_*` 作为受支持的兼容 re-export
- **THEN** 任何仍需复用的能力 MUST 以显式公开入口或 shared contract 形式暴露
