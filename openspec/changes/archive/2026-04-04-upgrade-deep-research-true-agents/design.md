## Context

当前 Deep Research 已经收敛到单一 `multi_agent` runtime，并且 branch 级 `researcher` / `verifier` / `reporter` 已具备 bounded tool-agent 的雏形。但控制平面仍主要依赖 graph node 路由与 `next_step` 字段表达阶段推进，缺少“当前由谁持有控制权”的一等状态，也没有结构化 handoff payload 来表达 agent 之间的权威移交。

这带来三个问题：

- 架构语义与 LangChain 官方 multi-agent 模式不完全对齐。当前系统更像 graph-driven orchestration with embedded tool agents，而不是显式的 handoff + subagent hybrid。
- checkpoint/resume 只能较好恢复执行步骤，不能稳定恢复控制平面所有权与移交上下文。
- `clarify`、`scope`、`supervisor`、`researcher`、`verifier`、`reporter` 的职责边界虽然在 specs 中已较清楚，但在运行时表示上仍不够统一，导致后续演进容易继续把控制语义塞回 graph 分支判断。

本次设计目标是在不破坏现有 branch 并发、artifact store、verification pipeline 和 outline gate 的前提下，把控制平面升级为 handoff 模型，并让 `supervisor` 成为唯一的全局控制平面 owner。

## Goals / Non-Goals

**Goals:**

- 将 `clarify`、`scope`、`supervisor` 建模为显式的 control-plane handoff agents。
- 引入稳定的控制平面状态，至少包括 `active_agent`、结构化 handoff payload 和 handoff history。
- 保留并强化 `researcher`、`verifier`、`reporter` 的 bounded tool-agent 能力，并明确它们由 `supervisor` 以 subagent 方式调用。
- 让 checkpoint/resume 能恢复控制平面 owner、handoff 上下文和当前研究阶段，而不仅是 graph node 路径。
- 保持现有 branch fan-out/fan-in、artifact merge、verification contracts 和 outline gate 能力不退化。

**Non-Goals:**

- 不在本次变更中引入新的外部依赖或替换 LangGraph/LangChain 基础设施。
- 不把所有角色都改造成可直接与用户对话的 handoff agents。
- 不重写现有 verification pipeline、artifact schema 或 Deep Research 对外 API。
- 不在本次变更中放宽任何 world-facing tool 的权限边界。

## Decisions

### 决策 1：采用 “handoff 控制平面 + subagent 执行平面” 的混合拓扑

`clarify`、`scope`、`supervisor` 构成控制平面 handoff 链。它们共享同一研究会话，但每个阶段都由显式 `active_agent` 持有控制权。`researcher`、`verifier`、`reporter` 不进入 handoff 链，而是由 `supervisor` 作为 subagent 调用。

原因：

- `clarify` / `scope` / `supervisor` 的核心问题是“谁当前负责推进流程”，这正是 handoff 语义。
- `researcher` / `verifier` 天然需要并发、上下文隔离、预算约束和统一回收结果，更适合 subagent。
- `reporter` 第一阶段保留为 subagent 更稳，避免把写作阶段变成新的控制平面 owner；如果后续需要交互式改稿，再独立升级为 handoff agent。

备选方案：

- 所有角色统一改成 handoff。放弃，因为会破坏 branch 并发模型，并让 `researcher` / `verifier` 失去受控 fan-out/fan-in 的天然表示。
- 所有角色继续保持 graph node + tool agent。放弃，因为无法解决控制平面 owner 不显式、resume 语义不完整的问题。

### 决策 2：`supervisor` 是唯一全局控制平面 owner

`supervisor` 拥有唯一的全局调度权限，负责：

- 读取和解释 `research brief`、ledgers、verification artifacts、outline gate 状态。
- 决定何时 dispatch、retry、replan、spawn revision branch、enter outline gate、call reporter 或 bounded stop。
- 以 subagent 方式调用 `researcher`、`verifier`、`reporter`。

`clarify` 与 `scope` 只拥有 intake/scoping 阶段的局部控制权，且最终都必须 handoff 回 `supervisor`。`researcher`、`verifier`、`reporter` 不得直接获得全局控制权。

原因：

- 当前 specs 已经把 `supervisor` 定义为唯一控制平面角色，本次需要在运行时表示上补齐这一点。
- 这样可以避免 request、revision issue、outline gap 和 replan 分散在多个角色中各自做决策。

备选方案：

- 允许 `verifier` 或 `reporter` 直接 handoff 给用户或其他角色。放弃，因为会让控制面重新分叉，削弱 `supervisor` 的权威性。

### 决策 3：引入结构化 handoff 状态，而不是只扩展 `next_step`

runtime state 新增如下核心字段：

- `active_agent`: 当前持有控制权的 control-plane agent，取值为 `clarify` / `scope` / `supervisor`。
- `handoff_envelope`: 最新一次 handoff 的结构化载荷，至少包含 `from_agent`、`to_agent`、`reason`、`context_refs`、`scope_snapshot`、`review_state`、`created_at`。
- `handoff_history`: handoff 事件历史，用于 resume、调试和 UI 可观测性。

