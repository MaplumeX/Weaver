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
