## Purpose
定义 multi-agent Deep Research 在正式研究前的 intake/scoping 门控、scope 审阅与批准契约。

## Requirements

### Requirement: Deep Research intake gates planning
系统 MUST 在 `multi_agent` Deep Research 中先完成 intake/scoping，再允许 planner 生成研究任务。

#### Scenario: Clarify runs before scope draft creation
- **WHEN** 一个新的 `multi_agent` Deep Research 请求进入 deep runtime
- **THEN** 系统 MUST 先触发 `clarify agent` 判断是否已具备足够的研究背景、目标和约束
- **THEN** 系统 MUST 只在 intake 已准备完成后再触发 `scope agent`

#### Scenario: Planning waits for approved scope
- **WHEN** 当前研究请求还没有已批准的 scope draft
- **THEN** 系统 MUST NOT 让 `planner` 直接基于原始 topic 生成研究任务
- **THEN** 系统 MUST 继续停留在 intake/scoping 阶段直到 scope 被批准

### Requirement: Scope draft is structured and reviewable
系统 MUST 让 `scope agent` 产出结构化且可审阅的 scope draft，供用户在进入研究前确认范围。

#### Scenario: Scope agent generates initial draft
- **WHEN** clarify 阶段确认已具备足够上下文
- **THEN** `scope agent` MUST 生成一个结构化 scope draft
- **THEN** 该草案 MUST 能表达研究目标、核心问题、纳入范围、排除范围、约束或偏好等范围信息

#### Scenario: User reviews draft before research begins
- **WHEN** scope agent 产出新的 scope draft
- **THEN** 系统 MUST 在进入 planner 前将该草案展示给用户审阅
- **THEN** 系统 MUST 通过可恢复的暂停点等待用户批准或提出修改意见

### Requirement: Scope revisions are feedback-driven
系统 MUST 仅允许用户通过自然语言修改意见驱动 scope 重写，而不是直接编辑结构化字段并立即生效。

#### Scenario: User requests scope revision
- **WHEN** 用户认为当前 scope draft 需要修改
- **THEN** 系统 MUST 接收用户的自然语言 `scope_feedback`
- **THEN** 系统 MUST 将当前草案与该反馈交给 `scope agent` 生成新的草案版本

#### Scenario: Direct field edits are not authoritative
- **WHEN** 客户端试图直接提交修改后的 scope draft 字段作为已确认范围
- **THEN** 系统 MUST NOT 将该字段集视为权威的已批准 scope
- **THEN** 系统 MUST 要求通过批准当前草案或提交修改意见来推进流程

### Requirement: Approved scope becomes the planner contract
系统 MUST 将用户明确批准的 scope snapshot 作为 planner 与后续研究循环的唯一上游范围契约。

#### Scenario: User approves the draft
- **WHEN** 用户明确批准当前 scope draft
- **THEN** 系统 MUST 将该版本记录为已批准 scope
- **THEN** planner MUST 基于该已批准 scope 而不是未批准候选草案生成研究任务

#### Scenario: Revised drafts do not override approval implicitly
- **WHEN** 系统仍处于 scope 修订过程中且用户尚未批准最新草案
- **THEN** 系统 MUST NOT 将任何候选 scope draft 自动视为已批准
- **THEN** 后续研究循环 MUST 保持阻塞状态
