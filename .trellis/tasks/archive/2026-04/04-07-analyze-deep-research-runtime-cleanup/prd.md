# brainstorm: analyze deep research runtime cleanup

## Goal

梳理当前 Deep Research 运行时从根图入口到结果产出的实际执行链路，识别已经不再被当前流程消费的逻辑、兼容分支和代码路径，并在不破坏现有 deep research / checkpoint / artifact 对外契约的前提下做最小清理。

## What I already know

* 用户目标是“分析当前的 deep research 流程，清除其中不用的逻辑、代码”。
* 当前仓库已有独立任务 `04-07-deep-research-agent-tools`，它关注工具与角色文档，不直接负责运行时清理。
* Deep Research 根图入口在 `agent/runtime/nodes/deep_research.py`，节点内部调用 `agent/runtime/deep/entrypoints.py`。
* `agent/runtime/deep/entrypoints.py` 当前只保留 `run_deep_research()`，并直接委托给 `agent/runtime/deep/orchestration/graph.py` 中的 `run_multi_agent_deep_research(...)`。
* `agent/runtime/deep/orchestration/graph.py` 注释声明当前运行时主链路为：`clarify -> scope -> scope_review -> research_brief -> supervisor_plan -> dispatch -> researcher/revisor -> merge -> reviewer -> supervisor_decide -> outline_gate -> report -> final_claim_gate -> finalize`。
* Deep Research 相关的 artifact 读取与恢复还连接到 `main.py`、`common/checkpoint_runtime.py`、`agent/core/state.py`。

## Assumptions (temporary)

* 本任务优先清理“当前真实流程已不再使用”的代码，不重写 Deep Research 架构。
* 需要把“未使用”限定为没有运行时消费者、没有 checkpoint/resume 依赖、没有测试或公开输出契约依赖。
* 本任务主要是后端运行时清理，可能涉及少量跨层契约检查，但不默认改前端展示。

## Open Questions

* 是否要保留对“旧 checkpoint / 旧 artifact snapshot 结构”的兼容读取？这会直接决定能否删除 `public_artifacts.py` 与 runtime store 中的一批 legacy fallback。

## Requirements (evolving)

* 画清当前 Deep Research 的真实执行链路和关键状态/artifact 流向。
* 识别并删除没有实际消费者的逻辑、分支、字段、辅助函数或兼容代码。
* 保留 chat/deep research 模式切换、interrupt/resume、artifact 输出等现有行为。
* 为被清理的路径补足或更新回归测试。
* 不再兼容旧 `artifact_store` snapshot 结构，只接受当前 lightweight runtime snapshot。

## Acceptance Criteria (evolving)

* [ ] 可以说明当前 Deep Research 从入口到完成的实际流程和关键模块。
* [ ] 至少一组确认无消费者的逻辑/代码被删除，而不是只做文档整理。
* [ ] Deep Research 相关回归测试更新并通过。
* [ ] 不引入 chat 或 checkpoint 恢复回归。
* [ ] 旧 `branch_results` / `validation_summaries` / legacy artifact payload 不再从 nested runtime snapshot 被恢复。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 不重做 Deep Research 的整体产品设计
* 不在本任务中扩展新角色、新工具能力或新 UI 展示
* 不清理与 Deep Research 无关的通用状态字段或普通聊天逻辑

## Technical Notes

* 已检查入口与主运行时文件：
  * `agent/runtime/nodes/deep_research.py`
  * `agent/runtime/deep/entrypoints.py`
  * `agent/runtime/deep/orchestration/graph.py`
* 需要进一步检查的高风险边界：
  * `main.py` 中 deep research artifacts 的读取与恢复
  * `common/checkpoint_runtime.py` 的公共 artifact 构建
  * `agent/runtime/deep/roles/`、`agent/infrastructure/agents/factory.py` 的角色/工具装配
  * Deep Research 测试集，尤其是 runtime、checkpointer、resume 相关测试
* 当前确认的真实执行链路是：
  * 根图路由到 `agent/runtime/nodes/deep_research.py`
  * 节点调用 `agent/runtime/deep/entrypoints.py:run_deep_research()`
  * entrypoint 直接委托 `agent/runtime/deep/orchestration/graph.py:run_multi_agent_deep_research()`
  * multi-agent graph 实际节点为：`bootstrap -> clarify -> scope -> scope_review -> research_brief -> outline_plan -> dispatch -> researcher/revisor -> merge -> reviewer -> supervisor_decide -> outline_gate -> report -> final_claim_gate -> finalize`
