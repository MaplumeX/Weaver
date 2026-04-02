## MODIFIED Requirements

### Requirement: Multi-agent runtime is split into internal components
系统 MUST 将 multi-agent runtime 拆分为 schema、store、dispatcher、loop、event helper、public entrypoint、runtime-owned roles 和 runtime-owned services 等内部组件，并消除对 `agent.workflows.*` Deep Research 实现的长期依赖。

#### Scenario: Defining runtime-owned artifacts
- **WHEN** multi-agent runtime 需要定义 `ResearchTask`、`EvidenceCard`、`KnowledgeGap` 或其他 artifact
- **THEN** 这些 schema MUST 位于 runtime-owned schema/contract 模块
- **THEN** role 与 service 模块 MUST 引用这些 schema，而不是在 graph loop 文件中内联定义

#### Scenario: Dispatching researcher workers
- **WHEN** coordinator loop 调度 researcher worker、任务队列或 artifact store
- **THEN** queue、store、dispatcher、role execution MUST 通过独立组件协作完成
- **THEN** runtime graph loop MUST NOT 继续直接承担 role 实现与 service 细节

#### Scenario: Locating deep runtime roles and services
- **WHEN** Deep Research 需要 clarify、scope、supervisor、researcher、reporter、verifier、gap analysis 或 artifact assembly 等能力
- **THEN** 这些实现 MUST 位于 `agent.runtime.deep.*` 或显式 shared contract 模块
- **THEN** 当前 runtime MUST NOT 继续从 `agent.workflows.*` 引入这些 runtime-owned 实现

### Requirement: Deep runtime state is nested and mode-scoped
系统 MUST 将 deep runtime 私有运行时状态收敛到嵌套且 mode-scoped 的结构中，并将剩余 legacy top-level deep fields 视为待迁移兼容层，而不是继续扩展的长期状态面。

#### Scenario: Recording multi-agent runtime data
- **WHEN** multi-agent runtime 需要记录 task queue、artifact store、runtime bookkeeping 或 agent runs
- **THEN** 系统 MUST 将这些数据放入明确的 deep runtime 状态块
- **THEN** 任何新增 deep-only 状态 MUST NOT 再写入顶层 `AgentState`

#### Scenario: Preserving non-deep modes
- **WHEN** `direct`、`web` 或 `agent` 模式执行
- **THEN** 这些模式 MUST 不依赖 deep runtime 私有字段才能正常工作
- **THEN** deep runtime 状态收口 MUST 不改变非 deep 模式的调用语义

#### Scenario: Migrating flattened legacy fields
- **WHEN** 历史顶层字段仍然存在以兼容旧逻辑
- **THEN** 系统 MUST 将其限制为过渡用途
- **THEN** 新代码 MUST 优先读写嵌套 deep runtime state，而不是继续扩大顶层字段集合
