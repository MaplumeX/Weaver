# Deep Research Supervisor Rollout

更新日期：2026-04-01

## 目标

本次改造把 `multi_agent` Deep Research 的控制面从公开的 `planner/coordinator` 双角色收敛为单一 `supervisor` 角色，并保留 `clarify -> scope -> scope_review` 前置门控。

## 当前架构

- `clarify`：判断是否需要补充上下文，并产出 intake summary。
- `scope`：基于 intake 生成结构化 scope draft。
- `scope_review`：等待用户批准或给出自然语言修订意见。
- `supervisor_plan`：读取已批准 scope，生成或补充 branch 任务，并把计划快照写入 runtime snapshot 与 artifact store。
- `dispatch`：按 graph 预算和并发限制派发 `researcher` branch 任务。
- `researcher`：返回结构化 `ResearchSubmission`，必要时附带 `CoordinationRequest`。
- `verify`：产出 `VerificationResult`、`ResearchSubmission` 和 `CoordinationRequest`，把重试 / replan / report-ready 信号显式交给 `supervisor_decide`。
- `supervisor_decide`：统一决定 `retry_branch / replan / dispatch / report / stop`，并持久化 `SupervisorDecisionArtifact`。
- `report`：只消费已验证 branch synthesis 生成最终报告。

## 关键 artifact

- `CoordinationRequest`：表达 follow-up、retry、replan、escalation、report-ready。
- `ResearchSubmission`：表达 researcher / verifier / reporter 的结构化 bundle。
- `SupervisorDecisionArtifact`：持久化 supervisor 的计划与循环决策。

## 观测点

- `research_agent_start` / `research_agent_complete` 现在会暴露 `supervisor` 角色。
- `research_artifact_update` 会额外暴露：
  - `coordination_request`
  - `research_submission`
  - `verification_submission`
  - `supervisor_decision`
- 前端流式消费可以直接区分：
  - `clarify`
  - `scope`
  - `scope_review`
  - `supervisor`
  - `research`
  - `verify`
  - `report`

## 回滚路径

如果 `multi_agent` supervisor 路径出现问题，按下面顺序回滚：

1. 将 `deepsearch_engine` 切回 `legacy`。
2. 保留 `clarify/scope/scope_review` 数据契约，不做 schema 回退。
3. 忽略 `coordination_requests`、`submissions`、`supervisor_decisions` 三类新增 artifacts。
4. 继续沿用既有 Deep Research 输出契约：`final_report`、`deepsearch_artifacts`、`research_tree`。

## 后续缺口

- `researcher`、`verifier`、`reporter` 仍然是角色化的受限执行器，但还没有全部切到通用 LangChain tool-agent loop。
- fabric tools 目前以 blackboard payload 与角色 allowlist 为主，后续可以继续向显式 tool 注册推进。
- 预算 enforcement 的专用单测还可以继续细化到 `supervisor_decide` 分支级语义。
