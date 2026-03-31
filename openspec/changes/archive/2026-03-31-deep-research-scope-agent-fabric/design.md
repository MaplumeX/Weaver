## Context

当前 Deep Research 的 `multi_agent` 版本已经拆出了 `ResearchPlanner`、`ResearchAgent`、`ResearchCoordinator`、`KnowledgeGapAnalyzer`、`ResearchReporter`、`ArtifactStore` 和 `ResearchTaskQueue`，但其核心控制流仍然位于 `MultiAgentDeepSearchRuntime._run()` 的进程内循环中。对外看，`deep` 路由仍然只进入单个 `deepsearch` 节点；对内看，并行 researcher 仍通过线程池派发，而不是 LangGraph 原生 fan-out/fan-in。

这带来几个问题：
- Deep Research 虽然名义上是 multi-agent，但缺少显式的 graph-level agent fabric，LangGraph 的 checkpoint、恢复、节点级可观测性没有真正进入这条路径。
- 研究循环、任务调度、预算控制和结果合并仍然纠缠在 runtime 内部，难以把流程控制与角色职责完全分离。
- 当前 artifacts 和 runtime state 主要以进程内对象视角组织，天然不适合 graph checkpoint/resume。
- planner、coordinator、verifier、reporter 与 researcher 的自治边界没有被 graph 契约表达，后续一旦引入更强工具自治，容易重新退化成若干黑盒 agent 嵌套。

本次变更需要在保留 Deep Research 外部入口、取消语义、SSE 主协议和 legacy engine 的前提下，把 `multi_agent` 路径提升为真正的 LangGraph 编排系统。

## Goals / Non-Goals

**Goals:**
- 将 `multi_agent` Deep Research 升级为 LangGraph 管理的子图执行面，而不是单节点内部 runtime。
- 明确 Deep Research 的角色拓扑、scope 边界、artifact handoff 和 graph-level fan-out/fan-in。
- 让 multi-agent 执行天然继承 checkpoint、恢复、interrupt 和节点级事件能力。
- 保持现有 `deep` 外部入口、API 请求格式、取消语义和最终报告输出契约稳定。
- 在不推翻现有 role 实现的前提下完成编排层迁移，优先复用已有 planner/researcher/coordinator/verifier/reporter 代码。

**Non-Goals:**
- 不在本变更中移除 legacy deepsearch engine。
- 不把整个外层 `research_graph` 重写为完全动态的自由自治 agent 社交系统。
- 不要求 planner、coordinator、verifier、reporter 第一阶段都升级为自由 tool-calling agent。
- 不在本变更中引入新的外部搜索提供商、RAG 存储或额外模型供应商。
- 不改变 `direct`、`web`、`agent` 三种模式的对外协议。

## Decisions

### 1. 保留 `deepsearch_node` 作为稳定入口，但将 `multi_agent` 路径升级为 LangGraph 子图

`deepsearch_node` 继续承担外层 graph 的稳定入口、取消检查、简单问题短路和最终收尾职责；当 engine 选择 `multi_agent` 时，不再把控制权交给单个 runtime 内循环，而是启动一个编译后的 Deep Research 子图。

这样做的原因：
- 外层 API、SSE 和路由契约已经围绕 `deepsearch_node` 成熟，保留入口能最小化迁移面。
- 真正需要升级的是 deep research 内核的控制平面，而不是最外层模式路由。

备选方案：
- 直接把 planner/researcher/verifier/reporter 提升为外层主 graph 顶层节点。
  - 未选原因：会把 deep research 的内部复杂性泄露到整个主 graph，增加非 deep 模式的耦合。
- 继续保留当前 runtime，只是在内部增加更多角色类。
  - 未选原因：无法得到 graph-native checkpoint、恢复和显式 fan-out/fan-in。

### 2. 引入显式的 Deep Research agent fabric，角色职责保持窄边界

Deep Research 子图内显式建模五类角色：
- `planner`
- `coordinator`
- `researcher`
- `verifier`
- `reporter`

其中：
- `planner`、`coordinator`、`verifier`、`reporter` 保持窄职责节点，只消费结构化输入并产出结构化结果。
- `researcher` 作为执行层，允许演进为真正的工具自治 worker，但其 fan-out/fan-in 仍由 graph 控制，而不是自行无限派生任务。

这样做的原因：
- 先把控制平面做清晰，再把执行平面做自治，可以避免所有角色都演化成黑盒 agent。
- 预算、事件、测试和失败恢复更容易收口。

备选方案：
- 所有角色一开始都升级为自由 tool-calling agent。
  - 未选原因：职责重叠、预算失控、事件语义模糊，且容易再次把关键循环藏回 agent 内部。

### 3. 采用三层 scope 模型：graph scope、branch scope、worker scope

Deep Research 状态按所有权拆分为三层：
- `graph scope`：主题、预算、全局任务队列、artifact snapshot、agent run ledger、最终汇总态
- `branch scope`：某一研究分支或专题的 brief、pending tasks、局部 coverage/gap 视图
- `worker scope`：单个 researcher 执行所需的 task brief、相关 artifacts、临时推理上下文和产出 payload

