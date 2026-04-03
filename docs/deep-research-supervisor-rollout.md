# Deep Research Supervisor Rollout

更新日期：2026-04-02

## 目标

本次改造把 `multi_agent` Deep Research 的控制面从公开的 `planner/coordinator` 双角色收敛为单一 `supervisor` 角色，并保留 `clarify -> scope -> scope_review` 前置门控。自 2026-04-02 起，正式协议进一步收敛为：

- `clarify -> scope -> scope_review -> research_brief -> supervisor_plan`
- `dispatch -> researcher -> merge -> verify -> supervisor_decide`
- `outline_gate -> report -> finalize`

## 当前架构

- `clarify`：判断是否需要补充上下文，并产出 intake summary。
- `scope`：基于 intake 生成结构化 scope draft。
- `scope_review`：等待用户批准或给出自然语言修订意见。
- `research_brief`：把已批准 scope 归一化为控制面专用的 `research brief`，并初始化 `task ledger` / `progress ledger`。
- `supervisor_plan`：读取权威 `research brief`，生成或补充 branch 任务，并把计划快照写入 runtime snapshot 与 artifact store。
- `dispatch`：按 graph 预算和并发限制派发 `researcher` branch 任务。
- `researcher`：返回结构化 `ResearchSubmission`，必要时附带注册过的 `CoordinationRequest`。
- `verify`：产出 `VerificationResult`、`coverage matrix`、`contradiction registry`、`missing evidence list` 和收敛后的 `CoordinationRequest`。
- `supervisor_decide`：统一决定 `retry_branch / replan / dispatch / outline_gate / report / stop`，并持久化 `SupervisorDecisionArtifact`。
- `outline_gate`：只消费已验证 branch synthesis 与结构化验证 artifacts，生成 `outline` 或 `outline_gap`。
- `report`：只在 outline 已就绪且不存在阻塞性 `outline_gap` 时生成最终报告。

## 关键 artifact

- `ResearchBriefArtifact`：approved scope 的唯一机器契约。
- `TaskLedgerArtifact`：记录 branch 目标、coverage target、状态与请求挂接关系。
- `ProgressLedgerArtifact`：记录当前 phase、未决 request、决策历史、outline 状态与停止原因。
- `CoverageMatrixArtifact`：记录 coverage 维度与当前覆盖状态。
- `ContradictionRegistryArtifact`：记录冲突 claim、来源与建议动作。
- `MissingEvidenceListArtifact`：记录仍缺失的证据与受影响结论。
- `OutlineArtifact`：记录最终报告前的章节结构、引用关系与阻塞性结构缺口。
- `CoordinationRequest`：只允许 `retry_branch`、`need_counterevidence`、`contradiction_found`、`outline_gap`、`blocked_by_tooling`。
- `ResearchSubmission`：表达 researcher / verifier / reporter 的结构化 bundle。
- `SupervisorDecisionArtifact`：持久化 supervisor 的计划与循环决策。

## 观测点

- `research_agent_start` / `research_agent_complete` 现在会暴露 `supervisor` 角色。
- `research_artifact_update` 会额外暴露：
  - `research_brief`
  - `task_ledger`
  - `progress_ledger`
  - `coverage_matrix`
  - `contradiction_registry`
  - `missing_evidence_list`
  - `outline`
  - `coordination_request`
  - `research_submission`
  - `verification_submission`
  - `supervisor_decision`
- 前端流式消费可以直接区分：
  - `clarify`
  - `scope`
  - `scope_review`
  - `research_brief`
  - `supervisor`
  - `research`
  - `verify`
  - `outline_gate`
  - `report`

## 迁移说明

- 移除的输入：
  - `deepsearch_engine=legacy`
  - `deepsearch_mode=auto|tree|linear`
  - `tree_parallel_branches`
  - `deepsearch_tree_max_searches`
- 新配置名：
  - `DEEPSEARCH_PARALLEL_WORKERS`
  - `DEEPSEARCH_MAX_SEARCHES`
- 回退方式：
  - 不再提供运行时级别的 legacy fallback。
  - 如果需要回退，只能整体回退这次 cleanup 变更。

## 协议约束

- `reporter` 不允许在缺少 outline 或存在阻塞性 `outline_gap` 时直接生成最终报告。
- `researcher`、`verifier` 和报告准备阶段提交 request 时，只允许使用注册过的 5 个 request type。
- 公共 `deep_research_artifacts` 现在会对外暴露 `research_brief`、双 ledger、结构化验证 artifacts、`outline` 和 `coordination_requests`。
- 本次协议中不包含 `needs_human_decision`，也不新增新的 HITL 审批入口。

## 后续缺口

- `researcher`、`verifier`、`reporter` 仍然是角色化的受限执行器，但还没有全部切到通用 LangChain tool-agent loop。
- fabric tools 目前以 blackboard payload 与角色 allowlist 为主，后续可以继续向显式 tool 注册推进。
- 预算 enforcement 的专用单测还可以继续细化到 `supervisor_decide` 分支级语义。
