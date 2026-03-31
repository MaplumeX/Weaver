## Context

当前 Deep Research 的 `multi_agent` runtime 已经具备显式的 intake/scoping、planning、dispatch、verify、coordinate、report 流程，但正式研究阶段的最小执行单元仍然是“单条 query 对应一个 researcher worker”。这导致几个持续问题：

- planner 的输出契约过低层，只能表达 query，而不能表达一个完整研究分支的目标、验收标准和允许的执行边界。
- researcher 虽然被建模为 graph 节点，但实质仍是“搜索一次 + 摘要一次”的执行器，没有真正继承通用 agent middleware、工具自治和多步工具调用能力。
- verifier 当前主要承担 coverage/gap 检查，缺少对 branch-level 结论的 claim/citation 验证流水线，导致 reporter 更像直接汇总 section draft，而不是汇总已验证分支结论。
- runtime 中已经存在 `branch_id`、`BranchBrief`、`branch_scopes` 等结构，但正式调度仍退化为 root branch 下的 query worker pool，没有把 branch 变成一等执行边界。

本次变更需要在不打碎现有 Deep Research 顶层角色面、不改变外部 API 入口和最终输出契约的前提下，把研究执行层升级为真正的 branch-agent fabric。

## Goals / Non-Goals

**Goals:**
- 将 planner 的正式输出从 query list 升级为 branch objective list。
- 将 researcher 从 query worker 升级为 branch-scoped true agent，并允许其在受控工具集内执行多步研究。
- 将 branch scope 提升为正式调度、验证和汇总的一等边界。
- 为验证回路引入显式的 claim/citation 检查与 coverage/gap 检查两阶段。
- 保持顶层公开角色面稳定，继续使用 `clarify`、`scope`、`planner`、`coordinator`、`researcher`、`verifier`、`reporter` 七类角色。
- 保持现有 checkpoint/resume、SSE 主协议和最终报告输出兼容。

**Non-Goals:**
- 不在本变更中移除 `legacy` deepsearch engine。
- 不把所有顶层角色都升级为自由 tool-calling agent。
- 不在第一阶段把 `scout`、`reader`、`analyst` 暴露为新的顶层公开角色。
- 不引入新的外部搜索提供商或新的长时存储后端。
- 不改变 `direct`、`web`、`agent` 三种模式的公开协议。

## Decisions

### 1. 保留顶层公开角色面不变，只把 researcher 升级为 branch execution subgraph

Deep Research 顶层仍保留七类公开角色：
- `clarify`
- `scope`
- `planner`
- `coordinator`
- `researcher`
- `verifier`
- `reporter`

其中 `researcher` 不再代表“执行单条 query 的 worker”，而是代表“执行一个 branch objective 的 branch agent”。在实现上，`researcher` 可以是一个受 graph 控制的内部执行子图或带阶段状态的 agent loop，但对外仍保持同一个公开 role。

这样做的原因：
- 当前前端、测试和事件模型已经围绕这七类 role 建立了稳定契约，直接扩张顶层 role 面会放大迁移成本。
- 真正需要升级的是研究执行粒度与自治边界，而不是 role 命名本身。

备选方案：
- 直接新增 `scout`、`reader`、`analyst` 为顶层角色。
  - 未选原因：会显著增加事件、UI、测试和规范兼容成本，且第一阶段收益不足。
- 继续保留 researcher 为 query worker，只在内部增加更多 helper。
  - 未选原因：无法解决 planner 契约过低层和验证回路过晚的问题。

### 2. 继续复用 `ResearchTask`，但将其升级为 branch objective 合同

系统继续使用 `ResearchTask` 作为 graph 中的正式任务载体，而不是新增并行的任务类型；但 `ResearchTask` 的权威字段需要从偏 query-oriented 升级为 branch-oriented。

核心新增字段或等价契约包括：
- `task_kind`
- `objective`
- `acceptance_criteria`
- `allowed_tools`
- `input_artifact_ids`
- `output_artifact_types`
- `branch_id`
- `parent_task_id`

现有 `query` 字段降级为 branch agent 内部某个执行阶段的派生输入，而不是 planner 的权威输出。

这样做的原因：
- 保留 `ResearchTask` 名称和主键体系可以降低 store、queue、event、resume 兼容成本。
- 真正要升级的是任务语义，而不是任务容器名称。

备选方案：
- 新增 `BranchTask` 并逐步淘汰 `ResearchTask`。
  - 未选原因：迁移面更大，而且需要同时维护两套任务快照兼容逻辑。

### 3. planner 输出 branch objectives，coordinator 只调度 branch，而不是 query

planner 在初始规划和 replan 阶段都只产出 branch objective，而不是直接生成要执行的搜索 query。一个 branch objective 至少要表达：
- 这条分支要回答什么问题
- 成功标准是什么
- 允许使用哪些工具类别
- 依赖哪些已存在 artifacts
- 完成后必须向 graph 返回什么结果

coordinator 只批准、暂停、重试或放弃 branch 级任务。query 的派生与执行属于 researcher 内部责任。

这样做的原因：
- 将“研究目标”和“执行细节”分层，可以避免 planner 直接把低层执行策略写死。
- coordinator 面对 branch 而不是 query，才能真正基于覆盖度和验证结果做调度判断。

备选方案：
- 让 planner 继续直接生成 query，并由 researcher 内部自行聚合成 branch。
  - 未选原因：branch 会退化为运行后才被推断出来的概念，不利于调度、验证和观察。

### 4. branch agent 继承共享 middleware，但工具集必须受限

