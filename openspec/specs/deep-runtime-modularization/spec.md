# deep-runtime-modularization Specification

## Purpose
TBD - created by archiving change modularize-agent-runtime. Update Purpose after archive.
## Requirements
### Requirement: Deep runtime selection is separated from runtime implementations
系统 MUST 将 deep runtime 的选择逻辑与具体 runtime 执行细节分离。

#### Scenario: Delegating from deepsearch entrypoint
- **WHEN** `deepsearch_node` 需要根据配置选择 `legacy` 或 `multi_agent` runtime
- **THEN** 系统 MUST 通过独立的 runtime 选择层完成委托，而不是把选择逻辑与某个具体 runtime 实现混写在同一模块中

#### Scenario: Preserving existing deep entry behavior
- **WHEN** Deep Research 请求进入 graph 级入口
- **THEN** 系统 MUST 保持现有 graph 入口与外部调用语义稳定，同时允许内部 runtime 模块自由重组

### Requirement: Legacy deep runtime is decomposed by responsibility
系统 MUST 将 legacy deep runtime 拆分为可独立理解和测试的职责单元。

#### Scenario: Legacy runtime contains mixed concerns
- **WHEN** legacy deep runtime 同时包含 engine 选择、query strategy、tree/linear orchestration、质量回环和事件发射
- **THEN** 系统 MUST 按选择器、执行器、策略和共享 helper 拆分这些职责

#### Scenario: Testing legacy runtime modules
- **WHEN** 需要为 legacy deep runtime 的某一职责补充测试
- **THEN** 系统 MUST 能在不加载完整 deep runtime 文件的前提下独立测试该职责模块

### Requirement: Multi-agent runtime is split into internal components
系统 MUST 将 multi-agent runtime 拆分为 schema、store、dispatcher、loop、event helper 和 public entrypoint 等内部组件。

#### Scenario: Defining runtime-owned artifacts
- **WHEN** multi-agent runtime 需要定义 `ResearchTask`、`EvidenceCard`、`KnowledgeGap` 或其他 artifact
- **THEN** 这些 schema MUST 位于专门的 schema 或 contract 模块，而不是埋在 coordinator loop 实现文件中

#### Scenario: Dispatching researcher workers
- **WHEN** coordinator loop 调度 researcher worker、任务队列或 artifact store
- **THEN** 系统 MUST 通过独立组件完成队列、存储和 worker dispatch，而不是把这些逻辑全部封装进单一 runtime 文件

### Requirement: Deep runtime state is nested and mode-scoped
系统 MUST 将 deep runtime 私有运行时状态收敛到嵌套且 mode-scoped 的结构中，避免继续平铺增长共享状态。

#### Scenario: Recording multi-agent runtime data
- **WHEN** multi-agent runtime 需要记录 task queue、artifact store、runtime bookkeeping 或 agent runs
- **THEN** 系统 MUST 将这些数据放入明确的 deep runtime 状态块，而不是继续向顶层 `AgentState` 添加同级字段

#### Scenario: Preserving non-deep modes
- **WHEN** `direct`、`web` 或 `agent` 模式执行
- **THEN** 这些模式 MUST 不依赖 deep runtime 私有字段才能正常工作

