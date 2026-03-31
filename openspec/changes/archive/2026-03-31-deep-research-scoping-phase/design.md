## Context

当前 Deep Research multi-agent runtime 的主路径是 `bootstrap -> plan -> dispatch -> researcher -> merge -> verify -> coordinate -> report -> finalize`。这条路径假设用户的研究目标、边界和约束在进入 planner 前已经足够明确，因此 planner 会直接把原始 topic 转成 research tasks。

这个假设对简单研究主题成立，但对复杂或高成本研究不成立，主要问题有：
- 用户经常只给出一个粗主题，没有提供研究目标、背景、排除项、来源偏好或时间范围。
- planner 直接围绕模糊 topic 开题，容易在研究开始后才发现范围漂移，浪费搜索预算。
- 现有通用 `clarify_node` 只负责入口歧义消解，不负责为 Deep Research 产出可确认的范围草案。
- 后端已有 LangGraph `interrupt()/resume` 和前端 interrupt 通道，但前端目前主要把它当作工具审批 UI，而不是 Deep Research 的 scope review UI。

这次变更是典型的跨层修改：涉及 deep runtime 子图、graph-scoped 状态、interrupt payload、流式事件语义，以及前端对中断态的消费方式，因此需要先把设计收敛清楚再实现。

## Goals / Non-Goals

**Goals:**
- 在 multi-agent Deep Research 中增加明确的前置 intake/scoping 阶段，顺序为 `clarify -> scope -> user review -> planner`。
- 让 `clarify agent` 负责补足用户背景与研究约束，`scope agent` 负责生成结构化 scope draft，`planner` 仅负责把已批准 scope 转成任务。
- 要求 scope draft 进入 planner 前必须经过用户批准，或在用户提交修改意见后由 `scope agent` 重写新版本。
- 复用现有 `interrupt/resume` 与 SSE 框架，尽量减少 API 和事件面的大改动。
- 明确禁止“用户直接修改结构化字段即生效”的路径，保持 scope 数据由 agent 统一规范化。

**Non-Goals:**
- 不改变 `legacy` Deep Research engine 的行为；第一阶段仅作用于 `multi_agent` runtime。
- 不重写外层 `route -> deepsearch` 入口协议，不新增独立 Deep Research API。
- 不在本变更中引入新的搜索提供方、验证器或 planner 策略优化。
- 不允许用户直接编辑 scope draft 内部字段后绕过 `scope agent`。
- 不要求在本变更中把 intake/scoping 状态纳入现有 artifact store 公共契约。

## Decisions

### 1. 在 planner 前新增 intake 子图，而不是复用外层通用 clarify 路由

multi-agent Deep Research 子图将扩展为：

`bootstrap -> clarify -> scope -> scope_review -> plan -> dispatch -> ...`

其中：
- `clarify` 负责判断是否已有足够背景进入 scope，如果不足则向用户提出一个聚焦的补充问题。
- `scope` 负责把 topic 与澄清结果整理为结构化 `scope draft`。
- `scope_review` 负责展示当前草案并等待用户“批准”或“提交修改意见”。
- `plan` 只能消费已批准的 scope snapshot，而不再直接消费裸 topic。

这样做的原因：
- 外层 `clarify_node` 的职责是通用路由防抖，不适合承载 Deep Research 专属的多轮范围界定协议。
- intake 子图属于 deep runtime 内部状态机，天然需要与 deep runtime 的 checkpoint、事件和 planner 输入绑定。

备选方案：
- 方案 A：复用外层 `clarify_node`，让它同时承担 Deep Research 的 intake。
  - 未选原因：会把通用路由歧义消解和 Deep Research scope 协议耦合在一起，职责过重。
- 方案 B：不新增节点，只在 `plan` 内部先做 intake prompt。
  - 未选原因：会让 `planner` 同时承担澄清、scope 建模和任务分解三种职责，违背单一职责。

### 2. intake/scoping 的权威状态放在 graph-scoped runtime_state，而不是先改 artifact store 契约

第一阶段将 intake/scoping 作为 graph-scoped 控制状态处理，建议至少包含：
- `intake_status`
- `clarify_question`
- `clarify_answer_history`
- `scope_revision_count`
- `scope_feedback_history`
- `current_scope_draft`
- `approved_scope_draft`

`planner` 只读取 `approved_scope_draft`。`current_scope_draft` 在未批准前只是候选草案。

这样做的原因：
- 这是典型的运行时控制状态，不是当前阶段必须暴露为长期共享 artifact 的研究证据。
- 可以在不修改 `deep-research-artifacts` 契约的前提下，把问题局限在 deep runtime 内部，降低首轮变更面。

备选方案：
- 将 `scope draft` 建模为新的 artifact store 类型。
  - 未选原因：会扩大 specs 与序列化契约变更面，第一阶段收益不够高。

