## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Legacy deep runtime is decomposed by responsibility
**Reason**: legacy deep runtime 将被整体移除，不再需要为已废弃实现维护独立模块化约束。
**Migration**: 将仍有复用价值的 helper 或 contract 迁移到 `agent.runtime.deep` 或显式 shared contracts，然后删除 legacy runtime 模块和对应测试。
