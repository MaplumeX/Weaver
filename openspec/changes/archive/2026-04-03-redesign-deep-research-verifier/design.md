## Context

当前 Deep Research runtime 已经具备 contract-first 的 artifact 骨架，包括 `ClaimUnit`、`CoverageObligation`、`RevisionIssue`、`coverage matrix`、`missing evidence list` 和 `outline gate`。但实现层面仍保留了旧式 topic-driven `KnowledgeGapAnalyzer`，并把它的输出与结构化 verification 结果在同一条 gate 链路中混用。

具体表现为：

- coverage 阶段会无条件执行 `KnowledgeGapAnalyzer`，把 topic 级 gaps 与结构化 obligation 结果合并。
- fallback gap 会进入 `knowledge_gap`、`missing_evidence_list`、`verification_summary` 和 `outline blocking_gaps`。
- `outline_gate` 与 `report` 因而会把启发式 gap 视作真实的阻塞性验证债务。
- verifier tool-agent 当前还允许单个 `passed` 结果覆盖整条 branch 的全部 obligations，缺少 obligation-addressable 裁决。

这使 runtime 同时存在“启发式过严”和“tool-agent 过松”两类错误，最终破坏报告收敛性和可解释性。

## Goals / Non-Goals

**Goals:**

- 将 Deep Research verifier 收敛为单一的 contract-first 权威 gate。
- 将启发式 gap 分析降级为 advisory planning signal，不再直接参与 final report gating。
- 让 coverage 判定与 issue 生成围绕 `ClaimUnit`、`CoverageObligation`、`EvidencePassage` 和 `RevisionIssue` 工作。
- 收紧 verifier tool-agent 契约，保证每次通过/失败裁决都能映射到具体 claim、obligation 或 issue。
- 保持现有 Deep Research 公开入口与大体 artifact 结构不变，避免引入第二套 runtime。

**Non-Goals:**

- 不重写整个 Deep Research graph。
- 不替换现有 `ClaimVerifier` 的全部判定策略；本次只收紧它与 coverage / issue gate 的集成方式。
- 不移除所有启发式 planning 能力；只调整它们的权威级别与输出边界。
- 不改变最终报告格式或对外 API 结构。

## Decisions

### 1. 将权威验证与启发式 gap planning 拆为两条独立语义链路

runtime 将保留结构化 verifier 作为唯一权威 gate，顺序保持为：

1. claim grounding
2. coverage obligation evaluation
3. cross-branch consistency evaluation
4. revision issue aggregation

启发式 gap 分析继续存在，但只作为 advisory planner 使用，用于生成：

- `replan_hints`
- `suggested_queries`
- 非阻塞的 quality / planning 信号

它不得：

- 降低 authoritative coverage score
- 覆盖已满足的 obligation 结果
- 独立生成 blocking final-report debt
- 在没有映射到 claim/obligation/issue 的前提下重开 revision loop

这样做的原因：

- verifier 的职责是裁决既有 contract 是否满足，不是重新定义研究 scope。
- gap planner 的职责是帮助继续搜索，不是 veto 已完成的结构化验证。

备选方案：

- 保持 `GapAnalysisResult` 作为合并后的统一 gate 对象。
  - 未选原因：会继续把 planning signal 和 contractual verdict 混为一谈。

### 2. coverage 判定从“文本主题重合”升级为“obligation-to-evidence 映射”

`CoverageEvaluationResult` 的权威来源应是：

- 已 grounded 的 claims
- 这些 claims 关联的 evidence passages / citations
- obligation 的 completion criteria

summary / findings 文本可以作为辅助信号，但不能再单独决定 obligation 已满足或未满足。coverage evaluator 需要显式产出：

- 哪些 criteria 已被满足
- 哪些 criteria 仍缺失
- 支撑这些判断的 claim_ids / passage_ids / citation_urls

这样做的原因：

- coverage 的对象是 contract，不是摘要文案。
- 只有 obligation-to-evidence 映射稳定后，supervisor 才能做精确 patch/follow-up。

备选方案：

- 继续使用基于 summary 的关键词覆盖判定。
  - 未选原因：极易被 topic overlap 或提示词漂移污染，且不可解释。

### 3. 只有 authoritative blocking debt 才能阻断 outline 和 report

`outline_gate` 与 `report` 的阻断条件收敛为：

- open / accepted 的 blocking revision issues
- unsatisfied / unresolved obligations
- unresolved contradictions
- reporter 自身识别出的结构性 outline gap

下列对象不再直接阻断最终报告：

- heuristic `knowledge_gap`
- advisory `suggested_queries`
- 未映射到具体 issue 的 topic-level “coverage still incomplete”

如果 advisory gap 与真实 contract debt 重合，必须先映射为正式 issue 或 missing evidence row，才能进入 gate。

