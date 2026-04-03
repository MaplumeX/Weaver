## Context

当前 Deep Research verifier 的问题不是单个 matcher 精度不够，而是整条验证链路的对象建模错误：

- verifier 会从 `branch_synthesis.summary/findings` 反向抽取 claim，而不是消费 researcher 直接提交的权威验证对象。
- claim grounding 和 coverage evaluation 仍依赖 token overlap、summary challenge 和 snippet 级证据，导致中文语义改写、数值改写和组合性结论经常被误判。
- verifier tool-agent 使用 summary-oriented tools，提交结果再以 branch 级粗粒度方式扇出到整批 claim / obligation。
- advisory `knowledge_gap`、revision issue、missing evidence list 和 outline blocker 会在多个阶段重复累计，最终把非权威噪音放大成阻塞性缺口。

该改动横跨 schema、verification service、tool-agent fabric、graph orchestration、outline gate 和 reporter handoff，属于典型的跨模块架构变更。设计必须同时满足以下约束：

- 保持 Deep Research checkpoint / resume 语义稳定。
- 不让 advisory reflection 再次污染 authoritative validation。
- 允许分阶段迁移，避免一次性切断旧 verifier 造成大面积回归。
- 尽量复用现有 artifact store 和 bounded tool-agent 模式，而不是重新引入一套平行 runtime。

## Goals / Non-Goals

**Goals:**

- 让 researcher 直接提交可验证的结构化 `AnswerUnit`，verifier 不再从 `summary` 反推验证目标。
- 让 verifier 只消费稳定、可追溯的 `EvidencePassage`，拒绝把搜索 snippet 直接当作权威证据。
- 将验证结果收敛到 unit / obligation 级，避免 branch 级 verdict 广播和 blocker 重复累计。
- 将 `reflection`、`validation`、`evaluation` 三层能力拆开，明确哪些信号会阻塞 runtime，哪些只是研究补强建议。
- 让 supervisor、outline gate 和 reporter 只消费 canonical branch validation summary。
- 通过双写与 shadow compare 完成迁移，确保旧流程可以有界回退。

**Non-Goals:**

- 不在本次设计中重写整个 researcher 搜索或阅读策略。
- 不把 verifier 变成通用自然语言事实裁判器；它只校验 runtime 内声明的结构化 answer units。
- 不在本次设计中引入新的外部评测服务或强制新增第三方依赖。
- 不改变最终报告的产品形态；重点是提高事实支撑与收敛可靠性。

## Decisions

### Decision 1: 引入 answer-unit 驱动的验证契约

运行时新增或等价引入以下 canonical contracts：

- `SearchLead`: 搜索召回线索，允许携带 snippet，但不能进入权威验证。
- `EvidencePassage`: 可验证证据，必须带稳定 `passage_id`、`document_id`、`url`、`source_title`、`text/quote` 和 locator metadata。
- `AnswerUnit`: researcher 直接提交的待验证答案单元，至少包含 `id`、`task_id`、`branch_id`、`unit_type`、`text`、`provenance`、`obligation_ids`、`supporting_passage_ids`。
- `UnitValidationResult`: 单个 `AnswerUnit` 的验证结果，状态为 `supported`、`partially_supported`、`unsupported` 或 `contradicted`。
- `ObligationCoverageResult`: obligation 级覆盖结果，只根据映射到该 obligation 的 supported units 计算。
- `BranchValidationSummary`: branch 级唯一权威汇总，供 supervisor / outline / reporter 消费。

原因：

- verifier 需要明确的“被验证对象”，而不是事后从 summary 猜。
- 证据、答案单元和阻塞状态必须共享同一组稳定 ID，才能实现 checkpoint-safe merge 和 deterministic fan-in。

备选方案：

- 直接扩展现有 `ClaimUnit`：短期成本更低，但会继续把原子 claim、组合结论和 reporter summary 混在一起，迁移期语义容易失控。

结论：

- 使用 `AnswerUnit` 作为统一抽象；实现期可以保留 `ClaimUnit` 兼容视图或别名，但权威契约以 `AnswerUnit` 为准。

### Decision 2: 将证据可采纳性作为独立阶段

验证流水线先做 `evidence admissibility check`，只允许稳定 `EvidencePassage` 进入权威判断。搜索结果 `summary`、`snippet`、`raw_excerpt` 只能创建 `SearchLead` 或帮助召回源文档，不能直接支撑事实 verdict。

原因：

- 当前大量误报来自 snippet 文本不完整、二手摘要和截断句子。
- 先过滤证据形态，比在 matcher 里无限补 heuristic 更有效。

备选方案：

- 允许 snippet 以“低置信度 evidence”进入 verifier：实现更简单，但会保留当前 blocker 噪音来源。

结论：

- verifier 只接受 passage 级权威证据；snippet 只保留在线索层。

### Decision 3: 按类型执行 unit-level validation，而不是继续使用统一 token overlap

`AnswerUnit` 按 `unit_type` 分流：

- `numeric`、`date`、`entity` 走确定性归一化和字段比对。
- `comparison`、`trend`、`causal_summary` 走受约束的语义判断。
- `composite_conclusion` 不直接对 passage 判真伪，而是依赖其子单元是否已 supported。

原因：

- 单一 token overlap 既不能处理中文语义改写，也无法区分数字/时间/趋势等高价值约束。
- 组合结论必须建立在已验证的原子单元之上，不能再被当作普通句子去做词面匹配。

备选方案：

- 纯 LLM judge：灵活但不可控，且难以解释 blocker 来源。
- 继续增强 token overlap：无法从根上解决结构化约束缺失。