跨 scope 的交接只通过结构化 payload 和 artifact snapshot 完成，不共享 sibling 的完整消息历史。

这样做的原因：
- 这是把“runtime 内 task-scoped context”升级为 graph-native state scope 的必要前提。
- 便于在 checkpoint/resume 时只恢复权威状态，而不依赖进程内对象身份。

备选方案：
- 继续把 deep research 中间态堆叠在共享 `AgentState` 顶层。
  - 未选原因：会重新放大状态蔓延，且 scope 所有权不清。

### 4. 任务分发从线程池切换为 LangGraph fan-out/fan-in

当 coordinator 批准执行 ready tasks 时，graph 通过 `Send` 或等价的 LangGraph 分发机制为每个 task 派生独立 researcher 执行路径；worker 完成后回到 merge/reduce 节点统一合并 artifacts、任务状态和预算消耗。

这样做的原因：
- fan-out/fan-in 变成图的一部分后，才能自然获得 checkpoint、恢复、节点级追踪和更清晰的事件边界。
- 并发行为不再埋在单节点线程池内部。

备选方案：
- 保留 `ThreadPoolExecutor`，只在外层包一层 graph node。
  - 未选原因：这是“图形化包装”，不是真正的编排迁移。

### 5. Artifact store 改为 checkpoint-safe 的权威协作介质

保留 `ResearchTask`、`BranchBrief`、`EvidenceCard`、`KnowledgeGap`、`ReportSectionDraft`、`FinalReportArtifact` 这些概念，但它们在 graph 执行中必须表现为可序列化 snapshot，而不是只依赖运行时对象与锁。

运行时可以保留轻量 facade 或 view helper，但权威状态必须可从 graph checkpoint 恢复。

这样做的原因：
- LangGraph 恢复要求权威状态可序列化、可重建。
- verifier、reporter 和 coordinator 应当依赖 artifact truth，而不是进程内对象引用。

备选方案：
- 继续把 `ArtifactStore` 和 `ResearchTaskQueue` 作为纯运行时内存对象长期持有。
  - 未选原因：恢复、调试和回放都会失真。

### 6. 事件模型升级为 graph-native 关联语义

现有 `research_agent_*`、`research_task_update`、`research_artifact_update`、`research_decision` 事件继续保留，但补充或收紧以下关联字段：
- `graph_run_id`
- `node_id`
- `branch_id`
- `task_id`
- `agent_id`
- `attempt`
- `parent_task_id` / `parent_branch_id`

事件应以 graph 步骤和角色生命周期为边界发出，而不是仅以 runtime 内部函数调用为边界。

这样做的原因：
- 前端 timeline 需要稳定关联 fan-out worker、resume attempt 和汇总阶段。
- graph retry/checkpoint 下必须能区分“同一任务的重试”与“新任务”。

备选方案：
- 维持现有事件名和最小字段集合。
  - 未选原因：一旦进入 graph-native 执行，前端和调试侧无法稳定辨别节点重放与真实新执行。

## Risks / Trade-offs

- [编排复杂度上升] → 通过保留外层入口稳定、优先迁移控制平面、复用现有 role 实现控制首阶段范围。
- [state/store 重构成本较高] → 先将权威状态收敛为可序列化 snapshot，再保留 facade 兼容层，避免一次性推翻所有内部 helper。
- [graph retry 可能导致重复事件] → 通过稳定关联字段和 attempt 计数降低歧义，并在前端消费层做去重。
- [researcher 自治与 coordinator 控制之间可能拉扯] → 第一阶段仅 researcher 允许向工具自治演进，且任务派生权仍保留给 coordinator。
- [legacy 与 graph-native multi-agent 并存增加维护成本] → 通过明确 engine 开关、统一入口与公共测试矩阵限制分叉持续时间。

## Migration Plan

1. 保留现有 `deepsearch_node` 外壳，新增 Deep Research 子图入口和独立 state schema，不改变外部请求格式。
2. 将现有 `MultiAgentDeepSearchRuntime` 的主循环拆解为 graph 节点：bootstrap、plan、dispatch、merge、verify、coordinate、report、finalize。
3. 将任务分发从线程池迁移为 LangGraph fan-out/fan-in；保留现有 researcher 逻辑作为 worker 内核。
4. 将 `task_queue`、`artifact_store`、`runtime_state`、`agent_runs` 收敛为 checkpoint-safe snapshot，并为现有 helper 提供兼容 facade。
5. 补齐 graph-native 事件关联字段和前端消费逻辑，确保旧客户端忽略新增字段时仍能正常拿到最终结果。
6. 补齐 graph orchestration、resume、artifact merge、event correlation 和 legacy engine 共存测试后，再评估是否提升 `multi_agent` 为默认 engine。

## Open Questions

- `multi_agent` 何时从实验开关升级为默认 deep engine，应以哪些稳定性指标作为门槛？
- 第一阶段 researcher 是否仅复用当前搜索封装，还是同时接入通用 LangChain tool-calling 中间件？
