## MODIFIED Requirements

### Requirement: Deep runtime state is nested and mode-scoped
系统 MUST 将 deep runtime 私有运行时状态收敛到嵌套且 mode-scoped 的结构中，并在完成本次 hard-cut 模式收口后删除 direct/web 历史模式节点、导出和兼容状态面；任何仍被 `agent` 或 `deep` 复用的共享能力 MUST 迁移到显式 shared 或正确 owning module，而不是继续借由已删除模式实现存活。

#### Scenario: Recording multi-agent runtime data
- **WHEN** multi-agent runtime 需要记录 task queue、artifact store、runtime bookkeeping 或 agent runs
- **THEN** 系统 MUST 将这些数据放入明确的 `deep_runtime` 状态块
- **THEN** 任何新增 deep-only 状态 MUST NOT 再写入顶层 `AgentState`

#### Scenario: Preserving agent mode
- **WHEN** `agent` 模式执行
- **THEN** 该模式 MUST 不依赖 deep runtime 私有字段才能正常工作
- **THEN** deep runtime 状态收口 MUST 不改变 `agent` 模式的调用语义

#### Scenario: Removing deleted mode scaffolding
- **WHEN** 系统删除 `direct` 与 `web` 历史模式节点和兼容导出
- **THEN** 任何仍被 `agent` 或 `deep` 复用的 helper MUST 先迁移到显式 shared 或新 owning module
- **THEN** 系统 MUST NOT 仅为保留旧模式结构而继续保留 `direct`/`web` 专属节点、re-export 或兼容状态字段