结论：

- 使用 typed validation pipeline，确定性优先，必要时再做受限语义判断。

### Decision 4: coverage 由 obligation-to-unit mapping 判定

coverage 不再通过 `summary` 或 claim 文本与 criteria 的 token overlap 判定，而是由 researcher 明确提交 `obligation_ids`，再由 verifier 检查该 obligation 所需的 answer units 是否 supported。

原因：

- coverage 本质是“这个任务要求是否被回答”，不是“文本里有没有相似词”。
- obligation 映射明确后，supervisor 和 reporter 都能解释为什么某项已满足或未满足。

备选方案：

- 保留 obligation mapping，并在缺失时 fallback 到 token match：会延续旧噪音，且让迁移后的 contract 失去刚性。

结论：

- 不提供 token overlap fallback；映射缺失即视为 contract 不完整。

### Decision 5: verifier tool-agent 改成 unit-addressable fabric tools

verifier tool-agent 不再调用 `fabric_challenge_summary` / `fabric_compare_coverage`。新的工具表面应等价提供：

- `fabric_list_answer_units`
- `fabric_get_obligations`
- `fabric_get_evidence_passages`
- `fabric_validate_unit`
- `fabric_validate_obligation`
- `fabric_submit_validation_results`

每个 verdict 必须绑定 `answer_unit_ids`、`obligation_ids` 或 `issue_ids`，并显式声明 `evidence_passage_ids`。

原因：

- tool-agent 只有拿到稳定对象才能处理边界 case，而不是重新解释 summary。
- merge 层必须精确知道它改写了哪些 validation objects。

备选方案：

- 保留 summary tools 作为 verifier 的便捷辅助：会让旧路径持续存在，最终重新污染权威链路。

结论：

- summary-oriented verifier tools 完整下线，不再作为 authoritative path。

### Decision 6: 只保留一个权威 branch gate

新增 `BranchValidationSummary` 作为 branch 唯一权威 gate，汇总：

- required unsupported / contradicted units
- uncovered obligations
- scoped consistency conflicts
- advisory reflection notes

outline gate、missing evidence list 和 reporter handoff 只从该汇总派生，不再各自重新累计 blocker。

原因：

- 当前 blocker 在多个 artifact 里重复出现，导致相同问题被多次升级。
- 最终 gating 应以“权威未决债务”而不是“多个列表都提到同一问题”为准。

备选方案：

- 保持现有 coverage matrix / missing evidence list / outline gap 各自判阻塞：解释性差，且继续存在重复累计问题。

结论：

- branch gate 单一权威化，其他 artifact 只做派生视图。

### Decision 7: 采用双写与 shadow compare 迁移

迁移分四步：

1. schema 扩展：双写 `AnswerUnit`、`EvidencePassage` metadata 和 `BranchValidationSummary`。
2. shadow mode：新 verifier 并行运行，对比旧结果，不接管 blocking。
3. consumer cutover：supervisor、outline gate、reporter 改读新汇总。
4. legacy removal：删除 summary-derived claim、summary-oriented tools、token-overlap coverage 和重复 blocker 聚合。

原因：

- verifier 位于 runtime 中枢，直接替换风险过高。
- shadow compare 能快速暴露旧测试没有覆盖的边界 case。

备选方案：

- 一次性切换：实施更快，但回归定位和回滚成本都更高。

结论：

- 采用 feature flag + dual write + shadow compare 方式迁移。

## Risks / Trade-offs

- [Artifact 数量增加] → 通过 `BranchValidationSummary` 做聚合读取，避免消费者直接遍历全部 unit-level artifacts。
- [迁移期新旧契约并存] → 使用明确 feature flag、兼容字段和 shadow compare 指标，限制双写窗口。
- [语义判断仍可能出现边界误差] → 按 `unit_type` 分层校验，并补充中文改写、数值、时间、趋势冲突测试集。
- [Researcher 负担上升] → 通过 fabric tools / helper builder 自动生成基础 `AnswerUnit` 结构，只要求 researcher 明确 obligation 映射与证据引用。
- [Outline gate 改为单一权威输入后，诊断信息可能变少] → 保留派生视图 artifact，但这些 artifact 不再拥有独立阻塞权。

## Migration Plan

1. 扩展 schema 和 artifact store，支持 `AnswerUnit`、增强版 `EvidencePassage` 和 `BranchValidationSummary`。
2. 在 researcher 提交路径引入新 contract builder，同时保留旧 `ClaimUnit` 兼容写入。
3. 新 verifier 以 shadow mode 运行，记录 unit-level 结果、coverage 结果和 branch summary，对比旧 blocker。
4. 切换 supervisor、outline gate、reporter 和 public artifacts 读取路径，仅消费新汇总。
5. 删除旧 verifier summary challenge、token-overlap coverage、批量 verdict 扇出和 blocker 重复聚合逻辑。

回滚策略：

- 保留 feature flag，使系统可以短时间回退到旧 verifier 读取路径。
- 在 cutover 之前不删除旧 artifact 读取逻辑，直到 shadow compare 稳定。

## Open Questions

- `AnswerUnit` 是否直接替代 `ClaimUnit` 命名，还是先保留 `ClaimUnit` 作为兼容 alias。
- `EvidencePassage` 的最小 locator 集是否只需要 `heading_path` / `quote`，还是要补充字符偏移或段落序号。
- `evaluation` 层是否在本次变更中只定义契约，不立即接入 runtime 外的 benchmark runner。
