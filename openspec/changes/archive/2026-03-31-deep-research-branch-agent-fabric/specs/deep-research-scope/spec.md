## MODIFIED Requirements

### Requirement: Deep research state is partitioned by scope
系统 MUST 将 Deep Research 的运行时状态划分为 `graph scope`、`branch scope` 和 `worker scope`，并为每一层定义明确的所有权，其中 `branch scope` MUST 成为正式的一等执行边界。

#### Scenario: Managing graph-level state
- **WHEN** 系统维护主题、预算、任务队列快照、artifact 快照、验证汇总或最终报告结果
- **THEN** 这些数据 MUST 归属于 `graph scope`
- **THEN** 任一 branch 或 worker MUST NOT 直接声明自己拥有这些全局状态

#### Scenario: Managing branch-level state
- **WHEN** planner、coordinator 或 verifier 需要跟踪某个研究分支的目标、当前结论、验证状态或后续动作
- **THEN** 这些数据 MUST 归属于对应的 `branch scope`
- **THEN** sibling branch MUST NOT 通过共享可变对象直接改写彼此的 branch-level 状态

#### Scenario: Managing worker-local state
- **WHEN** researcher branch agent 在某个执行阶段内进行局部推理、工具调用或暂存中间结果
- **THEN** 这些临时状态 MUST 归属于 `worker scope`
- **THEN** 这些临时状态 MUST NOT 被无差别暴露给 sibling worker 或其他 branch

### Requirement: Cross-scope handoff is artifact-backed
系统 MUST 通过结构化 artifacts 或显式 handoff payload 在不同 scope 之间传递信息，而不是共享完整消息历史或直接共享可变对象。

#### Scenario: Planner hands off branch objectives
- **WHEN** planner 将新的研究任务交给 coordinator 或 researcher
- **THEN** 系统 MUST 通过结构化 branch task 与相关 artifact 引用完成交接
- **THEN** 下游执行方 MUST 不需要读取 planner 的完整临时上下文才能理解任务

#### Scenario: Worker submits results to graph scope
- **WHEN** researcher branch agent 完成任务并需要提交证据、分支结论或任务状态更新
- **THEN** 系统 MUST 通过结构化 payload 或 artifact 快照完成回传
- **THEN** graph scope MUST 在统一 merge 阶段接收这些结果

#### Scenario: Branch reads upstream knowledge
- **WHEN** 某个 branch 需要消费其他阶段已经确认的研究结论
- **THEN** 系统 MUST 通过当前有效 artifacts、branch brief 或已验证的 branch synthesis 提供该信息
- **THEN** 系统 MUST NOT 依赖读取其他 worker 的完整临时上下文
