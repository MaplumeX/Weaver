## Context

当前 Deep Research 的 `multi_agent` runtime 已经完成了 `research brief`、双 ledger、outline gate 和 bounded tool-agent 的协议化改造，但 `verify` 阶段仍然主要基于 `branch_synthesis.summary`、关键词覆盖和粗粒度 follow-up request 做判断。这样会带来三个持续问题：

- 验证对象不稳定：系统实际上在检查自由文本摘要，而不是 branch 明确承诺的 claims 与 coverage obligation。
- 验证结果不可执行：`retry_branch`、`need_counterevidence` 等 request 只能表达“有问题”，不能表达“哪条 claim 有问题、缺哪类证据、修复后如何判定完成”。
- 验证闭环不完整：当前 loop 更像“失败后重跑”或“全局 replan”，缺少面向同一 branch 的定向修订能力。

本次设计需要在不引入第二套 runtime、不改变外部 `deep` 入口和最终报告公开接口的前提下，把验证协议升级为 contract-first pipeline，并补齐 branch revision loop。

## Goals / Non-Goals

**Goals:**

- 将 `verify` 升级为基于结构化 claims、coverage obligations 和 consistency inputs 的验证流水线。
- 让 `research brief` 与 branch task 派生出权威 coverage obligation，而不是继续让 verifier 依赖通用 topic checklist 或关键词命中。
- 让 verifier 输出结构化 revision issue，并允许 `supervisor` 决定 patch 现有 branch 或派生 counterevidence / follow-up branch。
- 扩展 artifact store、ledgers、tool-agent handoff 和事件模型，使验证与修订闭环对恢复、调试和前端可观察。
- 保持顶层公开角色面不变，继续使用 `clarify`、`scope`、`supervisor`、`researcher`、`verifier`、`reporter`。

**Non-Goals:**

- 不新增第二套 Deep Research runtime，也不恢复 legacy deepsearch 路径。
- 不引入新的人工审批入口、额外 HITL 决策类型或开放式 swarm。
- 不在本次设计中引入多 writer 报告系统或新的最终报告格式。
- 不扩展新的搜索 provider、RAG provider 或外部数据源。
- 不要求一次性移除所有启发式判断；启发式可以保留为 fallback，但不再作为权威验证合同。

## Decisions

### 1. 验证对象从自由文本摘要升级为结构化 verification contracts

`researcher` 不再只提交 `branch_synthesis.summary` 与 findings，而是需要同时提交结构化 claim 单元。与此同时，系统需要把 `research brief` 与 `ResearchTask.acceptance_criteria` 归一化为正式 coverage obligations。`verifier` 的权威输入因此变成：

- `ClaimUnit`
- `CoverageObligation`
- `EvidencePassage` / `FetchedDocument`
- `BranchSynthesis`
- cross-branch verified outputs

这样做的原因：

- claim 与 obligation 一旦有稳定 id，后续验证、重试、修订、事件和 UI 才能围绕同一对象协作。
- 这可以消除“重新从 summary 中猜测检查对象”的不稳定性。

备选方案：

- 继续以 `branch_synthesis.summary` 为唯一验证输入。
  - 未选原因：摘要是结果表述，不是验证合同；它会把 claim 抽取、coverage 解释和结论判断全部混在一起。

### 2. 验证流水线固定为 grounding -> coverage -> consistency -> issue aggregation

`verify` 不再只是 claim check + gap analysis 的松散组合，而是升级为 4 个有明确输入输出的阶段：

1. `claim grounding`
2. `coverage obligation evaluation`
3. `cross-branch consistency evaluation`
4. `revision issue aggregation`

其中 deterministic checker 负责可机械判断的 case，bounded tool-agent verifier 只处理补证据、查反例和边界裁决，而不是继续充当唯一 coverage 判官。

这样做的原因：

- 把“被支持 / 未覆盖 / 相互冲突 / 需要修订”分开后，`supervisor` 才能对症决策。
- tool-agent 只处理高不确定度 case，可以降低行为漂移。

备选方案：

- 继续使用一个统一 verifier prompt 或一个大 `_verify_node` 函数处理所有判断。
  - 未选原因：这会继续把验证语义、调度副作用和 artifact 生成耦合在一起。

### 3. Coverage obligations 由 brief 和 branch contract 派生，而不是由 verifier 临场推断

`supervisor_plan` 在创建 branch task 时，同时生成或刷新该 branch 的 obligation 集合。obligation 的来源只能是：

- `research brief.coverage_dimensions`
- `research brief.core_questions`
- `ResearchTask.acceptance_criteria`
- 经 `supervisor` 批准的 revision brief delta

