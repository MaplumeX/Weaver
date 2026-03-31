## MODIFIED Requirements

### Requirement: Multi-agent graph execution is checkpoint-aware
系统 MUST 让 multi-agent Deep Research 的权威执行状态落在 LangGraph 可 checkpoint 和恢复的边界上，而不是只存在于进程内循环，并在恢复后继续向调用方暴露可观察的执行进度。

#### Scenario: Deep research pauses or resumes
- **WHEN** multi-agent Deep Research 因 interrupt、暂停或进程恢复而需要继续执行
- **THEN** 系统 MUST 能从已持久化的 graph 状态恢复任务队列、artifacts 和当前阶段
- **THEN** 系统 MUST 不要求重新从头执行整个研究流程

#### Scenario: Scope review resumes after checkpoint
- **WHEN** Deep Research 在 scope 审阅阶段因 interrupt 或会话恢复而继续执行
- **THEN** 系统 MUST 恢复当前 scope draft、修订次数、用户反馈历史和下一步动作
- **THEN** 系统 MUST 不跳过用户批准而直接进入 planner

#### Scenario: Worker fan-out resumes after checkpoint
- **WHEN** 一个包含 researcher fan-out 的阶段在 checkpoint 之后恢复
- **THEN** 系统 MUST 依据已持久化任务状态决定哪些任务需要继续、跳过或重试
- **THEN** 系统 MUST 不因恢复而把已完成任务重复视为新的 ready 任务

#### Scenario: Resumed execution remains externally observable
- **WHEN** 调用方在 scope review 或其他 checkpoint 之后继续执行 Deep Research
- **THEN** 系统 MUST 支持通过可观察的继续执行路径暴露恢复后的 planner、research、verify 和 report 阶段进度
- **THEN** 调用方 MUST 不需要等待隐藏的后台完成或重新发起全新研究请求，才能看到恢复后的执行过程
