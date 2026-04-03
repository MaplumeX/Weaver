## Context

当前 Deep Research 已经收敛到单一 `multi_agent` runtime，并具备清晰的 `scope -> supervisor -> branch dispatch -> verify -> report` 主干、artifact blackboard、任务队列和 checkpoint/resume 能力。但这条主干仍有 5 个会持续放大复杂度的问题：

- `scope` 审批之后直接进入计划，缺少一个稳定的机器契约，导致 `supervisor` 需要从已批准 scope 中临时推断研究目标、验收维度和来源偏好。
- `supervisor` 当前主要依赖计数器、摘要和少量结构化结果做决策，无法把 branch 目标、coverage target、失败原因和未决请求表达成正式控制面状态。
- `verify` 仍偏向给出 coverage/gap 摘要，而不是显式沉淀“哪个维度没覆盖、哪些结论互相冲突、哪些证据缺失”。
- `report` 直接消费已验证 branch synthesis，缺少统一的 outline gate，导致最终报告结构与研究阶段的 branch 划分容易脱节。
- `coordination request` 还是开放式结构，后续如果继续扩展 agent 行为，控制回路会越来越依赖自由文本解释。

本次设计只覆盖前述 5 个协议级重构，不包含 branch revision loop、额外 HITL 入口或新的 runtime 形态。

## Goals / Non-Goals

**Goals:**

- 在 scope approval 之后引入结构化 `research brief`，作为 `supervisor` 进入正式规划前的唯一机器契约。
- 为 `supervisor` 建立 `task ledger` 与 `progress ledger`，让计划、调度、重规划和停止决策有明确状态载体。
- 在 `verify` 与最终 `report` 之间插入 `outline gate`，先生成可验证的报告结构，再进入最终汇总。
- 将验证结果升级为 `coverage matrix`、`contradiction registry` 和 `missing evidence list` 等结构化 artifacts。
- 将 `coordination request` 收敛为有限类型集合：`retry_branch`、`need_counterevidence`、`contradiction_found`、`outline_gap`、`blocked_by_tooling`。

**Non-Goals:**

- 不新增第二套 Deep Research runtime，也不恢复 tree/linear/legacy 控制面。
- 不把系统改成自由对话式 swarm 或开放式 agent society。
- 不在本次设计中引入 `needs_human_decision`、新的人工审批入口或额外 scope review 回路。
- 不在本次设计中引入 branch revision loop、多 writer 并行写作或新的外部搜索提供商。
- 不改变外部 `deep` 入口、最终报告公开接口或非 Deep 模式的执行路径。

## Decisions

### 1. Approved scope 先归一化为 `research brief`，再进入正式规划

`scope_review` 批准后的结果不再直接喂给 `supervisor`。graph 会先生成一个结构化 `research brief` artifact，再由 `supervisor_plan` 读取该 brief 做 branch 分解。

`research brief` 至少包含：

- 研究主题与用户目标
- 核心问题与比较维度
- 明确纳入 / 排除范围
- 交付格式约束
- 来源偏好与时间边界
- 覆盖维度与基础验收标准

这样做的原因：

- `scope draft` 面向用户审阅，强调可读性；`research brief` 面向控制面，强调可执行性。
- 这可以把“人类可读范围确认”和“机器可执行规划契约”解耦，减少 `supervisor` 对原始文本语义的重复推断。

备选方案：

- 继续让 `supervisor` 直接消费 approved scope。
  - 未选原因：scope 越丰富，控制面 prompt 和后续计划越容易出现隐式字段漂移。

### 2. `supervisor` 用双账本表达控制面，而不是继续依赖轻量摘要

新增两类权威 artifacts：

- `task ledger`：记录 branch 目标、coverage target、依赖、优先级、当前状态和上游 artifact 引用。
- `progress ledger`：记录每轮决策、未决 request、阻塞原因、失败分类、预算停止原因和重规划依据。

`task queue` 继续承担调度职能，但不再独自承载控制面语义；账本负责解释“为什么有这些任务、这些任务服务于哪些 coverage target、为什么下一步是 replan 而不是 report”。

这样做的原因：

- `task queue` 擅长表达领取和状态流转，不擅长表达研究意图与决策历史。
- 双账本能让 `supervisor` 决策更可审计，也为 checkpoint/resume 后的恢复上下文提供更稳定的解释面。

备选方案：

- 把 ledger 信息继续塞进 runtime state 的聚合字段或 task metadata。
  - 未选原因：状态职责会越来越混杂，调试时难区分“调度事实”和“控制面推理依据”。

### 3. `outline gate` 是 report 之前的必经阶段，但不是多 writer 系统

