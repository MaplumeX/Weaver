## MODIFIED Requirements

### Requirement: Workflow internals are not treated as external API
系统 MUST 将 `agent.workflows.*`、`agent.compat.*`、`agent.core.graph` 以及其他内部实现目录视为内部模块；当完成本次重组后，系统 MUST 通过 facade、公开 contracts 或显式 runtime public entrypoints 暴露能力，而 MUST NOT 继续保留 workflow/compat/shim 路径作为受支持 API。

#### Scenario: External module imports workflow internals
- **WHEN** 外围模块需要调用 Deep Research 相关能力、事件、artifact contract、builder 或 interaction helper
- **THEN** 系统 MUST 提供 facade、公开契约或显式 runtime public entrypoint 替代对旧内部路径的直接依赖
- **THEN** 外围调用方 MUST 迁移离开 `agent.workflows.*`、`agent.compat.*` 与其他 shim 路径

#### Scenario: Post-migration compatibility exports are removed
- **WHEN** hard-cut 重组完成
- **THEN** 系统 MUST NOT 继续保留 `agent.workflows.*`、`agent.compat.*` 或 `agent.core.graph` 作为受支持的兼容 re-export 或 patch 入口
- **THEN** 任何仍需复用的能力 MUST 以 `agent` facade、`agent.contracts.*` 或显式 runtime public entrypoint 形式暴露

#### Scenario: Internal and test callers are migrated directly
- **WHEN** tests、examples 或内部模块仍依赖旧导入路径或旧 monkeypatch 位置
- **THEN** 系统 MUST 直接更新这些调用方指向新的 owning module
- **THEN** 系统 MUST NOT 为保留旧 patch 点而继续扩展 re-export、compat alias 或历史目录包装层
