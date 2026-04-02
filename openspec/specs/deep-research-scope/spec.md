## Purpose
定义 Deep Research 运行时中的 graph、branch、agent scope 边界，以及跨 scope 状态暴露与交接约束。
## Requirements
### Requirement: Deep research state is partitioned by scope
系统 MUST 将 Deep Research 的运行时状态划分为 `graph scope`、`branch scope` 和 `agent scope`，并为每一层定义明确的所有权，其中 `branch scope` MUST 成为正式的一等执行边界。

#### Scenario: Managing graph-level state
- **WHEN** 系统维护主题、预算、任务队列快照、artifact 快照、验证汇总、`supervisor` 决策记录或最终报告结果
- **THEN** 这些数据 MUST 归属于 `graph scope`
- **THEN** 任一 branch 或 agent MUST NOT 直接声明自己拥有这些全局状态

#### Scenario: Managing branch-level state
- **WHEN** `supervisor`、`verifier` 或 `reporter` 需要跟踪某个研究分支的目标、当前结论、验证状态或后续动作
- **THEN** 这些数据 MUST 归属于对应的 `branch scope`
- **THEN** sibling branch MUST NOT 通过共享可变对象直接改写彼此的 branch-level 状态

#### Scenario: Managing agent-local state
- **WHEN** 任一 Deep Research tool agent 在某个执行阶段内进行局部推理、工具调用或暂存中间结果
- **THEN** 这些临时状态 MUST 归属于对应的 `agent scope`
- **THEN** 这些临时状态 MUST NOT 被无差别暴露给 sibling agent 或其他 branch

### Requirement: Cross-scope handoff is artifact-backed
系统 MUST 通过结构化 artifacts、blackboard payload 或显式 fabric tool handoff 在不同 scope 之间传递信息，而不是共享完整消息历史或直接共享可变对象。

#### Scenario: Supervisor hands off branch objectives
- **WHEN** `supervisor` 将新的研究任务交给 `researcher`
- **THEN** 系统 MUST 通过结构化 branch task、相关 artifact 引用和必要的 blackboard 上下文完成交接
- **THEN** 下游执行方 MUST 不需要读取 `supervisor` 的完整临时上下文才能理解任务

#### Scenario: Agent submits results to graph scope
- **WHEN** `researcher`、`verifier` 或 `reporter` 完成任务并需要提交证据、验证结论、报告输入或任务状态更新
- **THEN** 系统 MUST 通过结构化 payload、artifact 快照或 fabric tool 提交完成回传
- **THEN** `graph scope` MUST 在统一 merge 阶段接收这些结果

#### Scenario: Branch reads upstream knowledge
- **WHEN** 某个 branch 需要消费其他阶段已经确认的研究结论
- **THEN** 系统 MUST 通过当前有效 artifacts、branch brief、verification 结果或已验证的 branch synthesis 提供该信息
- **THEN** 系统 MUST NOT 依赖读取其他 agent 的完整临时工具上下文

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

