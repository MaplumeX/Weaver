## MODIFIED Requirements

### Requirement: Deep Research intake gates planning
系统 MUST 在 `multi_agent` Deep Research 中先完成 clarify/scoping，并在 scope 审批后生成结构化 `research brief`，再允许 `supervisor` 进入正式计划与调度。

#### Scenario: Clarify runs before scope draft creation
- **WHEN** 一个新的 `multi_agent` Deep Research 请求进入 deep runtime
- **THEN** 系统 MUST 先触发 `clarify agent` 判断是否已具备足够的研究背景、目标和约束
- **THEN** 系统 MUST 只在 intake 已准备完成后再触发 `scope agent`

#### Scenario: Planning waits for approved scope and research brief
- **WHEN** 当前研究请求还没有已批准的 scope draft，或已批准 scope 尚未被归一化为权威 `research brief`
- **THEN** 系统 MUST NOT 让 `supervisor` 生成正式研究任务
- **THEN** 系统 MUST 继续停留在 intake/scoping 或 brief handoff 阶段直到 `research brief` 就绪

### Requirement: Approved scope becomes the supervisor contract
系统 MUST 将用户明确批准的 scope snapshot 先转换为结构化 `research brief`，并让该 brief 成为 `supervisor` 与后续研究循环的唯一上游范围契约。

#### Scenario: User approves the draft
- **WHEN** 用户明确批准当前 scope draft
- **THEN** 系统 MUST 将该版本记录为已批准 scope
- **THEN** 系统 MUST 基于该已批准 scope 生成结构化 `research brief`，并让 `supervisor` 只读取该 brief 进入正式规划

#### Scenario: Revised drafts do not override the authoritative brief implicitly
- **WHEN** 系统仍处于 scope 修订过程中且用户尚未批准最新草案
- **THEN** 系统 MUST NOT 将任何候选 scope draft 或未重新生成的 brief 自动视为新的权威规划契约
- **THEN** 后续研究循环 MUST 保持阻塞状态或继续使用最近一次已批准且已归一化的权威 brief

#### Scenario: Approval handoff remains visible after scope review
- **WHEN** 用户批准当前 scope draft 并且系统开始生成 `research brief`
- **THEN** 系统 MUST 让用户继续观察到从 scope approval 进入 brief handoff 与 planning 的后续进展
- **THEN** 客户端 MUST 不需要额外刷新或静默等待最终结果，才能知道批准后的流程已经继续执行