`next_step` 暂时保留，作为 graph 路由兼容层；但恢复时优先依据 `active_agent` 与 `handoff_envelope` 推导下一步。

原因：

- `next_step` 适合节点跳转，不适合表达控制权所有者。
- handoff payload 需要引用 artifact 和上下文，而不是让下游 agent 重新从自由文本历史中推断。

备选方案：

- 继续让 `next_step` 承载控制语义。放弃，因为字段职责会继续混乱，也不利于测试和公开观测。

### 决策 4：handoff 与 coordination request 明确分层

handoff 只用于控制平面 agent 之间的所有权转移，例如：

- `clarify -> scope`
- `scope -> supervisor`
- `supervisor -> scope`（要求重写 scope）

coordination request 继续用于执行平面反馈，例如：

- `retry_branch`
- `need_counterevidence`
- `outline_gap`
- `blocked_by_tooling`

`researcher`、`verifier`、`reporter` 不直接产生 handoff，而是提交 request、bundle、issue 或 report artifact，由 `supervisor` 决定是否触发新的控制平面 handoff。

原因：

- handoff 是 owner change。
- coordination request 是 execution feedback。
- 把这两层混在一起会让 runtime 又回到“谁都能推动流程”的状态。

### 决策 5：控制平面 agent 也改为 bounded tool agents，但只暴露 fabric-only tools

`clarify`、`scope`、`supervisor` 从普通 LLM wrapper 升级为 bounded tool agents，不过只允许使用 fabric-only tools，例如读取 intake summary、写入 scope draft、提交 handoff、读取 ledgers、提交 supervisor decisions。

原因：

- 这样所有角色都能统一进入 agent/tool 运行时模型，减少一半是 node、一半是 agent 的不对称。
- 同时保留现有权限边界，不让控制平面直接触达搜索或抓取工具。

备选方案：

- 继续让控制平面角色使用裸 `llm.invoke`。放弃，因为这样 handoff 只存在于 graph 外围，无法形成一致的 agent 契约。

### 决策 6：`reporter` 第一阶段保持为 `supervisor` 调用的 subagent

`reporter` 默认不进入 handoff 控制链。只有 outline artifact 就绪、无阻塞性 gap、且 `supervisor` 明确决定进入写作阶段时，才由 `supervisor` 调用 `reporter` subagent。

原因：

- 报告生成仍然是执行动作，不是控制权分配。
- 当前系统已经有较成熟的 outline gate 和 reporter tool-agent 路径，保留 subagent 可以把改造风险集中在控制平面。

备选方案：

- 立刻把 `reporter` 加入 handoff。暂不采用，因为这会扩大变更面，并增加 interactive drafting 相关语义，而当前用户目标主要是重构 Deep Research 多智能体系统。

## Risks / Trade-offs

- [handoff 状态与现有 `next_step` 双轨并存会引入短期复杂度] → 通过“handoff 为权威、`next_step` 为兼容路由”的规则限制分歧，并增加状态一致性测试。
- [控制平面 agent 化后，graph 代码与 fabric tools 的边界会重新分配] → 优先抽离最小 handoff/fabric 接口，避免一次性重写所有节点。
- [resume 逻辑可能出现恢复到错误 owner 的问题] → 为 `active_agent` / `handoff_envelope` 建立序列化和恢复测试，并在恢复时做 state validation。
- [若误把执行反馈升级为 handoff，`supervisor` 权限边界会再次变糊] → 明确规定只有 control-plane role 可以产生 handoff，execution role 只能提交 request/bundle。
- [`reporter` 保持 subagent 会让“对话式改稿”能力暂时不是一等手段] → 明确这属于后续增量，而不是本次 true-agents 改造的阻塞项。

## Migration Plan

1. 扩展 schema/runtime state，加入 `active_agent`、`handoff_envelope`、`handoff_history`，同时保留 `next_step`。
2. 为控制平面定义 handoff/fabric 接口，并让 `clarify`、`scope`、`supervisor` 逐步迁移到 bounded tool-agent 实现。
3. 调整 graph 路由，使 intake/scoping/brief 阶段优先由 handoff owner 驱动。
4. 保持现有 `researcher`、`verifier`、`reporter` subagent 路径不退化，仅把调用入口统一收口到 `supervisor`。
5. 更新 public artifacts / events / resume 载荷，使外部可观察到当前 active control-plane agent 与 handoff 状态。
6. 在完成兼容验证后，再逐步弱化对纯 `next_step` 驱动的依赖。

回滚策略：

- 若控制平面 handoff 引入严重回归，可保留 schema 扩展字段但回退到现有 graph-driven owner 推导逻辑。
- 由于不引入外部依赖且保留 `next_step`，回滚主要是运行时分支切换，不涉及数据迁移。

## Open Questions

- `reporter` 是否需要在后续版本升级为可与用户继续交互的 handoff agent，而不是长期停留在 subagent 形态。
- handoff history 是否需要成为一等 artifact 持久化对象，还是先保留在 runtime/public snapshot 中即可。
- UI 是否需要显式展示 `active_agent` 与最近一次 handoff reason，还是仅用于调试与恢复链路。
