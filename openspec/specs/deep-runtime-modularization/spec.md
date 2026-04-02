# deep-runtime-modularization Specification

## Purpose
TBD - created by archiving change modularize-agent-runtime. Update Purpose after archive.
## Requirements
### Requirement: Deep runtime selection is separated from runtime implementations
系统 MUST 将 Deep Research 入口收敛到单一 `multi_agent` runtime 的公开入口，并避免通过 selector 或 compatibility wrapper 重新引入运行时选择分支。

#### Scenario: Delegating from deepsearch entrypoint
- **WHEN** `deepsearch_node` 需要启动 Deep Research
- **THEN** 系统 MUST 直接委托给 `multi_agent` runtime 的公开入口
- **THEN** 系统 MUST 不再要求单独的 selector 层去决定 `legacy` 或 `multi_agent` runtime

#### Scenario: Preserving existing deep entry behavior
- **WHEN** Deep Research 请求进入 graph 级入口
- **THEN** 系统 MUST 保持现有 graph 入口与外部调用语义稳定
- **THEN** 内部 runtime 重组 MUST 不再暴露多 runtime 分支给调用方

### Requirement: Multi-agent runtime is split into internal components
系统 MUST 将 multi-agent runtime 拆分为 schema、store、dispatcher、orchestration loop、event helper、public entrypoint、runtime-owned agent packages、runtime-owned services、artifact adapters 与 supporting helper 等内部组件，并消除对 `agent.workflows.*`、`agent.compat.*` 或其他历史 shim 路径的长期依赖。

#### Scenario: Defining runtime-owned artifacts
- **WHEN** multi-agent runtime 需要定义 `ResearchTask`、`EvidenceCard`、`KnowledgeGap` 或其他 artifact
- **THEN** 这些 schema MUST 位于 runtime-owned schema/contract 模块
- **THEN** agent、service 与 artifact adapter 模块 MUST 引用这些 schema，而不是在 orchestration loop 文件中内联定义

#### Scenario: Dispatching researcher workers
- **WHEN** orchestration loop 调度 researcher worker、任务队列、artifact store 或 bounded tool-agent session
- **THEN** queue、store、dispatcher、agent execution 与 supporting helpers MUST 通过独立组件协作完成
- **THEN** runtime orchestration 文件 MUST NOT 继续直接承担 agent 实现与 service 细节

#### Scenario: Locating deep runtime agents and services
- **WHEN** Deep Research 需要 clarify、scope、supervisor、researcher、reporter、verifier、gap analysis、artifact assembly 或 tool-agent builder 等能力
- **THEN** 这些实现 MUST 位于 `agent.runtime.deep.*`、`agent.builders.*`、`agent.research.*` 或显式 shared contract 模块
- **THEN** 当前 runtime MUST NOT 继续从 `agent.workflows.*` 或 `agent.compat.*` 引入这些 runtime-owned 或 runtime-required 实现

### Requirement: Deep runtime state is nested and mode-scoped
系统 MUST 将 deep runtime 私有运行时状态收敛到嵌套且 mode-scoped 的结构中，并在完成本次 hard-cut 迁移后删除顶层 flattened legacy deep fields，而不是继续把它们保留为长期兼容状态面。

#### Scenario: Recording multi-agent runtime data
- **WHEN** multi-agent runtime 需要记录 task queue、artifact store、runtime bookkeeping 或 agent runs
- **THEN** 系统 MUST 将这些数据放入明确的 `deep_runtime` 状态块
- **THEN** 任何新增 deep-only 状态 MUST NOT 再写入顶层 `AgentState`

#### Scenario: Preserving non-deep modes
- **WHEN** `direct`、`web` 或 `agent` 模式执行
- **THEN** 这些模式 MUST 不依赖 deep runtime 私有字段才能正常工作
- **THEN** deep runtime 状态收口 MUST 不改变非 deep 模式的调用语义

#### Scenario: Removing flattened legacy fields
- **WHEN** 历史顶层 `deepsearch_*` 字段仅为兼容旧逻辑存在
- **THEN** 系统 MUST 将调用方迁移到嵌套 `deep_runtime` 结构
- **THEN** 系统 MUST 删除这些顶层镜像字段，而不是继续保留双轨读写

