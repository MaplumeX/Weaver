# Deep Research Verification Revision Loop

## 背景

Deep Research 的多分支运行时已经具备 `research brief -> supervisor -> dispatch -> verify -> outline -> report` 的基本骨架，但旧的 `verify` 主要依赖 branch summary 与宽松的 coverage 启发式判断，无法稳定回答下面三个问题：

1. 哪个 claim 被哪段 evidence 支撑或反驳。
2. 哪个 coverage obligation 已满足、部分满足或仍未满足。
3. 哪些验证问题应该触发 branch patch、follow-up branch、counterevidence branch 或 bounded stop。

本轮改造把验证协议收紧为 contract-first 流程，并把修订动作纳入 supervisor 的主控制回路。

## 运行时流程

当前 Deep Research 的验证与修订闭环按下面的顺序运行：

1. `supervisor_plan` 为每个 branch task 派生结构化 `CoverageObligation`。
2. `researcher` 在提交 `BranchSynthesis` 时同时派生 `ClaimUnit`，并把 issue resolution 信息写回 branch artifacts。
3. `verify` 先执行 claim grounding，再执行 obligation evaluation，再执行 cross-branch consistency evaluation。
4. `verify` 把 claim grounding、coverage evaluation、consistency results 聚合成 `RevisionIssue`。
5. `supervisor_decide` 根据 issue 严重度和推荐动作，选择：
   - patch existing branch
   - spawn follow-up branch
   - spawn counterevidence branch
   - retry branch
   - bounded stop / report
6. `outline_gate` 只消费通过验证且没有 blocking issue 的 branch；若仍有 structure gap，会把控制权退回 supervisor。

## 核心 Artifact

本轮新增或强化的 Deep Research artifacts：

- `ClaimUnit`: branch synthesis 中可验证的原子 claim。
- `CoverageObligation`: 从 task acceptance criteria、research brief 或 revision brief 派生的覆盖义务。
- `ClaimGroundingResult`: 单个 claim 的 grounded / unsupported / contradicted 裁决。
- `CoverageEvaluationResult`: obligation 的 satisfied / partially_satisfied / unsatisfied / unresolved 裁决。
- `ConsistencyResult`: 跨 branch claim 冲突结果。
- `RevisionIssue`: verifier 输出给 supervisor 的结构化修订问题。
- `BranchRevisionBrief`: supervisor 为 patch/follow-up/counterevidence work 生成的修订简报。
- `TaskLedgerArtifact` / `ProgressLedgerArtifact`: 权威记录 issue lifecycle、resolution linkage、revision lineage 与 stop reason。

这些 artifacts 会被持久化到 Deep Research runtime snapshot，并通过 public artifacts 对外暴露。

## Tool-Agent 契约

researcher / verifier 的 bounded tool-agent 不再只是生成自由文本，而是围绕结构化 contracts 工作：

- researcher tool-agent 需要输出 `ClaimUnit`、`BranchSynthesis`、`resolved_issue_ids`。
- verifier tool-agent 需要先读取 `fabric_get_verification_contracts`，再提交 `claim_ids`、`obligation_ids`、`consistency_result_ids`、`issue_ids`。
- 当 verifier tool-agent 在 `claim_check` 或 `coverage_check` 明确给出 `passed` 时，runtime 会把该裁决映射为结构化 grounding / coverage artifacts，而不是继续只依赖 summary 文本启发式。

## Rollout 指南

建议按下面顺序启用和观察这条能力：

1. 先在多分支 Deep Research runtime 中启用 contract-first verification。
2. 打开 `quality_update`、public artifacts 与 task/progress ledger 观测，确认 claim grounding、coverage matrix、revision issues 持续更新。
3. 在 bounded tool-agent 模式下验证 researcher / verifier / reporter 三条路径都能提交结构化 bundle。
4. 用 checkpoint/resume 回归验证 revision lineage、issue status 与 terminal state 可以恢复。
5. 只有当 `outline_gate` 在 blocking issue 条件下稳定拒绝成文后，再把这套结果用于 UI 的 final report gating。

## Benchmark 指标

本轮 rollout 重点关注三项 revision-loop 指标：

- `verification_precision`: `grounded_claims / total_checked_claims`。用于衡量当前验证通过的 claim 比例。
- `unresolved_issue_count`: 当前仍处于 `open` 或 `accepted` 状态的 revision issue 数量。
- `revision_convergence`: `resolved_issues / total_revision_issues`。用于衡量修订闭环是否在收敛。

这些指标会出现在：

- `quality_update` SSE 事件
- `deep_research_artifacts.quality_summary`
- `scripts/benchmark_deep_research.py` 的执行模式输出聚合指标

建议把这三项指标与既有的 `citation_coverage`、`query_coverage_score`、`unsupported_claims_total` 一起观察，而不是单独解读任一指标。
