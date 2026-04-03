## ADDED Requirements

### Requirement: Canonical Deep Research event and checkpoint names are stable
系统 MUST 使用 canonical Deep Research 命名空间暴露 interrupt checkpoint、进度事件和 topology 更新，并且 MUST NOT 再发出 `deepsearch_*` 或 `research_tree_update` 之类的历史别名。

#### Scenario: Runtime emits Deep Research checkpoint prompts
- **WHEN** Deep Research 进入 clarify、scope review 或 merge 审批等 interrupt 阶段
- **THEN** 系统 MUST 使用 canonical Deep Research checkpoint 名称暴露该阶段
- **THEN** 系统 MUST NOT 再使用 `deepsearch_clarify`、`deepsearch_scope_review`、`deepsearch_merge` 或其他历史 checkpoint 名称

#### Scenario: Runtime emits topology progress
- **WHEN** Deep Research 的 branch topology 或研究拓扑发生变化
- **THEN** 系统 MUST 发出 canonical topology update 事件
- **THEN** 前端、测试与调试工具 MUST NOT 再依赖 `research_tree_update` 或其他 deepsearch 时代事件别名
