# Optimize deep research validation

## Goal

优化 Deep Research 当前的校验与报告生成链路，把“质量评估”和“报告是否可生成”解耦。目标是在不引入阻塞报告生成硬 gate 的前提下，提升章节质量判断、风险表达和最终报告的可解释性。

## What I already know

* 当前主校验入口在 `agent/runtime/deep/orchestration/graph.py::_review_section_draft()`。
* 当前章节评审基于 `objective_score`、`grounding_ratio`、来源/passage 是否齐备、freshness advisory 来生成 `blocking_issues` / `advisory_issues`。
* 当前 `reviewer -> supervisor_decide -> outline_gate -> report -> final_claim_gate -> finalize` 已经部分软化：
* `outline_gate` 允许在有 `reportable_section_drafts` 时输出 partial report。
* `final_claim_gate` 发现 `unsupported` / `contradicted` 时只标记 `review_needed`，不再阻塞 `finalize`。
* 当前仍然存在较强 gate 语义的地方主要是 reviewer 层和 section certification 聚合逻辑。
* 当前报告上下文 `ReportSectionContext` 只包含标题、摘要、findings、branch_summaries、citation_urls，扩展风险/置信度字段的改造面较小。

## Assumptions (temporary)

* 本次优先做后端运行时与 artifact 结构调整，不做前端界面改版。
* 本次按优先级顺序只做三件事：
* 1. 把 pass/fail/certified/blocked 改成质量快照视角
* 2. 让 reviewer 只提补强建议，不决定是否允许出报告
* 3. 报告按置信度/风险渲染，而不是等待全部 certified
* 不在本轮引入 claim-level 全量重构，但会为后续 claim-level 校验预留结构。
* 不允许因为质量问题阻塞最终报告生成；只有系统错误才允许终止流程。

## Open Questions

* 对外公开的 `validation_summary` / `section_certifications` 是否需要在一个过渡期内保持兼容字段，避免影响现有消费方？

## Requirements (evolving)

* 保留当前 Deep Research 多阶段运行时结构，不推翻现有 LangGraph 流程。
* 将章节质量表达为可聚合、可解释的评估快照，而不是通过/失败二元 gate。
* 章节评审结果应能继续驱动“补强研究/修订”的调度，但不能直接阻断报告生成。
* 报告输出必须显式区分高置信结论、有限证据结论和待人工复核项。
* runtime artifacts 与 public artifacts 需要暴露新的质量/风险字段。

## Acceptance Criteria (evolving)

* [ ] 章节评审不再依赖 `blocking_issues -> blocked` 作为报告前置条件。
* [ ] 即使存在未完全认证章节，只要有可报告内容，也能生成带限制说明的报告。
* [ ] 最终报告能区分不同置信度/风险等级的信息，而不是把所有章节平铺输出。
* [ ] 公开 artifact 中能看出章节质量、风险标记和建议后续动作。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 前端 deep research 展示界面重写
* 引入新的外部评测平台或 SaaS
* 全量 claim-level verifier 重构

## Technical Notes

* 关键文件：
* `agent/runtime/deep/orchestration/graph.py`
* `agent/runtime/deep/schema.py`
* `agent/runtime/deep/artifacts/public_artifacts.py`
* `agent/runtime/deep/roles/reporter.py`
* 参考方向：
* STORM：研究与写作解耦，优先产出可用报告
* GPT Researcher：planner/executor/publisher 分层聚合
* AutoGen Reflection：reviewer 作为 critique loop，而不是最终 gate
* Ragas / 类似 eval 框架：把 groundedness / relevancy 作为质量指标，而不是控制流硬条件
