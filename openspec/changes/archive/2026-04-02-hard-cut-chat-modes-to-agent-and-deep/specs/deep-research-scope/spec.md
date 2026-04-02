## MODIFIED Requirements

### Requirement: Deep research scope does not pollute non-deep execution
系统 MUST 将 Deep Research 专有状态保持在专用作用域或嵌套状态块中，避免 `agent` 模式依赖这些内部字段；已删除的 `direct` 与 `web` 模式 MUST NOT 再作为需要保留兼容性的运行路径存在。

#### Scenario: Agent mode executes
- **WHEN** `agent` 模式运行
- **THEN** 该模式 MUST 不要求存在 Deep Research 的 branch 或 agent scope 数据
- **THEN** 系统 MUST 允许 `agent` 执行在缺少这些 deep-only 字段时正常工作

#### Scenario: Deep runtime snapshot is exposed externally
- **WHEN** 系统需要对外暴露 Deep Research 运行时快照
- **THEN** 系统 MUST 暴露结构化且 scope-aware 的摘要视图
- **THEN** 系统 MUST NOT 把内部临时对象或不可序列化引用直接泄露到公共状态
