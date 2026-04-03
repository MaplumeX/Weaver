## MODIFIED Requirements

### Requirement: Public deep research artifacts are derived from the multi-agent store
系统 MUST 从 canonical Deep Research runtime 的权威 task queue、artifact store、topology 快照和 final report 快照生成公开的 Deep Research artifacts 视图，而 MUST NOT 再依赖 `deepsearch_artifacts`、`research_plan`、`research_tree` 或其他旧顶层 fallback 字段做兼容拼装。

#### Scenario: Session or API exports public deep research artifacts
- **WHEN** `SessionManager`、API 响应或导出逻辑需要读取公开 Deep Research artifacts
- **THEN** 系统 MUST 输出 canonical artifact payload，并暴露客户端仍依赖的 `sources`、`fetched_pages`、`passages`、`claims`、`quality_summary`、最终报告和 topology 信息
- **THEN** 调用方 MUST NOT 需要解析 `deepsearch_artifacts`、`research_plan` 或 `research_tree` 才能恢复当前 Deep Research 结果

#### Scenario: Resume path rebuilds from canonical artifacts only
- **WHEN** 调用方在 interrupt、暂停或会话恢复后继续执行 Deep Research
- **THEN** 系统 MUST 仅基于 canonical public artifacts 与权威 runtime snapshot 恢复执行上下文
- **THEN** 系统 MUST NOT 再把旧的 `deepsearch_artifacts`、`research_plan`、`research_tree` 或其他兼容字段回填到顶层 state
