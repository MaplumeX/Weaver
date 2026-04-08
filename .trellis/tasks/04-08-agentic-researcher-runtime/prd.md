# brainstorm: deep research agentic researcher runtime

## Goal

将 Deep Research 中的 `researcher` 从单轮流水线执行器升级为 branch-scoped、有限工具、有限轮次的 agentic runtime，在不破坏外层 `supervisor / reviewer / verifier` 职责边界的前提下，显著提升研究补洞能力、证据绑定质量和研究结果稳定性。

## What I already know

* 当前 `researcher` 主要执行 `search -> rank -> fetch -> passage -> synthesize` 单轮流水线，缺少 branch 内自我补搜和覆盖评估闭环。
* 外层 runtime 已经存在 `scope / supervisor / reviewer / revisor / verifier / reporter` 分工，不适合把全局计划权再次下放给 `researcher`。
* `TaskStage` 已经预留了 `verify / grounding_check / coverage_evaluation / consistency_check / challenge / compare` 等阶段，可复用为内部子运行时阶段枚举。
* `domain routing` 已能输出 `search_hints / suggested_sources / language_hints`，但 deep runtime 当前基本只把它用于 provider profile，未充分注入 planner / researcher。
* reviewer 当前会基于 `objective_score / grounding_ratio / source_count / freshness advisory` 做 hard gate，并在证据不足时生成 retry task；这说明大量问题是研究后置发现，而不是研究前置收敛。
* 已有 benchmark 脚本可用于对比 query coverage、freshness 等指标，适合做改造前后回归验证。

## Assumptions (temporary)

* 第一期按确认方案推进：同步重构 `planner + researcher + branch artifacts`，`reviewer / verifier` 保留外层职责。
* 第一期允许对 `researcher` 内部实现做较大重构，但尽量保持外层 `ResearchTask -> BranchResearchOutcome` 接口稳定。
* 第一阶段可以同步调整相关 schema、prompt、测试和 benchmark 指标，但不引入新的外部基础设施依赖。
* 外层 orchestrator 仍保留 branch 调度、section gate 和最终质量裁决职责。
* `supervisor` 需要做控制面增强，但不接管 branch 内部研究执行。

## Open Questions

* 暂无阻塞性开放问题。已确定第 1 期中 `supervisor` 只做确定性的控制面增强，不引入语义型 `replan / spawn_follow_up_branch / spawn_counterevidence_branch` 能力。

## Requirements (evolving)

* `researcher` 需要具备 branch 内多轮研究能力，而不是单轮流水线。
* `planner` 需要消费 domain hints、source preferences、language hints、time boundary 等更丰富的 scope 信号。
* `researcher` 必须保持有限工具边界，默认仅使用 `search / read / extract / synthesize / verify` 相关能力。
* branch 内需要显式 coverage assessment，能够按 `acceptance_criteria` 判断已覆盖、部分覆盖和缺失。
* branch 内需要显式 evidence quality assessment，至少覆盖 authority、freshness、grounding、diversity、contradiction 风险。
* synthesis 必须输出更强的 claim grounding，而不是依赖后置粗匹配。
* 在证据不足时，系统应输出有限结论和 open questions，而不是强行给出确定性摘要。
* 保持事件流和任务状态可观察，便于 SSE 展示和 benchmark 统计。
* `supervisor` 需要消费新的 branch 级质量产物，并据此做更精确的 dispatch / stop / report 控制。
* `supervisor` 相关节点需要避免与 branch 内 agentic researcher 的微观循环重复决策。
* `supervisor` 第一期不引入语义型 `replan / spawn_follow_up_branch / spawn_counterevidence_branch`，只保留确定性控制面动作。

## Acceptance Criteria (evolving)

* [ ] `researcher` 能在单个 branch 内执行受控多轮研究闭环。
* [ ] branch outcome 包含 coverage / quality / grounding 等结构化产物，足以支撑 reviewer hard gate。
* [ ] reviewer 的 retry 数量相较当前设计下降，或至少其 retry 原因更聚焦于真正外部不可得信息。
* [ ] benchmark 能观察到 query coverage、freshness 或 grounding 至少一项质量指标的稳定提升。
* [ ] 现有 deep research 主流程测试继续通过，并新增 agentic researcher 回归测试。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 不将 `researcher` 升级为完全开放式通用 agent
* 不移除外层 `supervisor / reviewer / verifier`
* 不引入新的外部队列、数据库或独立 worker 进程
* 不在第一阶段解决所有领域专用抓取问题（如复杂 PDF、表格、OCR）

