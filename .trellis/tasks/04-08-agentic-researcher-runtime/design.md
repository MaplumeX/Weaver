# Agentic Researcher Runtime Design

## Goal

将现有单轮 `researcher` 流水线重构为 branch-scoped、bounded multi-round runtime，同时保持外层 deep runtime 的控制面稳定：

* `planner` 生成更强的 branch 查询策略
* `researcher` 在 branch 内完成多轮补搜、证据评估和 claim grounding
* `supervisor` 只做确定性控制面增强
* `reviewer / verifier` 继续保留外层 hard gate

## Non-Goals

* 不把 `researcher` 升级为完全开放式通用 agent
* 不把 `supervisor` 升级为语义型全局调度 agent
* 不引入新的外部基础设施
* 不在第 1 期支持全局 `follow_up_research / counterevidence_research` 拓扑扩张

## High-Level Architecture

### Outer Runtime

Outer runtime 继续负责：

* scope 审核与批准
* outline 生成
* section task dispatch
* reviewer / verifier hard gate
* partial/full report 决策

### Inner Branch Runtime

每个 `section_research` 任务进入一个内部 branch runtime：

1. 规范化 branch context
2. 生成初始查询集
3. 执行一轮检索与抓取
4. 产出 evidence ledger
5. 做 coverage / quality / contradiction / grounding assessment
6. 决定 `continue / synthesize / bounded_stop`
7. 若继续，生成 follow-up queries 并进入下一轮

## Module Split

### Keep As Facade

`agent/runtime/deep/roles/researcher.py`

对外继续暴露：

```python
class ResearchAgent:
    def research_branch(
        self,
        task: ResearchTask | dict[str, Any],
        *,
        topic: str,
        existing_summary: str = "",
        max_results_per_query: int = 5,
    ) -> dict[str, Any]:
        ...
```

### New Modules

`agent/runtime/deep/researcher_runtime/contracts.py`

* branch 内部 dataclass / typed dict
* query spec / round result / assessment contracts

`agent/runtime/deep/researcher_runtime/state.py`

* `BranchResearchState`
* state 初始化与更新 helper

`agent/runtime/deep/researcher_runtime/planner.py`

* 初始查询生成
* follow-up query refine
* branch 内 counterevidence query refine

`agent/runtime/deep/researcher_runtime/search.py`

* 检索
* ranking
* fetch target selection
* content fetch + passage extraction

`agent/runtime/deep/researcher_runtime/assess.py`

* coverage assessment
* quality assessment
* contradiction assessment
* stop / continue decision

`agent/runtime/deep/researcher_runtime/grounding.py`

* claim extraction / normalization
* claim -> passage binding
* grounding summary

`agent/runtime/deep/researcher_runtime/runner.py`

* bounded multi-round loop
* stage transitions
* final outcome assembly

## Contracts

### BranchResearchState

```python
@dataclass
class BranchResearchState:
    task_id: str
    section_id: str | None
    branch_id: str | None
    topic: str
    objective: str
    acceptance_criteria: list[str]
    existing_summary: str
    domain_config: dict[str, Any]
    source_preferences: list[str]
    language_hints: list[str]
    freshness_policy: str
    authority_preferences: list[str]
    round_index: int = 0
    max_rounds: int = 3
    max_results_per_query: int = 5
    max_follow_up_queries_per_round: int = 2
    search_budget_remaining: int = 0
    token_budget_remaining: int = 0
    executed_queries: list[str] = field(default_factory=list)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    passages: list[dict[str, Any]] = field(default_factory=list)
    coverage_artifacts: list[dict[str, Any]] = field(default_factory=list)
    quality_artifacts: list[dict[str, Any]] = field(default_factory=list)
    contradiction_artifacts: list[dict[str, Any]] = field(default_factory=list)
    grounding_artifacts: list[dict[str, Any]] = field(default_factory=list)
    decision_artifacts: list[dict[str, Any]] = field(default_factory=list)
    open_gaps: list[str] = field(default_factory=list)
    stop_reason: str = ""
```