在 `verify` 和 `report` 之间新增 graph-controlled `outline gate`。它只消费已验证的 branch synthesis、coverage matrix、contradiction registry 和 missing evidence list，并输出：

- `outline artifact`
- 可选的 `outline_gap` coordination request

`reporter` 只有在 outline 已就绪且不存在阻塞性的 `outline_gap` 时才能进入最终报告生成。最终报告仍保持单次汇总，不拆成多 branch writer。

这样做的原因：

- 研究完成不等于报告结构已经收敛。
- 先固定 outline，可以把“结构缺口”与“事实缺口”分开处理，避免 reporter 在最终成文阶段重新承担规划职责。

备选方案：

- 维持现状，直接让 reporter 从 verified branch syntheses 生成最终报告。
  - 未选原因：报告结构质量会继续依赖 reporter 临场组织，难以复用验证阶段形成的 coverage 信号。

### 4. 验证改为显式多 artifact 输出，而不是只给 summary/gap

`verifier` 产物升级为以下结构化 artifacts：

- `coverage matrix`：按研究维度、核心问题或比较轴记录覆盖状态与证据支撑情况
- `contradiction registry`：记录冲突 claim、冲突来源、冲突范围和建议处理动作
- `missing evidence list`：记录仍缺少的证据、需要的来源类型和受影响的结论

原有质量摘要可以继续存在，但降级为导出或 UI 视图，不再作为 `supervisor` 的主要决策输入。

这样做的原因：

- `supervisor` 需要知道“缺什么”，而不只是“分数够不够”。
- 这些 artifacts 也能直接供 `outline gate` 判断结构是否已满足写作前提。

备选方案：

- 保留单一 gap analysis，并把细节塞进自由文本 summary。
  - 未选原因：恢复、测试和重规划会继续依赖重新解析自然语言。

### 5. `coordination request` 使用封闭类型集合，不引入新的人工决策类型

`coordination request` 统一为闭合集合：

- `retry_branch`
- `need_counterevidence`
- `contradiction_found`
- `outline_gap`
- `blocked_by_tooling`

所有 request 必须带上 request type、影响范围、原因、阻塞级别、相关 artifact 引用和建议下一步动作。`supervisor` 是唯一消费和决策方。

这样做的原因：

- 闭合集合可以防止控制回路逐渐退回到自由文本协议。
- 不引入 `needs_human_decision`，能保持本次变更聚焦于系统内闭环，不扩大产品交互面。

备选方案：

- 允许开放式 request type 或直接加入新的人工决策请求。
  - 未选原因：会放大控制面复杂度，也不符合本次变更仅覆盖 1-5 步的边界。

## Risks / Trade-offs

- [Artifacts 数量增加] → 通过继续使用 canonical artifact store，并把对外公开视图做成派生结果，避免公开接口同步膨胀。
- [Outline gate 增加一个阶段，可能拉长完成时间] → 保持 outline gate 只消费已验证 artifacts，不做新的 world-facing 搜索。
- [Task queue 与 ledgers 可能出现状态漂移] → 所有 ledger 更新都只允许在 graph merge 阶段与 task/artifact 更新一起提交。
- [Verifier 输出更复杂，测试面扩大] → 以 `coverage matrix`、`contradiction registry`、`missing evidence list` 为独立测试对象，而不是只测最终 summary 文本。
- [Request taxonomy 过早收敛可能限制未来扩展] → 先使用封闭集合，后续若确有必要再通过 spec 显式新增类型，而不是默许自由扩展。

## Migration Plan

1. 为 Deep Research artifact/store/schema 增加 `research brief`、双 ledger、增强验证 artifacts 和收敛后的 coordination request 类型。
2. 在 multi-agent graph 中插入 `research brief` 生成阶段与 `outline gate`，并扩展 runtime snapshot 以承载新状态。
3. 调整 `supervisor` 输入与决策逻辑，使其优先消费 brief、ledgers 和增强验证 artifacts。
4. 调整 `verifier` 与 `reporter` 的输入输出契约，确保最终报告只在 outline 就绪后执行。
5. 补齐事件、测试与文档，确保 resume、SSE 和公共 artifacts 视图覆盖新增阶段。

## Open Questions

- `outline gate` 首版更适合实现为 `reporter` 的预写作阶段，还是单独的 graph node/role？本次 spec 只要求它是一个独立 gate，不强制具体类边界。
- `coverage matrix` 的维度枚举是完全来自 `research brief`，还是允许 verifier 在执行期补充新维度？本次设计倾向“brief 提供主维度，verifier 可追加候选维度但需显式标注来源”。
