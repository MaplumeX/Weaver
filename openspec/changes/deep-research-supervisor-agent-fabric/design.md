## Context

当前 Deep Research 的 `multi_agent` 路径已经具备子图外壳、checkpoint-safe artifact/task snapshot 和 `clarify/scope` 前置门控，但正式研究阶段仍由 runtime 手写 `search -> read -> extract -> synthesize` 流程驱动。与此同时，仓库已经有通用 tool-agent middleware、受限工具选择和 HITL/limit/retry 机制，却没有真正进入 Deep Research 执行层。

这带来三个核心问题：

- `clarify/scope` 虽然已经是正式阶段，但它们还没有被纳入统一的 agent fabric 心智，正式研究开始后控制平面又退回到脚本化 runtime。
- `researcher`、`verifier`、`reporter` 仍不是严格意义上的 tool agents，无法在边界内自主规划工具调用，也无法把 follow-up、challenge 和 report handoff 表达为正式协作动作。
- 任务、artifact 和事件虽然已经结构化，但还缺少 blackboard 风格的 submit/request 协议，导致多 agent 协作更像 runtime 内部函数编排，而不是一套真正的 agent fabric。

## Goals / Non-Goals

**Goals:**

- 保留 `clarify` 和 `scope` 作为正式前置阶段，并把它们纳入统一的 Deep Research agent fabric。
- 引入 `supervisor agent` 作为唯一控制平面角色，统一负责计划、调度、replan、停止与汇总推进。
- 将 `researcher`、`verifier`、`reporter` 升级为真正的 bounded tool agents。
- 通过 blackboard/fabric tools 让 agent 使用结构化任务、artifact、result bundle 和 request 协作。
- 继续让 graph 掌握预算、并发、merge、checkpoint、resume 和最终提交权。

**Non-Goals:**

- 不移除 `legacy` deepsearch engine。
- 不把整个系统改成自由聊天式 agent society。
- 不向所有角色开放完整 tool registry。
- 不改变现有 `deep` API 入口、取消语义和最终报告输出契约。
- 不在第一阶段引入新的搜索提供商或新的持久化后端。

## Decisions

### 1. 保留 `clarify/scope`，但把它们定义为 fabric agents

`clarify` 和 `scope` 继续作为正式前置阶段存在，并且在 graph 上保持可观察、可中断、可恢复。它们不会直接做外部研究，而是作为窄职责 fabric agents 使用 intake/scope review 相关工具，对研究目标、约束、来源偏好和验收标准做结构化整理。

这样做的原因：

- 外部 Deep Research 系统普遍保留研究前澄清与范围确认，只是表达方式不同。
- 对 Weaver 而言，`clarify/scope` 已经是成立的产品交互面，去掉它们会让真正的多 agent 升级反而失去前置控制。

备选方案：

- 将 `clarify/scope` 吞并进 `supervisor`。
  - 未选原因：会让前置门控退化成内部 prompt 约定，降低可观察性和可恢复性。

### 2. 用单一 `supervisor agent` 取代 planner/coordinator 双控制面

新的控制平面由 `supervisor agent` 独占。它负责从已批准 scope 生成 branch 级任务、批准 dispatch、消费 verifier 反馈、决定 retry/replan/stop，并把已验证产物交给 reporter。原本 planner/coordinator 的职责将下沉为 supervisor 的 phase 或内部技能，而不再作为对外一等角色存在。

这样做的原因：

- 外部成熟架构更接近 orchestrator/supervisor 统一掌控控制平面，而不是 planner/coordinator 双头控制。
- 对 tool-agent 系统而言，控制平面最好只有一个最终拥有者，避免决策权分裂。

备选方案：

- 保留 planner/coordinator 两个公开角色，再分别 tool-agent 化。
  - 未选原因：控制面过碎，事件、测试和状态所有权都更复杂。

### 3. 引入 blackboard + fabric tools，而不是让 agent 直接改共享状态

多 agent 协作以 blackboard 为核心。agent 通过 fabric tools 读取 scope、任务、artifacts 和验证结论，并通过结构化 submit/request 动作提交结果。典型动作包括：

- 读取当前批准 scope、任务与 artifacts
- 创建或更新 branch task 提议
- 提交 branch result bundle
- 提交 verification bundle
- 提交 follow-up request 或 escalation
- 标记报告输入就绪

graph 仍然是唯一能把这些提交写入权威 task/artifact store 的执行面。

这样做的原因：

- 这能让真正的 tool agents 与 checkpoint-safe graph 状态自然对接。
- 它也能避免 agent 直接持有 store 引用，破坏 merge 和恢复边界。

备选方案：

- 让 agent 直接操作 task queue / artifact store。
  - 未选原因：会打破 graph 的权威状态边界，恢复和调试成本高。

### 4. 为每个角色定义独立工具表面，而不是共享完整 registry

角色工具面按职责分层：