### New Schema Artifacts

需要在 [schema.py](/home/maplume/projects/Weaver/agent/runtime/deep/schema.py) 新增：

* `BranchQueryRoundArtifact`
* `BranchCoverageArtifact`
* `BranchQualityArtifact`
* `BranchContradictionArtifact`
* `BranchGroundingArtifact`
* `BranchDecisionArtifact`

### BranchResearchOutcome Extension

`ResearchAgent.research_branch()` 继续返回 dict，但扩展字段：

```python
{
    "queries": list[str],
    "search_results": list[dict[str, Any]],
    "sources": list[dict[str, Any]],
    "documents": list[dict[str, Any]],
    "passages": list[dict[str, Any]],
    "summary": str,
    "key_findings": list[str],
    "open_questions": list[str],
    "confidence_note": str,
    "claim_units": list[dict[str, Any]],
    "coverage_summary": dict[str, Any],
    "quality_summary": dict[str, Any],
    "contradiction_summary": dict[str, Any],
    "grounding_summary": dict[str, Any],
    "research_decisions": list[dict[str, Any]],
    "limitations": list[str],
    "stop_reason": str,
}
```

## Planner Design

### Outer Planner Changes

[planner.py](/home/maplume/projects/Weaver/agent/runtime/deep/roles/planner.py) 需要额外消费：

* `domain_config.search_hints`
* `domain_config.language_hints`
* `approved_scope.source_preferences`
* `approved_scope.time_boundary`
* `approved_scope.coverage_dimensions`
* `approved_scope.deliverable_constraints`

目标不是生成更多 task，而是生成更强的每 task 查询意图。

### Branch Query Strategy

每个 branch 初始 query set 至少包含这些类别：

* `base_query`
* `official_source_query`
* `freshness_query`
* `comparison_query`

注意：这些只是 `query_hints` 分类，不新增全局 `task_kind`。

## Researcher Inner Loop

### Runner Pseudocode

```python
def run_branch(state: BranchResearchState) -> BranchResearchOutcome:
    while state.round_index < state.max_rounds:
        round_spec = planner.build_round_queries(state)
        round_result = search.execute_round(state, round_spec)
        state = state_after_round(state, round_result)

        coverage = assess.evaluate_coverage(state)
        quality = assess.evaluate_quality(state)
        contradiction = assess.evaluate_contradictions(state)
        grounding = grounding.build_grounding(state)

        decision = assess.decide_next_step(
            state=state,
            coverage=coverage,
            quality=quality,
            contradiction=contradiction,
            grounding=grounding,
        )
        state = apply_decision(state, decision)

        if decision.action in {"synthesize", "bounded_stop"}:
            break

    return assemble_outcome(state)
```

### Decision Model

branch 内只允许这些动作：

* `continue_search`
* `refine_queries`
* `compare_evidence`
* `synthesize`
* `bounded_stop`

### Deterministic Stop Conditions

出现任一条件即可停止：

* `coverage_ready == True` 且 `grounding_ready == True`
* `round_index >= max_rounds`
* branch 预算耗尽
* 连续一轮没有新增高质量 evidence
* contradiction 高但无法继续补充有效证据

## Assessment Design

### Coverage Assessment

对每条 `acceptance_criteria` 输出：

```python
{
    "criterion": str,
    "status": "covered" | "partial" | "missing",
    "evidence_passage_ids": list[str],
    "notes": str,
}
```

聚合后输出：

* `coverage_ready`
* `covered_count`
* `missing_count`
* `missing_topics`

### Quality Assessment

输出至少这些维度：

* `authority_score`
* `freshness_score`
* `source_diversity_score`
* `evidence_density_score`
* `objective_alignment_score`
* `quality_ready`

### Contradiction Assessment

输出：

* `has_material_conflict`
* `conflict_source_urls`
* `conflicting_claims`
* `needs_counterevidence_query`

这里只影响 branch 内 query refine，不影响 outer topology。

