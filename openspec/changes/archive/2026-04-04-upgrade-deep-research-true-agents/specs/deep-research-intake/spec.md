## MODIFIED Requirements

### Requirement: Deep Research intake gates planning
系统 MUST 在 `multi_agent` Deep Research 中先完成由 control-plane handoff 驱动的 clarify/scoping，并在 `supervisor` 收到权威 `research brief` handoff 后才允许进入正式计划与调度。

#### Scenario: Clarify hands control to scope before draft creation
- **WHEN** 一个新的 `multi_agent` Deep Research 请求进入 deep runtime 且当前仍需要 intake 判断
- **THEN** 系统 MUST 先触发 `clarify agent` 持有控制权并判断是否已具备足够的研究背景、目标和约束
- **THEN** 系统 MUST 只在 `clarify` 显式 handoff 给 `scope` 后再触发 `scope agent`

#### Scenario: Planning waits for supervisor to receive the approved brief handoff
- **WHEN** 当前研究请求还没有已批准的 scope draft，或已批准 scope 尚未被 handoff 为权威 `research brief`
- **THEN** 系统 MUST NOT 让 `supervisor` 生成正式研究任务
- **THEN** 系统 MUST 继续停留在 intake/scoping 或 brief handoff 阶段直到 `supervisor` 收到权威 brief

### Requirement: Scope draft is structured and reviewable
系统 MUST 让 `scope agent` 在持有当前 control-plane 所有权时产出结构化且可审阅的 scope draft，供用户在进入研究前确认范围，并在审阅暂停前后保留可理解的 review 与 handoff 上下文。

#### Scenario: Scope agent generates a reviewable draft while holding control
- **WHEN** clarify 阶段确认已具备足够上下文并将控制权 handoff 给 `scope`
- **THEN** `scope agent` MUST 生成一个结构化 scope draft
- **THEN** 该草案 MUST 能表达研究目标、核心问题、纳入范围、排除范围、约束或偏好等范围信息

#### Scenario: User reviews draft before research begins
- **WHEN** `scope agent` 产出新的 scope draft
- **THEN** 系统 MUST 在进入 `supervisor` 正式计划前将该草案展示给用户审阅
- **THEN** 系统 MUST 通过可恢复的暂停点等待用户批准或提出修改意见

#### Scenario: Review context survives pause and restore with ownership intact
- **WHEN** scope 审阅阶段被暂停、恢复或再次进入审阅
- **THEN** 系统 MUST 保留当前草案版本、审阅状态、当前 `active_agent` 和最近一次 handoff 原因
- **THEN** 用户 MUST 能理解当前草案是在等待批准、等待重写，还是刚刚生成的新版本

### Requirement: Approved scope becomes the supervisor contract
系统 MUST 将用户明确批准的 scope snapshot 先转换为结构化 `research brief`，并通过显式 handoff 交给 `supervisor`，让该 brief 成为后续研究循环的唯一上游范围契约。

#### Scenario: User approves the draft
- **WHEN** 用户明确批准当前 scope draft
- **THEN** 系统 MUST 将该版本记录为已批准 scope
- **THEN** 系统 MUST 基于该已批准 scope 生成结构化 `research brief`，并将控制权 handoff 给 `supervisor`

#### Scenario: Revised drafts do not override the authoritative brief implicitly
- **WHEN** 系统仍处于 scope 修订过程中且用户尚未批准最新草案
- **THEN** 系统 MUST NOT 将任何候选 scope draft 或未重新生成的 brief 自动视为新的权威规划契约
- **THEN** 后续研究循环 MUST 保持阻塞状态或继续使用最近一次已批准且已归一化的权威 brief

#### Scenario: Approval handoff remains visible after scope review
- **WHEN** 用户批准当前 scope draft 并且系统开始生成 `research brief`
- **THEN** 系统 MUST 让用户继续观察到从 scope approval 进入 brief handoff 与 `supervisor` planning 的后续进展
- **THEN** 客户端 MUST 不需要额外刷新或静默等待最终结果，才能知道批准后的流程已经继续执行