`KnowledgeGapAnalyzer` 可以继续作为辅助分析器生成候选 gap，但不能再定义权威 coverage contract。

这样做的原因：

- 覆盖判断必须和 scope/brief 对齐，否则 verifier 会不断引入新的隐式标准。
- `supervisor` 生成任务时就知道 branch 需要回答什么，最适合同时生成 obligation。

备选方案：

- 继续让 verifier 基于 topic 和 collected knowledge 动态生成 gap 维度。
  - 未选原因：会让覆盖标准随 prompt 漂移，导致同一 branch 在不同轮次难以复现。

### 4. 修订闭环通过 branch revision brief 驱动，而不是复用粗粒度 retry 语义

当 verifier 发现问题时，系统不会只发 `retry_branch`。它会先生成结构化 `RevisionIssue`，再由 `supervisor` 决定：

- patch 现有 branch
- 派生 counterevidence branch
- 派生 follow-up branch
- stop / finalize with bounded failure

一旦进入修订，系统必须创建 `BranchRevisionBrief`，至少包含：

- target branch / target task
- issue ids
- 需要补充或反驳的 claims / obligations
- 可复用的已有证据
- 建议动作与完成标准

这样做的原因：

- “重跑一次”并不等于“修复问题”；修订需要明确目标和验收条件。
- branch revision brief 可以在 checkpoint/resume、事件流和 UI 中保持稳定语义。

备选方案：

- 继续使用现有 `retry_branch` request，直接把任务重新放回队列。
  - 未选原因：这只能表达“再试一次”，不能表达“修哪一条问题”。

### 5. 保持角色面不变，但把验证和修订服务模块化

顶层 graph 节点仍保持 `verify` 与 `supervisor_decide`，不引入新的公开角色；但实现上需要把以下逻辑从 `graph.py` 中抽出：

- claim grounding service
- coverage obligation service
- consistency service
- revision issue reducer
- revision planning helpers

`graph.py` 只保留 orchestration、merge、checkpoint/resume 和事件发射边界。

这样做的原因：

- 当前 graph 过大，继续叠加 revision loop 会让控制流和验证语义一起失控。
- 抽服务后才能为每个 verifier 子阶段建立独立单测与 benchmark。

备选方案：

- 新建第二套 verification runtime。
  - 未选原因：会破坏已有单一 canonical runtime 的方向。

## Risks / Trade-offs

- [Artifacts 数量明显增加] → 通过把 public artifacts 做成 canonical store 的派生视图，避免公开接口随内部对象数量线性膨胀。
- [Revision loop 拉长完成时间] → 优先 patch 现有 branch，限制每个 issue 的修订次数，并继续沿用 graph 级预算守卫。
- [Deterministic checker 与 tool-agent 裁决可能不一致] → 保留 unresolved / adjudication-needed 状态，不强迫所有冲突被压扁成二元结论。
- [Migration 期间新旧 verifier 结果可能并存] → 在 schema/store 中保持兼容字段，先让新 artifacts 成为权威输入，再逐步降级旧 summary-based path。
- [Supervisor 决策面变复杂] → 用 branch revision brief 和 issue taxonomy 收紧输入，避免把自由文本重新带回控制面。

## Migration Plan

1. 扩展 `schema`、`store`、public artifacts 和 checkpoint snapshot，新增 verification contracts 与 revision artifacts。
2. 抽出 claim grounding、coverage obligation、consistency 和 issue aggregation 服务，并让 `_verify_node` 调用这些服务。
3. 扩展 `researcher` 结果 bundle，使其包含 claim units、resolution metadata 和 revision-aware output。
4. 扩展 `supervisor` 决策逻辑、ledger 和 task creation helpers，使其支持 patch existing branch 与 spawn follow-up branch。
5. 更新 tool-agent fabric、SSE 事件、前端公共视图与恢复逻辑，使新验证对象和 lineage 对外可观察。
6. 补齐单测、集成测试和 benchmark 指标；在内部保留 summary-based fallback 作为短期回滚路径，待新 verifier 稳定后再移除。

## Open Questions

- `ClaimUnit` 的粒度应以“单句可验证陈述”为主，还是需要进一步拆到“实体-指标-时间范围”级别？本次设计倾向先以单句 claim 为主，并允许 metadata 承载实体与时间信息。
- patch existing branch 时应复用原 `branch_id` 并生成新 `task_id`，还是为修订创建新的 `branch_id`？本次设计倾向“保留同一 `branch_id`，新增 revision task 并记录 lineage”。
- bounded tool-agent verifier 在 adjudication 阶段是否允许覆盖 deterministic finding，还是只能补证据后重新提交？本次设计倾向“允许覆盖，但必须引用 issue ids 与新 evidence refs，并保留原 finding 状态供审计”。
