## ADDED Requirements

### Requirement: Public deep research artifacts are derived from the multi-agent store
系统 MUST 从 `multi_agent` runtime 的权威 task queue、artifact store 和 final report 快照生成公开的 Deep Research artifacts 视图，而不是依赖 legacy runner 风格的兼容拼装对象。

#### Scenario: Session or API exports public deep research artifacts
- **WHEN** `SessionManager`、API 响应或导出逻辑需要读取 `deepsearch_artifacts`
- **THEN** 系统 MUST 从 `fetched_documents`、`evidence_passages`、`verification_results`、`final_report` 和质量快照生成公开 artifacts
- **THEN** 公开 artifacts MUST 暴露客户端仍依赖的 `sources`、`fetched_pages`、`passages`、`claims`、`quality_summary` 和最终报告字段，而不要求调用方解析内部 store 结构

#### Scenario: Public artifact export reuses recorded verification output
- **WHEN** `multi_agent` runtime 已经记录 claim/citation 验证结果或来源证据
- **THEN** 系统 MUST 直接复用这些结构化产物构建公开 `claims` 与来源信息
- **THEN** 系统 MUST NOT 通过 legacy verifier 回填或重新解析自由文本来生成第二份事实源