### Grounding Assessment

对每个 claim 输出：

```python
{
    "claim_id": str,
    "claim_text": str,
    "importance": "primary" | "secondary",
    "evidence_passage_ids": list[str],
    "evidence_urls": list[str],
    "grounded": bool,
}
```

聚合后输出：

* `primary_grounding_ratio`
* `secondary_grounding_ratio`
* `grounding_ready`

## Supervisor Changes

### What To Change

[supervisor.py](/home/maplume/projects/Weaver/agent/runtime/deep/roles/supervisor.py)

* `create_outline_plan()` 增强 section contract
* `decide_section_action()` 消费 richer aggregate summary

[graph.py](/home/maplume/projects/Weaver/agent/runtime/deep/orchestration/graph.py)

* `_research_brief_node()` 生成 normalized policy pack
* `_dispatch_node()` 基于 richer branch status 进行确定性 dispatch
* `_supervisor_decide_node()` 基于 richer aggregate summary 做确定性控制

### What Not To Change In Phase 1

* 不启用 `SupervisorAction.REPLAN`
* 不启用 `SupervisorAction.SPAWN_FOLLOW_UP_BRANCH`
* 不启用 `SupervisorAction.SPAWN_COUNTEREVIDENCE_BRANCH`
* 不启用 `DEEP_SUPERVISOR_DECISION_PROMPT` 作为主流程决策源

## Graph Integration

### `_researcher_node()`

需要新增写入：

* branch round artifacts
* branch coverage artifact
* branch quality artifact
* branch contradiction artifact
* branch grounding artifact
* branch decision artifacts

### `_merge_node()`

需要累积：

* `searches_used`
* `tokens_used`
* branch quality summaries
* branch stop reasons

### `_reviewer_node()`

优先消费 branch 结构化产物，减少重复推导：

* coverage gaps
* primary claim grounding
* freshness limitations
* contradiction notes

## Prompt Changes

### Revise

* `DEEP_PLANNER_PROMPT`
* `DEEP_PLANNER_REFINE_PROMPT`
* `DEEP_RESEARCHER_EVIDENCE_SYNTHESIS_PROMPT`

### Add

* `DEEP_RESEARCHER_GAP_ANALYSIS_PROMPT`
* `DEEP_RESEARCHER_QUERY_REFINE_PROMPT`
* `DEEP_RESEARCHER_COUNTEREVIDENCE_PROMPT`
* `DEEP_RESEARCHER_CLAIM_GROUNDING_PROMPT`

## Testing Strategy

### Unit

* planner 能消费 richer scope/domain hints
* researcher inner loop 能执行多轮 bounded search
* coverage 满足时能提前 stop
* 无新增高质量证据时能 bounded stop
* contradiction 会触发 branch 内 counterevidence query refine
* grounding artifact 正确绑定 primary claims

### Runtime / Graph

* `_researcher_node()` 能写入 richer branch artifacts
* `_merge_node()` 能聚合新的 outcome 字段
* `_reviewer_node()` 能消费 richer branch artifacts 而不回归
* `_supervisor_decide_node()` 在 richer aggregate summary 下仍保持确定性

### Benchmark

对比改造前后：

* `query_coverage_score`
* `freshness_ratio_target` 达成率
* `primary_grounding_ratio`
* reviewer retry 次数
* partial report 比例

## Rollout Order

1. 扩展 schema 与 prompts
2. 重构 outer planner
3. 新增 `researcher_runtime` 子模块
4. 让 façade `ResearchAgent` 接入新 runner
5. 调整 graph / artifact store / reviewer 消费逻辑
6. 增强 supervisor 的确定性控制路径
7. 补测试与 benchmark

## Risk Notes

* 最大风险是 branch artifacts 增多后，`graph.py` 合并逻辑变复杂
* 第二个风险是 grounding contract 改动后影响 reviewer hard gate 阈值
* 第三个风险是多轮 branch loop 可能拉长时延，需要通过 `max_rounds` 和 budget 严格约束