### 3. scope 审阅复用现有 interrupt/resume，但只支持“批准”或“提交反馈重写”

`scope_review` 节点使用专用 checkpoint，例如 `deepsearch_scope_review`。它向前端输出：
- 结构化 `scope_draft`
- 人类可读的摘要内容
- 当前版本号
- 允许的动作：`approve_scope`、`revise_scope`

恢复时：
- `approve_scope`：将当前 draft 提升为 `approved_scope_draft`，进入 `plan`
- `revise_scope`：要求提供 `scope_feedback`，并回到 `scope` 生成新版本

系统明确不支持：
- 客户端直接修改 `scope_draft` 字段后作为权威数据提交
- 在没有反馈文本的情况下要求 scope agent“随便再改一版”

这样做的原因：
- 保持结构化 scope 始终由 agent 生成和规范化，避免用户直接改坏字段间一致性。
- 复用现有 `interrupt/resume` 能力，避免新增专用 API。

备选方案：
- 方案 A：允许用户在前端直接编辑字段再确认继续。
  - 未选原因：会把 schema 校验、一致性修复和冲突处理压力推给前端与恢复逻辑。
- 方案 B：新增独立 `/api/deepsearch/scope/review` 接口。
  - 未选原因：现有 interrupt/resume 已能满足暂停与恢复，不需要额外 API 面。

### 4. 复用现有事件家族，扩展 role / decision / artifact 取值，而不是新增大量事件类型

本变更优先扩展现有 Deep Research 事件：
- `research_agent_start / complete`：新增 `clarify`、`scope` 角色
- `research_decision`：新增 `clarify_required`、`scope_ready`、`scope_revision_requested`、`scope_approved` 等决策类型
- `research_artifact_update`：可增加 `artifact_type=scope_draft` 的生命周期事件

这样做的原因：
- 现有 SSE 消费链已经能识别这些事件家族，新增字段和值的兼容性更好。
- 前端可以先增量识别新角色和决策，不需要重做整个流协议。

备选方案：
- 为 intake/scoping 新增一整套全新事件类型。
  - 未选原因：事件面膨胀过快，旧客户端兼容负担更重。

### 5. 前端对 scope review 采用只读草案 + 反馈输入框，而不是可编辑表单

前端中断面板需要从“工具审批”推广为“通用 interrupt 面板”，但在 scope 审阅场景下只提供：
- 当前 scope draft 的只读展示
- 一个修改意见输入框
- `确认范围并开始研究`
- `提交修改意见`

这样做的原因：
- 与“只允许反馈驱动重写”的后端契约一致
- 前端实现更简单，不需要维护复杂的结构化表单和字段级校验

备选方案：
- 提供完整字段表单供用户直接编辑。
  - 未选原因：与本次明确的交互约束冲突，也会提高 UI 与状态校验复杂度。

## Risks / Trade-offs

- [用户确认链路变长，首次出报告更慢] → 仅在 `multi_agent` Deep Research 中启用 intake/scoping，并允许 `clarify` 在信息充分时直接进入 `scope`，减少无谓往返。
- [用户多次反馈导致 scope 无限重写] → 引入 `scope_revision_count` 和上限，超过上限时要求用户重新描述需求或人工终止。
- [前端仍按“工具审批”理解 interrupt] → 将 interrupt UI 抽象为通用 review 容器，按 `checkpoint` 类型渲染不同动作与文案。
- [未批准 scope 与已批准 scope 混淆] → 只允许 `approved_scope_draft` 驱动 planner，并在状态中显式区分 `current` 与 `approved`。
- [clarify 与 scope 边界重新模糊] → 规定 clarify 只补信息，不生成任务；scope 只产草案，不生成任务；planner 只拆任务。

## Migration Plan

1. 在 multi-agent deep runtime 中增加 intake/scoping 状态字段与初始路由逻辑。
2. 新增 `clarify`、`scope`、`scope_review` 节点，并让 `plan` 读取 `approved_scope_draft`。
3. 扩展 interrupt payload 与恢复动作，支持 `approve_scope` / `revise_scope`。
4. 扩展事件发射与前端状态映射，使 intake/scoping 过程可见。
5. 将前端 interrupt UI 抽象为可按 checkpoint 渲染的 review 面板，并为 scope 场景增加反馈输入与批准动作。
6. 补齐 runtime、interrupt/resume、SSE 和前端消费测试。

## Open Questions

- `clarify agent` 是每次只提一个问题，还是允许在单次输出中列出一个紧凑的问题集合？
- 当用户连续提交无效或过于抽象的修改意见时，是继续由 scope agent 尝试重写，还是退回 clarify 阶段重新补信息？
- scope review 阶段是否需要在会话恢复 API 中暴露专门的状态摘要，还是保持依赖通用 interrupt 状态接口即可？
