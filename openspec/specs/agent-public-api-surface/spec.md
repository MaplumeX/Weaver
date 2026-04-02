# agent-public-api-surface Specification

## Purpose
TBD - created by archiving change modularize-agent-runtime. Update Purpose after archive.
## Requirements
### Requirement: Agent facade remains the default public entrypoint
系统 MUST 为外部调用方保留稳定的 `agent` facade 入口，并优先通过该入口暴露公开能力。

#### Scenario: External module calls agent capability
- **WHEN** `main.py`、`common/*`、`web` 生成代码或其他外围模块需要调用 agent 能力
- **THEN** 系统 MUST 优先通过 `agent/__init__.py`、`agent/api.py` 或显式公开入口访问这些能力

#### Scenario: Internal implementation moves
- **WHEN** `agent` 包内部文件位置发生迁移
- **THEN** 已声明为公开入口的 facade MUST 保持稳定，避免要求外围调用方跟随内部文件重组频繁改 import

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

### Requirement: Deprecated Deep Research facade exports are removed
系统 MUST 将 `agent/__init__.py` 与 `agent/api.py` 上的 Deep Research 公开入口收敛到当前 canonical surface，而 MUST NOT 继续暴露 `run_deepsearch`、`run_deepsearch_auto` 或其他 deepsearch 时代的兼容导出。

#### Scenario: External module imports a Deep Research runtime entrypoint
- **WHEN** 外围模块需要通过 `agent` facade 调用 Deep Research 运行时能力
- **THEN** 系统 MUST 只暴露 canonical Deep Research entrypoint
- **THEN** 外围模块 MUST NOT 再通过 facade 导入 `run_deepsearch`、`run_deepsearch_auto` 或其他已退役别名

#### Scenario: Internal tests or examples patch Deep Research logic
- **WHEN** tests、examples 或内部模块需要 monkeypatch Deep Research 运行时
- **THEN** 它们 MUST 指向当前 owning module 或 canonical public entrypoint
- **THEN** 系统 MUST NOT 为保留历史 patch 点继续扩展 facade re-export