这样做的原因：

- 最终报告 gate 必须可审计、可复现。
- 否则 runtime 会长期卡在“还可以继续搜”而不是“当前是否已满足合同”。

备选方案：

- 保留 `knowledge_gap -> missing_evidence -> outline_blocked` 的隐式链路。
  - 未选原因：这正是当前无法收敛的主要根因。

### 4. verifier tool-agent 只能提交 contract-addressable 裁决

bounded verifier tool-agent 仍可辅助 claim/coverage/consistency 裁决，但其提交必须引用具体对象：

- `claim_ids`
- `obligation_ids`
- `consistency_result_ids`
- `issue_ids`

若 tool-agent 判定 coverage 通过，它必须说明：

- 覆盖了哪些 obligations
- 使用了哪些 evidence_passage_ids / citation_urls
- 是否关闭了哪些 existing issues

系统不得再接受“branch passed”这类 blanket pass 并据此把全部 obligations 强行改写成 `satisfied`。

这样做的原因：

- tool-agent 裁决只有绑定具体 contract，才能与 deterministic verifier 一致合并。
- 这也能减少“一个宽松 `passed` 覆盖整条 branch”的误报。

备选方案：

- 保留 branch-wide `passed`，由 runtime 自动填满 obligation rows。
  - 未选原因：这会把 tool-agent 的自由文本捷径重新带回权威 gate。

### 5. 将 verification issue 分为真正阻塞与 advisory follow-up 两类

`RevisionIssue` 继续是 supervisor 的主输入，但 blocking 语义需要更严格：

- `contradicted` claim 和 `unsatisfied` / `unresolved` obligation 默认 blocking
- `partially_satisfied` obligation 默认 non-blocking，除非明确升级为 blocking
- heuristic planning gaps 不直接生成 `RevisionIssue`

supervisor 收到 non-blocking issue 时可以：

- 接受风险并继续
- 记录待办
- 派生补充 branch

但系统不应强制将所有 weak signals 都重开完整 revision loop。

这样做的原因：

- 当前系统把“还可补充”错误地等价成“不能出报告”。
- bounded revision loop 的关键是 issue 粒度，而不是 gap 数量。

备选方案：

- 继续将 `partially_satisfied` 与 topic gap 一并视为 follow-up 必要条件。
  - 未选原因：会持续制造假阻塞。

## Risks / Trade-offs

- [advisory gap 不再阻断报告，可能放过“可继续补强”的内容] → 通过保留 non-blocking issue、quality summary 和 suggested queries，让 UI 与 supervisor 仍可见这些弱信号。
- [coverage evaluator 收紧后，部分现有测试与假 verifier 需要重写] → 同步更新 service tests、runtime tests 和 tool-agent contract tests，先固定新语义再重构实现。
- [引入 authoritative / advisory 双轨概念后，artifact 解释成本上升] → 在 public artifacts 和 ledger 中明确区分 `blocking verification debt` 与 `advisory research gaps`。
- [tool-agent 契约收紧可能降低短期通过率] → 允许 runtime 在缺少精确 obligation mapping 时回落到 deterministic verifier，而不是直接 blanket fail。

## Migration Plan

1. 新增或调整 OpenSpec delta specs，明确 authoritative gate 与 advisory gap 的语义边界。
2. 在 runtime 中拆分 `KnowledgeGapAnalyzer` 的 planner 角色和 verifier gate 角色，先修改 `build_gap_result` 与 `outline/report` gate。
3. 重构 coverage evaluator，使其输出 obligation-to-evidence 映射，并收紧 `RevisionIssue` 的 blocking 规则。
4. 更新 verifier tool-agent fabric 契约与 merge 逻辑，移除 blanket pass 行为。
5. 更新 public artifacts、quality summary、SSE 事件和 missing evidence 生成逻辑。
6. 重写并补齐 tests，尤其是：
   - fallback gap 不得覆盖已满足 obligation
   - advisory gaps 不得单独阻断 report
   - partially satisfied obligations 默认 non-blocking
   - verifier tool-agent 必须 obligation-addressable

## Open Questions

- 是否直接把 `KnowledgeGapAnalyzer` 重命名为 `ResearchGapPlanner`，还是保留旧类名并只调整语义边界？当前倾向保留兼容入口，内部迁移到 planner 语义。
- `partially_satisfied` 是否需要在 schema 中补充更明确的风险等级字段，还是继续复用 `RevisionIssue.blocking + severity` 即可？当前倾向复用现有字段，避免扩大 schema 面。
- public artifacts 中是否需要显式新增 `advisory_gaps` 视图，还是继续沿用现有 `knowledge_gaps` 字段并降低其权威级别？当前倾向保留字段名、调整文档和 gate 语义，减小兼容面。