* 当前 multi-agent runtime 持久化的 `deep_runtime.artifact_store` 是 lightweight 结构，测试也明确断言只包含：
  * `scope`
  * `outline`
  * `plan`
  * `evidence_bundles`
  * `section_drafts`
  * `section_reviews`
  * `section_certifications`
  * `final_report`
* 当前代码里已发现的 legacy/兼容读取点：
  * `agent/runtime/deep/artifacts/public_artifacts.py`
    * `_normalize_legacy_sources`
    * `_normalize_legacy_fetched_pages`
    * `_normalize_legacy_passages`
    * `_build_legacy_public_artifacts`
    * 对 `branch_results` / `validation_summaries` 的 fallback 读取
  * `agent/runtime/deep/orchestration/graph.py`
    * `LightweightArtifactStore.__init__()` 对 `branch_results` / `validation_summaries` 的兼容读取
    * `branch_results()` / `validation_summaries()` 这类 section_* 的别名方法
* 当前已确认仍然是活跃契约，不能直接判定为废代码的部分：
  * `main.py` 中 `deep_research_clarify` / `deep_research_scope_review` 的 resume payload 归一化
  * `common/checkpoint_runtime.py` 的 `deep_research_artifacts` 恢复链路
  * `state["deep_research_artifacts"]` 的 canonical 恢复读取

## Research Notes

### Constraints from our repo/project

* 需要保留 Deep Research 的 interrupt/resume、artifact 提取、session resume API。
* 不能只看当前调用链，还要看 checkpoint round-trip 和 `main.py` 对外返回结构。
* 当前测试明确覆盖：
  * 运行时只能走 `multi_agent`
  * `deep_runtime.artifact_store` 的 lightweight 结构
  * `deep_research_artifacts` 的提取/恢复与 resume API

### Feasible approaches here

**Approach A: 保守清理兼容层** (Recommended)

* How it works:
  * 保留旧 checkpoint / `deep_research_artifacts` 的读取兼容。
  * 只删除当前运行时内部确认无消费者的别名、重复投影、无效桥接。
* Pros:
  * 风险最低，不破坏已有会话恢复。
  * 更符合当前 PRD 里“checkpoint/runtime compatibility is a contract boundary”的约束。
* Cons:
  * 可删除代码量相对有限。

**Approach B: 清理旧 snapshot 兼容读取**

* How it works:
  * 继续保留 canonical `deep_research_artifacts` 恢复链路，但删除 `artifact_store` 旧结构兼容读取，例如 legacy sources/fetched_pages/passages 适配。
* Pros:
  * 能显著减少 runtime/artifact adapter 的历史包袱。
* Cons:
  * 可能影响历史 checkpoint 的 artifact 回填或旧快照恢复，需要补更强的回归测试。

**Approach C: 激进收口到当前 runtime**

* How it works:
  * 只保留当前 `multi_agent + lightweight artifact_store + canonical public artifacts` 合同，其余旧 snapshot/旧字段兼容全部移除。
* Pros:
  * 清理最彻底，后续维护最简单。
* Cons:
  * 会主动放弃历史会话/历史快照的恢复兼容，风险最高。

## Technical Approach

* `agent/runtime/deep/artifacts/public_artifacts.py`
  * 删除 legacy artifact_store 适配分支。
  * `build_public_deep_research_artifacts()` 只投影当前 lightweight snapshot。
* `agent/runtime/deep/orchestration/graph.py`
  * `LightweightArtifactStore` 仅恢复 `section_drafts` / `section_reviews` 等当前键。
  * 删除 `branch_results()` / `validation_summaries()` 这类仅为旧结构保留的别名入口。
* 测试
  * 增加回归，明确旧 nested runtime store 不再产生 public artifacts。
  * 增加回归，明确 runtime store 不再从旧键名恢复章节草稿/评审。

## Decision (ADR-lite)

**Context**: 用户要求清理当前 Deep Research 流程中的无用逻辑和代码，并明确选择“只保留当前 multi_agent runtime 契约”。

**Decision**: 删除 Deep Research runtime 内部对旧 `artifact_store` snapshot 的兼容读取，包括 legacy public artifact 适配、旧键名恢复和仅服务旧结构的内部别名方法；继续保留 canonical `deep_research_artifacts` 读取与 resume API。

**Consequences**:
* 历史 checkpoint 中如果只包含旧 `artifact_store` 结构，将不再自动回填为当前 public artifacts。
* 当前 multi-agent runtime、canonical artifact 恢复链路、session resume / evidence / export 仍保持工作。
* Deep Research 内部状态模型更简单，减少重复投影和双轨维护。
