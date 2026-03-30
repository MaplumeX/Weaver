## Context

当前 Deep Research 的默认生产路径是 `route=deep -> deepsearch_node -> run_deepsearch_auto()`，tree/linear runner 在单个 deep runtime 内部完成查询生成、搜索、阅读、总结、质量判断和最终报告生成。仓库虽然已经有 `ResearchCoordinator`、`ResearchPlanner`、`ResearchAgent`、`ResearchReporter`、`sub_agent_contexts` 与 branch context fork/merge 等零件，但这些能力没有形成默认的多 agent 主执行面。

这带来几个直接问题：
- Deep Research 的控制流、研究产物、事件语义主要依附在一个大 state 和一个大 runner 中，职责边界不清晰。
- tree 分支的并发更像研究子任务并发，而不是具备明确输入输出契约、预算和生命周期的 worker agent。
- 前端只能稳定感知 `search`、`research_tree_update`、`quality_update` 等粗粒度事件，无法解释 agent 级协作过程。
- 如果继续在现有 runner 内追加更多策略，`deepsearch_optimized.py` 和图级 orchestration 会继续双核膨胀。

该变更是典型的跨模块架构调整，涉及 `agent/core/*`、`agent/workflows/*`、`main.py` 和 `web/*` 的事件消费层，因此需要先明确技术设计，再开始实现。

## Goals / Non-Goals

**Goals:**
- 在不破坏现有 `deep` 入口和 SSE 主协议的前提下，引入一个可切换的 multi-agent Deep Research runtime。
- 用结构化 research artifacts 替代 loose state 拼接，让 planner、researcher、verifier、reporter 之间通过明确契约协作。
- 为 researcher worker 建立可并发、可隔离、可回退的任务执行模型，避免 sibling context 污染。
- 让 coordinator 成为唯一的深度研究循环控制点，统一决定继续研究、补缺、汇总或结束。
- 扩展事件语义，让前端能展示 agent、task、artifact 级过程，同时保持 legacy 兼容。

**Non-Goals:**
- 不把整个 `research_graph` 重写为完全动态的自由自治 agent 社交系统。
- 不移除 legacy `deepsearch` runner；第一阶段必须保留回退开关。
- 不改变 `direct / web / agent` 三种模式的既有外部语义。
- 不在本变更中引入新的外部搜索源、RAG 或全新模型供应商。
- 不在第一阶段追求任意 agent 类型扩展，初始只覆盖 coordinator、planner、researcher、verifier、reporter 这条闭环。

## Decisions

### 1. 保留图级入口稳定，新增内嵌 multi-agent deep runtime

`deepsearch_node` 继续作为 Deep Research 的图级入口，但内部不再只分发到 legacy tree/linear runner，而是增加 `multi_agent` engine 选项。路由层、取消令牌、HITL、SSE 外壳和最终回答出口继续沿用现有外层框架。

这样做的原因：
- 现有 `deep` 模式入口、流式输出和取消能力已经围绕 `deepsearch_node` 成熟，外壳不需要为架构升级而整体重写。
- 真正变化最大的部分是深度研究内核，而不是模式选择和 API 外围。

备选方案：
- 方案 A：把 planner/researcher/reporter 全部提升为顶层 LangGraph 节点。
  - 未选原因：任务数量与并发 worker 数是动态的，静态图会让编排复杂度快速膨胀。
- 方案 B：完全保留现有 runner，只新增一些“agent prompt”。
  - 未选原因：这不会形成真正的运行时隔离和任务契约，仍然是单 runner。

### 2. 采用 artifact-first 协作，而不是共享完整消息历史

multi-agent runtime 以内存中的结构化 artifact store 作为协作媒介，至少包含以下核心对象：
- `ResearchTask`
- `BranchBrief`
- `EvidenceCard`
- `KnowledgeGap`
- `ReportSectionDraft`
- `FinalReportArtifact`

每个 agent 读取共享 brief 和与自己任务相关的 artifacts，写回自己的结构化产物，不直接共享 sibling `messages`。

这样做的原因：
- 减少上下文污染，便于测试和恢复。
- 便于让 verifier、reporter 只消费规范化证据，而不是随意读取整个 runner 历史。

备选方案：
- 继续把所有中间结果塞进 `AgentState`。
  - 未选原因：状态字段会持续失控增长，职责边界也无法收敛。