## Technical Notes

* 已检查核心文件：
* `agent/runtime/deep/roles/researcher.py`
* `agent/runtime/deep/roles/planner.py`
* `agent/runtime/deep/orchestration/graph.py`
* `agent/runtime/deep/schema.py`
* `agent/research/domain_router.py`
* `agent/runtime/nodes/routing.py`
* `agent/prompts/runtime_templates.py`
* `tools/research/content_fetcher.py`
* `scripts/benchmark_deep_research.py`
* 关键设计方向：推荐采用“branch 内部子图 / 受控 agentic runtime”，而不是继续堆叠线性流水线，也不是放开成完全自治 agent。
* 需要特别注意跨层 contract：`ResearchTask` 输入、`BranchResearchOutcome` 输出、artifact store 持久化、SSE 事件、benchmark 指标都可能受到影响。
* 当前 `supervisor` 与相关节点的实际职责较轻：
* `create_outline_plan()` 负责把 `core_questions` 映射成 section。[agent/runtime/deep/roles/supervisor.py]
* `_dispatch_node()` 只做 ready task claim 与下发。[agent/runtime/deep/orchestration/graph.py]
* `_supervisor_decide_node()` 主要根据 `aggregate_sections`、budget 和 `report_ready` 决定 `dispatch / report / stop`。[agent/runtime/deep/orchestration/graph.py]
* 因此适合做“控制面增强”，不适合把 branch 内研究判断继续堆到 `supervisor`。
* 仓库里已经有 `SupervisorAction.REPLAN / SPAWN_FOLLOW_UP_BRANCH / SPAWN_COUNTEREVIDENCE_BRANCH` 枚举，但当前实现未真正落地相应动作链路；第 1 期不启用这些动作。[agent/runtime/deep/roles/supervisor.py]
* 仓库里已经有 `DEEP_SUPERVISOR_DECISION_PROMPT` 模板注册，但当前主流程没有实际使用它做 supervisor 语义决策；第 1 期继续保持未启用状态。[agent/prompts/runtime_templates.py]

## Research Notes

### Feasible Approaches For Supervisor Control Plane

**Approach A: 混合式 supervisor**

* `budget / stop / report` 继续走确定性规则
* `replan / spawn_follow_up_branch / spawn_counterevidence_branch` 走 LLM 语义决策
* 优点：
* 保留关键控制面的稳定性和可测性
* 只把最需要语义判断的“研究扩展动作”交给模型
* 能复用现有 `SupervisorAction` 和 `DEEP_SUPERVISOR_DECISION_PROMPT`
* 缺点：
* 需要设计好触发门槛，避免 supervisor 过度扩张任务

**Approach B: 确定性增强 supervisor（已选）**

* `dispatch / report / stop / bounded retry` 都由结构化 artifacts + 阈值驱动
* 通过 richer scope、section contract 和 branch quality artifacts 提升 supervisor 判断质量
* 优点：
* 最稳定、最好做回归测试
* 与第 1 期 agentic researcher 的 bounded loop 分工最清晰
* 缺点：
* 暂时不支持全局语义型研究拓扑扩张

**Approach C: LLM-first supervisor**

* 大部分控制面动作都交给模型决策，规则仅兜底
* 优点：
* 最灵活
* 缺点：
* 波动大，容易破坏现有 deep runtime 的确定性与预算控制

### Chosen Direction

* 采用 Approach B。
* `supervisor` 的职责增强为：
* 读取 branch 级质量产物
* 在确定性 budget/report gate 下做更精确的 dispatch / stop / partial report 判断
* 仅做 section 级宏观控制，不扩张全局研究拓扑，不进入 branch 内部微观循环

## Converged Scope

### In Scope For Phase 1

