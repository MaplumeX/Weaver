## ADDED Requirements

### Requirement: Public Deep Research events carry stable iteration grouping metadata
系统 MUST 为正式研究循环中的公开 Deep Research 事件提供稳定的轮次归属语义，使前端无需依赖事件到达时间推断同一任务、产物或验证结果属于哪一轮。

#### Scenario: Branch task update belongs to a formal iteration
- **WHEN** 正式研究循环中的 branch task 发出 `research_task_update`
- **THEN** 事件 MUST 包含稳定的 `iteration`、`branch_id`、`task_kind` 和 `stage`
- **THEN** 客户端 MUST 能仅基于公开事件字段把该更新归档到单一轮次与单一 branch

#### Scenario: Branch artifact update belongs to a formal iteration
- **WHEN** 正式研究循环中的 branch-scoped artifact 或 verification artifact 发出 `research_artifact_update`
- **THEN** 事件 MUST 包含稳定的 `iteration` 以及关联该 artifact 所需的 branch / task 上下文字段
- **THEN** 客户端 MUST 能把该 artifact 更新挂到正确的轮次和分支摘要下，而不需要猜测时间窗口

#### Scenario: Retry or resume preserves run continuity metadata
- **WHEN** 某个 branch 在 checkpoint 恢复或重试后继续发出 `research_agent_*`、`research_task_update`、`research_artifact_update` 或 `research_decision`
- **THEN** 这些事件 MUST 保留 `graph_run_id`、`resumed_from_checkpoint`、`attempt` 和 `iteration` 等公开连续性字段
- **THEN** 客户端 MUST 能把这些事件识别为同一研究流程的后续进展，而不是新的无关流程

### Requirement: Canonical structured events are sufficient for timeline projection
系统 MUST 让 Deep Research 的公开结构化事件本身足以支持 thinking timeline 投影，而不是要求前端依赖 companion generic events 才能得到完整进度语义。

#### Scenario: Client renders task lifecycle without generic companion events
- **WHEN** 前端仅消费 `research_task_update`、`research_agent_*`、`research_artifact_update` 和 `research_decision`
- **THEN** 它 MUST 仍能识别任务状态、分支归属、阶段推进和轮次归属
- **THEN** companion generic events 的抑制、缺失或去噪 MUST NOT 造成唯一进度信息丢失

#### Scenario: Startup and loop phases remain understandable from structured events
- **WHEN** 客户端基于公开 Deep Research 事件渲染 `intake`、`scope`、`planning`、`branch research`、`verify` 或 `report`
- **THEN** 结构化事件 MUST 提供足够的公开 phase 语义，使客户端无需依赖重复的 generic `status`、`thinking` 或 `task_update` 文案
- **THEN** 客户端 MUST 不需要解析内部状态对象或非公开 runtime 结构，才能组织用户级 timeline