- `clarify/scope/supervisor`: 只允许 fabric tools 与必要的轻量 planning utilities
- `researcher`: 允许搜索、浏览、抓取、抽取、必要的轻量分析工具，以及只读/提交型 fabric tools
- `verifier`: 允许反证搜索、来源阅读、抽取、对比分析工具，以及验证结果提交型 fabric tools
- `reporter`: 允许读取已验证 artifacts、必要的格式化/导出/轻量 Python 工具，以及报告提交型 fabric tools

这样做的原因：

- 真正的 tool-agent 系统靠的是“角色化工具面”，不是“所有角色都能用所有工具”。
- 这可以直接复用现有中间件栈，同时把风险面控制在可解释边界内。

备选方案：

- 所有角色共享完整工具集。
  - 未选原因：权限过大，预算与安全边界都会失控。

### 5. `researcher` 和 `verifier` 都升级为 bounded tool-agent loops

`researcher` 不再由 runtime 手写步骤驱动，而是在 branch 任务内执行受限 tool-agent loop。它可以在预算内多步调用工具，但不能直接扩图，只能提交 result bundle 或 follow-up request。

`verifier` 也不再是被动的规则/函数检查器，而是可执行 challenge/search/read/compare 的 tool agent。它的输出仍然必须落成结构化 verification artifacts，交由 supervisor 决定后续动作。

这样做的原因：

- 真正的 Deep Research 执行质量，主要取决于研究和验证环节是否能做受控多步工具自治。
- 这比单纯把 reporter 或 clarify tool-agent 化更直接改善系统能力。

备选方案：

- 只升级 researcher，verifier 保持纯函数化。
  - 未选原因：验证仍会成为控制回路中的能力短板。

### 6. `reporter` 只消费已验证 blackboard 产物

reporter 负责把已验证 branch synthesis、verification 结果和引用信息整理成最终输出。它可以使用格式化或导出工具，但不能跳过 verifier 直接消费未验证中间摘要。

这样做的原因：

- Deep Research 的最终可信度建立在“verified artifacts -> report”这条链路上。
- reporter 参与工具使用的价值，在格式化和导出，而不是重新决定事实真值。

备选方案：

- 让 reporter 重新读取原始来源并自行选择事实。
  - 未选原因：会绕开 verifier，破坏职责分离。

### 7. graph 继续保留预算、fan-out/fan-in、merge 和 checkpoint 的权威

虽然执行层升级为 tool agents，但 graph 仍是权威控制器：

- 预算在 dispatch 与 merge 边界检查
- fan-out/fan-in 由 graph 派发与汇总
- checkpoint 和 resume 只依赖权威快照，不依赖 agent 内部对象身份
- 最终写入 task/artifact store 的动作只发生在 graph 管理的提交阶段

这样做的原因：

- 这能同时保留 tool-agent 灵活性和 LangGraph 的确定性/恢复能力。

备选方案：

- 把循环完全交给 supervisor agent 自己管理。
  - 未选原因：会重新失去 checkpoint-safe 和 merge-safe 的系统边界。

## Risks / Trade-offs

- [角色切换成本上升] → 通过保留 `clarify/scope`、继续使用现有 `deep` 入口和最终报告契约，减少外部迁移面。
- [tool-agent 行为更难预测] → 通过角色化工具白名单、步骤限制、预算限制和 graph-only merge 收口行为。
- [blackboard artifacts 数量增加] → 通过区分权威 artifacts 与临时对话历史，只持久化协作必须的数据。
- [事件面变复杂] → 保留现有事件家族，只扩充 supervisor/tool-agent 所需字段和阶段语义。
- [planner/coordinator 语义迁移到 supervisor 期间可能出现双栈复杂度] → 通过明确 rollout 阶段和引擎开关控制迁移窗口。

## Migration Plan

1. 新增 Deep Research fabric tools、agent role allowlists 和 blackboard request/result schema。
2. 在 `multi_agent` runtime 内引入 `supervisor` 节点与对应快照字段，先接管计划、调度和 replan 决策。
3. 将 `researcher` 替换为 branch tool-agent runner，并让 merge 消费结构化 result bundle。
4. 将 `verifier` 升级为 challenge-oriented tool agent，并把 verification bundle 接入 supervisor 决策回路。
5. 将 `reporter` 改为只消费已验证 artifacts 的报告 agent，补齐事件、SSE 和 resume 兼容。
6. 通过 `deepsearch_engine` 或等效 runtime 开关分阶段灰度；回滚时切回现有 `legacy` 或旧 `multi_agent` 路径。

## Open Questions

- 第一阶段是否允许 `supervisor` 使用极少量只读 world tools 做 spot-check，还是完全限制为 fabric-only？
- `reporter` 在第一阶段是否需要真正的 tool loop，还是保留为“读取 blackboard + 生成报告”的轻量 agent 即可？
- follow-up request 是否应该落成独立 artifact 类型，还是先作为 artifact metadata / structured payload 过渡？