* 重构 `planner`，让其消费 richer scope 和 domain signals
* 将 `researcher` 重构为 branch-scoped、bounded multi-round runtime
* 增加 branch 级 coverage / quality / contradiction / grounding artifacts
* 增强 `supervisor` 及相关图节点，使其消费 richer artifacts 并做更精细的确定性控制
* 保持 `reviewer / verifier` 作为外层 hard gate
* 扩展测试和 benchmark 指标

### Still Out Of Scope For Phase 1

* 完全开放式通用 agent
* supervisor 接管 branch 内部工具调用
* 独立 worker 进程或新的外部基础设施
* 复杂 PDF/OCR/表格抽取系统

## Proposed Design

### 1. Runtime Layering

**Outer graph responsibilities**

* `scope`：定义研究范围与约束
* `supervisor`：生成 section contract、消费 branch 质量产物、决定全局扩张或收敛
* `reviewer / verifier`：做最终 hard gate，不负责 branch 内自我补搜
* `reporter`：生成最终报告

**Inner branch runtime responsibilities**

* `planner-lite`：按 branch objective 生成初始与补充查询
* `researcher runtime`：在 branch 内执行 bounded rounds
* `branch assessor`：产出 coverage / quality / contradiction / grounding 结论
* `branch synthesizer`：在证据充分时输出结构化草稿，否则输出有限结论与 open questions

### 2. Module Split

**Keep**

* `agent/runtime/deep/roles/researcher.py`
* 保留为 façade，对外仍提供 `research_branch()`

**Add**

* `agent/runtime/deep/researcher_runtime/state.py`
* `agent/runtime/deep/researcher_runtime/planner.py`
* `agent/runtime/deep/researcher_runtime/search.py`
* `agent/runtime/deep/researcher_runtime/assess.py`
* `agent/runtime/deep/researcher_runtime/grounding.py`
* `agent/runtime/deep/researcher_runtime/runner.py`
* `agent/runtime/deep/researcher_runtime/contracts.py`

**Update**

* `agent/runtime/deep/roles/planner.py`
* `agent/runtime/deep/roles/supervisor.py`
* `agent/runtime/deep/orchestration/graph.py`
* `agent/runtime/deep/schema.py`
* `agent/prompts/runtime_templates.py`

### 3. New Branch-Level Contracts

**BranchResearchState**

* `task_id`
* `section_id`
* `branch_id`
* `topic`
* `objective`
* `acceptance_criteria`
* `domain_config`
* `source_preferences`
* `freshness_policy`
* `coverage_targets`
* `round_index`
* `max_rounds`
* `search_budget_remaining`
* `tokens_budget_remaining`
* `executed_queries`
* `candidate_results`
* `documents`
* `passages`
* `coverage_assessment`
* `quality_assessment`
* `contradiction_assessment`
* `grounding_assessment`
* `open_gaps`
* `stop_reason`

**New artifacts in `schema.py`**

* `BranchQueryRoundArtifact`
* `BranchCoverageArtifact`
* `BranchQualityArtifact`
* `BranchContradictionArtifact`
* `BranchGroundingArtifact`
* `BranchDecisionArtifact`

**BranchResearchOutcome extensions**

* `coverage_summary`
* `quality_summary`
* `contradiction_summary`
* `grounding_summary`
* `research_decisions`
* `limitations`
* `stop_reason`

### 4. Planner Changes

* `ResearchPlanner.create_plan()` 和 `refine_plan()` 增加 richer prompt 输入：
* `domain_config.search_hints`
* `domain_config.language_hints`
* `scope.source_preferences`
* `scope.time_boundary`
* `scope.coverage_dimensions`
* `scope.deliverable_constraints`
* branch task 的 `query_hints` 改为分层结构来源：
* base query
* official-source query
* freshness query
* comparison / counterevidence query
* 第 1 期不新增全局 `task_kind=counterevidence_research` 与 `task_kind=follow_up_research`，这些策略先保留在 branch 内部 query 级别实现

### 5. Researcher Inner Loop

**Round flow**

1. normalize branch context
2. build round query set
3. search and rank
4. select fetch targets
5. fetch and extract passages
6. assess coverage / quality / contradiction / grounding
7. decide:
* `search_again`
* `compare_sources`
* `synthesize`
* `bounded_stop`
8. if continue, emit `BranchDecisionArtifact` and enter next round

**Loop bounds**