### 3. 用 coordinator + task queue 驱动 researcher worker 并发

coordinator 负责：
- 启动初始计划
- 决定任务优先级
- 根据 `KnowledgeGap` 触发 replan
- 判断完成、预算停止或失败中止

planner 只负责产出任务，researcher 只负责消费任务并产出证据，verifier 负责检查覆盖度与证据缺口，reporter 负责最终汇总。researcher worker 从任务队列领取任务，遵守并发上限和预算约束。

这样做的原因：
- 将“循环控制”与“执行任务”分离，符合单一职责。
- 现有 tree branch 并发可以迁移为 researcher worker 并发，而不是继续扩展 branch 特判。

备选方案：
- 让每个 researcher 自己决定是否继续派生子任务。
  - 未选原因：任务树会失去全局预算控制，难以保持可预测性。

### 4. 保留 legacy engine 作为独立可选运行时

新增 `deepsearch_engine=legacy|multi_agent` 配置，默认第一阶段采用安全默认值。`legacy` 与 `multi_agent` 作为两个显式可选 runtime 存在，但当用户或部署配置明确选择 `multi_agent` 时，运行时发生不可恢复错误应直接报错，而不是隐式降级到 `legacy`。

失败时必须记录原因，并将错误透传到上层 Deep Research 错误处理链路。

这样做的原因：
- 显式选择 `multi_agent` 时，静默切回 `legacy` 会掩盖真实稳定性问题，也会误导调试。
- 保持 engine 语义明确，便于问题归因和灰度观察。

备选方案：
- 在 `multi_agent` 失败时自动切回 `legacy`。
  - 未选原因：会混淆实际运行 engine，并让排障日志和前端表现出现假象。

### 5. 扩展事件模型，但保持兼容现有流协议

新增 agent/task/artifact/coordinator 决策事件，例如：
- `research_agent_start`
- `research_agent_complete`
- `research_task_update`
- `research_artifact_update`
- `research_decision`

同时保持现有 `search`、`quality_update`、`research_tree_update` 和最终 `message/text` 输出语义不变。前端优先消费新事件增强 timeline；旧客户端即使忽略新事件，也仍能拿到最终结果。

这样做的原因：
- 事件演进不能破坏既有流式协议。
- 新前端展示要基于增量能力，而不是依赖一次性重写。

备选方案：
- 复用现有 `search`/`status` 事件硬塞 agent 信息。
  - 未选原因：事件语义会继续混乱，前端难以稳定演进。

## Risks / Trade-offs

- [运行时复杂度上升] → 通过严格的 agent 职责划分、有限的首批 agent 类型和显式 engine 选择控制范围。
- [状态与 artifact 双写导致不一致] → 以 artifact store 为 deep runtime 的权威中间态，只将必要摘要回填到 `AgentState`。
- [前端事件过多导致 UI 噪音] → 对 agent/task 事件做去重、聚合和阶段性显示，不直接逐条原样暴露。
- [并发 worker 造成预算失控] → 由 coordinator 和 task queue 统一计数搜索/时间/token 预算，并在领取任务前检查。
- [迁移期间存在两套 deep engine] → 通过单一配置入口、统一输出契约和回归测试控制分叉成本。

## Migration Plan

1. 增加 `deepsearch_engine` 开关和 multi-agent runtime 空实现，先接入 `deepsearch_node` 而不改变默认行为。
2. 定义 artifact schema、task queue 和 coordinator loop，把现有 planner/researcher/reporter 类接入新 runtime。
3. 将 tree branch 并发逐步迁移为 researcher worker 并发，保留 legacy tree runner。
4. 增加新的 research events，并在 `main.py` 与前端 stream hook 中透传和消费。
5. 为 mode selection、错误透传、并发调度、artifact merge、事件流和最终报告输出补齐测试。
6. 在验证质量与稳定性后，再决定是否提升 multi-agent engine 为默认值。

## Open Questions

- 第一阶段的默认 `deepsearch_engine` 是否保持 `legacy`，还是仅对显式实验开关用户启用 `multi_agent`？
- verifier 是否应作为独立 agent 存在，还是先以内嵌质量步骤实现，再在第二阶段独立化？
- artifact store 第一阶段只做内存态，还是同时设计与 `SessionManager` 的持久化衔接点？
