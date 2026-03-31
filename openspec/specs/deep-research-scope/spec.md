## Purpose
定义 Deep Research 运行时中的 graph、branch、worker scope 边界，以及跨 scope 状态暴露与交接约束。

## Requirements

### Requirement: Deep research state is partitioned by scope
系统 MUST 将 Deep Research 的运行时状态划分为 `graph scope`、`branch scope` 和 `worker scope`，并为每一层定义明确的所有权。

#### Scenario: Managing graph-level state
- **WHEN** 系统维护主题、预算、任务队列快照、artifact 快照或最终汇总结果
- **THEN** 这些数据 MUST 归属于 `graph scope`
- **THEN** 任一 branch 或 worker MUST NOT 直接声明自己拥有这些全局状态

#### Scenario: Managing worker-local state
- **WHEN** researcher worker 执行单个任务
- **THEN** 其临时推理上下文、局部输入和未提交结果 MUST 归属于 `worker scope`
- **THEN** 这些临时状态 MUST NOT 被无差别暴露给 sibling worker

### Requirement: Cross-scope handoff is artifact-backed
系统 MUST 通过结构化 artifacts 或显式 handoff payload 在不同 scope 之间传递信息，而不是共享完整消息历史或直接共享可变对象。

#### Scenario: Worker submits results to graph scope
- **WHEN** researcher worker 完成任务并需要提交证据、摘要或任务状态更新
- **THEN** 系统 MUST 通过结构化 payload 或 artifact 快照完成回传
- **THEN** graph scope MUST 在统一 merge 阶段接收这些结果

#### Scenario: Branch reads upstream knowledge
- **WHEN** 某个 branch 需要消费其他阶段已经确认的研究结论
- **THEN** 系统 MUST 通过当前有效 artifacts 或 branch brief 提供该信息
- **THEN** 系统 MUST NOT 依赖读取其他 worker 的完整临时上下文

### Requirement: Deep research scope does not pollute non-deep execution
系统 MUST 将 Deep Research 专有状态保持在专用作用域或嵌套状态块中，避免非 deep 模式依赖这些内部字段。

#### Scenario: Non-deep mode executes
- **WHEN** `direct`、`web` 或 `agent` 模式运行
- **THEN** 这些模式 MUST 不要求存在 Deep Research 的 branch 或 worker scope 数据
- **THEN** 系统 MUST 允许 non-deep execution 在缺少这些专有字段时正常工作

#### Scenario: Deep runtime snapshot is exposed externally
- **WHEN** 系统需要对外暴露 Deep Research 运行时快照
- **THEN** 系统 MUST 暴露结构化且 scope-aware 的摘要视图
- **THEN** 系统 MUST NOT 把内部临时对象或不可序列化引用直接泄露到公共状态
