## MODIFIED Requirements

### Requirement: Shared contracts are imported from explicit public locations
系统 MUST 为事件、registry、worker context、claim/result artifact 或其他跨层共享契约提供显式公开位置；这些公开位置 MUST 指向稳定 contract 定义或 facade wrapper，而 MUST NOT 继续把 `agent.workflows.*` 或 runtime loop 实现暴露为 contract backing。

#### Scenario: Tools consume agent events
- **WHEN** `tools/*` 需要发出或消费 agent 事件
- **THEN** 它们 MUST 依赖显式公开的事件契约模块
- **THEN** 这些契约模块 MUST NOT 通过 `agent.workflows.*` 内部实现文件反向提供事件类型

#### Scenario: Common layer reads research artifacts
- **WHEN** `common/*` 需要读取来源、claim、artifact 或 runtime 元数据
- **THEN** 它们 MUST 通过公开的 shared contracts 或 facade 访问这些结构
- **THEN** 它们 MUST NOT 直接导入 `agent.workflows.*` 内部实现

#### Scenario: Implementation moves behind a public contract
- **WHEN** 某个共享契约的真实实现从 workflow internals 迁移到 runtime-owned module
- **THEN** `agent.contracts.*` 的导入路径 MUST 保持稳定
- **THEN** 外围调用方 MUST 不需要跟随内部实现目录重组修改导入

### Requirement: Workflow internals are not treated as external API
系统 MUST 将 `agent.workflows.*` 和其他内部实现目录视为内部模块；当需要迁移兼容时，系统 MUST 使用显式 facade 或 compat 入口，而 MUST NOT 继续把 workflow internals 作为受支持公开 API。

#### Scenario: External module imports workflow internals
- **WHEN** 外围模块需要调用 Deep Research 相关能力、事件或 artifact contract
- **THEN** 系统 MUST 提供 facade、公开契约或显式 compat 入口替代对 `agent.workflows.*` 的直接依赖
- **THEN** 外围调用方 MUST 迁移离开 workflow internals 路径

#### Scenario: Post-migration deep research compatibility exports are removed
- **WHEN** `multi_agent` 已经成为唯一的 Deep Research runtime 且调用方已迁移
- **THEN** 系统 MUST NOT 继续保留 `agent.workflows.deepsearch_*` 作为受支持的兼容 re-export
- **THEN** 任何仍需复用的能力 MUST 以显式公开入口或 shared contract 形式暴露

#### Scenario: Temporary migration path is required
- **WHEN** 某个内部调用方还未完成迁移
- **THEN** 系统 MUST 优先提供 `agent` facade、`agent.contracts.*` 或显式 compat 入口
- **THEN** 系统 MUST NOT 通过继续扩展 `agent.workflows.*` 的 re-export 集合来满足兼容需求