researcher branch agent 应接入共享 agent middleware 栈，以继承 tool selector、retry、limit、HITL 等能力；但不能直接开放完整 tool registry。实现上需要新增一个面向 Deep Research 的 builder，例如 `build_deep_research_tool_agent()`，基于现有 middleware 复用机制，只注入受控工具集：
- 搜索类工具
- 页面抓取/读取类工具
- 证据抽取辅助工具
- 必要的轻量浏览器阅读工具

这样做的原因：
- “真正的 agent”价值主要在多步工具自治，而不是多一个 LLM 包装层。
- 直接复用完整工具集会使预算、风险审批和结果契约失控。

备选方案：
- researcher 继续完全自定义实现，不接 middleware。
  - 未选原因：会继续与普通 agent 模式分叉，难以复用已有可靠机制。
- researcher 直接使用完整 registry。
  - 未选原因：超出本次变更需要，且会放大不必要的工具风险面。

### 5. verifier 升级为两阶段验证流水线，但公开 role 仍是 verifier

`verifier` 仍保持单一公开角色，但内部执行至少拆成两阶段：
- `claim_check`：检查 branch synthesis 中的关键结论是否被 `EvidencePassage` / `FetchedDocument` / 来源证据支持，必要时识别 citation 或 claim 问题。
- `coverage_check`：检查整体覆盖度、剩余 gap、是否还需要 replan。

reporter 只消费通过验证的 branch synthesis，而不是直接消费所有 section draft。

这样做的原因：
- 当前 coverage-only verifier 不能支撑“研究执行层自治增强”后的质量门控。
- 保持 verifier 为单一 role 可以避免事件和前端出现新的顶层复杂度。

备选方案：
- 新增 `claim-checker` 顶层 role。
  - 未选原因：收益有限，且不必要地扩大角色面。
- 把 claim 校验交给 reporter 末端处理。
  - 未选原因：校验太晚，无法驱动 replan。

### 6. artifact handoff 从“evidence + section”升级为 branch execution bundle

除了现有的 `ResearchTask`、`EvidenceCard`、`KnowledgeGap`、`ReportSectionDraft`、`FinalReportArtifact`，还需要引入或等价建模下列 artifact：
- `SourceCandidate`
- `FetchedDocument`
- `EvidencePassage`
- `BranchSynthesis`
- `ClaimCheckResult`

merge 仍然是唯一允许写入共享权威状态的阶段。researcher / verifier 只返回结构化 bundle，不直接改写全局 store。

这样做的原因：
- true agent 的多步执行天然会产生中间产物；如果不结构化保存，resume、debug 和 verifier 都会失真。
- reporter 需要消费“已验证分支结论”，而不是混杂的原始抓取结果。

备选方案：
- 继续只保存 `EvidenceCard` 和 `ReportSectionDraft`。
  - 未选原因：信息损失过大，难以支撑 claim 级验证和 branch 级回流。

### 7. 事件模型保持角色稳定，但补充 branch/stage/task-kind 维度

现有 `research_agent_*`、`research_task_update`、`research_artifact_update`、`research_decision` 事件继续保留，但需要新增或收紧这些字段：
- `task_kind`
- `stage`
- `branch_id`
- `objective_summary`
- `input_artifact_ids`
- `validation_stage`
- `parent_task_id`

其中：
- `role` 继续表示顶层角色
- `phase` 继续表示当前大阶段
- `stage` 表示 researcher/verifier 内部的细分执行阶段

这样做的原因：
- 保持旧客户端兼容，同时让新客户端能看懂 branch agent 的真实推进过程。
- 可以在不新增顶层 role 的前提下提供足够的可观察性。

备选方案：
- 直接增加新的事件类型表达所有内部阶段。
  - 未选原因：第一阶段对前端兼容性压力过大。

## Risks / Trade-offs

- [任务契约变复杂] → 通过复用 `ResearchTask` 名称、只增加 branch 语义所需字段来控制复杂度。
- [researcher 接入通用 agent middleware 后行为更难预测] → 使用受限工具集、显式 allowed tools、统一 budget gate 和 graph merge 收口。
- [artifact 类型增加，store 和 snapshot 体积变大] → 只持久化权威中间产物，不保存完整工具对话历史。
- [事件字段增加会带来前端适配成本] → 保留现有事件名和旧字段含义，新增字段只做增强，不改变旧消费路径。
- [验证流水线变长，可能增加总体时延] → claim_check 先围绕 branch synthesis 的关键结论执行，避免对所有原始证据做全量深验。

## Migration Plan

1. 升级 proposal/spec 契约，先把 branch objective、branch execution、validation pipeline 和事件字段确定下来。
2. 扩展 `ResearchTask`、artifact schema 和 snapshot/store，使 branch agent 所需字段与中间产物能够被权威持久化。
3. 调整 planner 和 dispatcher，使其正式产出并分发 branch objective，而不是 query list。
4. 为 Deep Research 新增受限的 tool-agent builder，并将 researcher 路径替换为 branch agent 执行循环。
5. 在 verifier 中引入 claim/citation 检查阶段，并让 coordinator 基于验证结果做 replan 或 report 决策。
6. 更新事件发射与前端消费逻辑，补齐 checkpoint/resume、branch dispatch、validation 回流测试。

## Open Questions

- 第一阶段的 branch agent 是否需要内部子图，还是先用单节点 agent loop + staged state 就足够？
- `FetchedDocument` 与 `EvidencePassage` 是否都需要成为一等 artifact，还是允许其中一种作为另一种的 metadata 附属存在？
- claim/citation 检查在第一阶段采用完全确定性规则、LLM 辅助校验，还是两者混合？