* `max_rounds` 默认 3
* branch 内新增 `max_follow_up_queries_per_round`
* 任何情况下不得突破 outer runtime budget

### 6. Supervisor Enhancements

**`create_outline_plan()`**

* section 不再只有 `objective / acceptance_checks / freshness_policy`
* 新增：
* `coverage_targets`
* `source_preferences`
* `authority_preferences`
* `counterevidence_required`
* `follow_up_policy`
* `branch_stop_policy`

**`_research_brief_node()`**

* 除了把 approved scope 落盘，还要生成 normalized policy pack：
* scope normalized fields
* domain hints
* freshness defaults
* authority defaults
* section dispatch policy

**`decide_section_action()`**

* 保留确定性前置 gate：
* budget exhausted
* no reportable content
* all sections certified
* 在未命中上述 gate 时，基于结构化 aggregate summary 与 branch artifacts 做确定性动作判断：
* `dispatch`
* `report`
* `stop`
* `bounded_retry`

**Deterministic triggers**

* `dispatch`
* 仍有未认证 section，且对应 branch outcome 显示可继续补搜
* `report`
* 已有足够 reportable section，或 coverage/quality 达到可报告阈值
* `bounded_retry`
* branch outcome 显示存在可恢复缺口，且 retry/budget 未超限
* `stop`
* budget exhausted、section blocked 或整体不具备继续研究价值

### 7. Graph Changes

**`_dispatch_node()`**

* claim ready tasks 时继续以现有 `section_research / section_revision` 为主
* 需要结合 richer branch artifacts 和 retry policy 做更精细的 ready task 选择

**`_route_after_dispatch()`**

* `section_revision` 继续路由到 `revisor`
* 其余研究任务继续路由到 `researcher`

**`_researcher_node()`**

* 接收 richer branch outcome
* 向 artifact store 写入新增 branch artifacts
* 将 `TaskStage` 映射到 branch 内阶段输出

**`_merge_node()`**

* 累积新增 artifact
* 把 branch decision 与 quality assessment 汇总到 runtime state

**`_reviewer_node()`**

* 优先消费 `coverage_summary / grounding_summary / contradiction_summary`
* 减少 reviewer 自己重复推导 branch 质量问题

**`_supervisor_decide_node()`**

* 先跑确定性 gate
* 再消费 aggregate summary 与 branch artifacts 做确定性 dispatch/report/stop 判断
* 不在第 1 期构造新的研究拓扑类型

### 8. Prompt Changes

**Revise existing**

* `DEEP_PLANNER_PROMPT`
* `DEEP_PLANNER_REFINE_PROMPT`
* `DEEP_RESEARCHER_EVIDENCE_SYNTHESIS_PROMPT`

**Add**

* `DEEP_RESEARCHER_GAP_ANALYSIS_PROMPT`
* `DEEP_RESEARCHER_QUERY_REFINE_PROMPT`
* `DEEP_RESEARCHER_COUNTEREVIDENCE_PROMPT`
* `DEEP_RESEARCHER_CLAIM_GROUNDING_PROMPT`

### 9. Testing Plan

**Unit tests**

* planner consumes domain/scope hints and emits richer `query_hints`
* branch runtime performs multi-round bounded loop
* branch runtime stops when coverage satisfied
* contradiction assessment can trigger branch 内 counterevidence query refinement
* grounding artifact binds claims to evidence passages
* supervisor deterministic decision consumes richer branch artifacts without引入语义动作

**Graph/runtime tests**

* `_supervisor_decide_node()` can基于 richer artifacts 产生更精确的 `dispatch / report / stop`
* reviewer consumes richer branch artifacts without regression

**Benchmark**

* compare pre/post:
* query coverage
* freshness ratio
* grounded primary claims ratio
* retry count from reviewer
* partial report frequency

## Recommended Implementation Order

1. 扩展 schema 和 prompts，先把 contracts 定下来
2. 重构 planner，让 task 能携带 richer branch hints
3. 实现 `researcher_runtime` 子模块与 bounded loop
4. 修改 graph，把 richer outcome 接进 artifact store
5. 增强 supervisor 的确定性控制路径
6. 更新 reviewer 消费逻辑
7. 补测试与 benchmark
