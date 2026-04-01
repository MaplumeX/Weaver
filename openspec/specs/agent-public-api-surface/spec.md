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
系统 MUST 为事件、registry、worker context 或其他跨层共享契约提供显式公开位置。

#### Scenario: Tools consume agent events
- **WHEN** `tools/*` 需要发出或消费 agent 事件
- **THEN** 它们 MUST 依赖显式公开的事件契约模块，而不是依赖某个 workflow 实现文件中的内部定义

#### Scenario: Common layer reads research artifacts
- **WHEN** `common/*` 需要读取来源、claim、artifact 或 runtime 元数据
- **THEN** 它们 MUST 通过公开的 shared contracts 或 facade 访问这些结构，而不是直接导入 `agent.workflows.*` 内部实现

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
