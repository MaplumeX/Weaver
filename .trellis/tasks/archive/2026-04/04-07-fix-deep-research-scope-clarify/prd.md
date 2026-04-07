# Fix deep research scope and clarify duplication

## Goal

修复 Deep Research 流程中的两个异常行为：跳过 `scope` 阶段，以及 `clarify` 被重复询问；定位是否由 checkpoint/checkpointer 恢复链路导致，并为该类问题补上回归保护。

## What I already know

* 用户观察到 Deep Research 会跳过 `scope` 阶段。
* 用户观察到 `clarify` 会问两次。
* 用户怀疑问题与 `checkpointer` 有关。
* 代码中 Deep Research 的核心状态机位于 `agent/runtime/deep/orchestration/graph.py`。
* `main.py` 负责 checkpoint resume payload normalize、streaming 与 interrupt/resume API。

## Assumptions (temporary)

* 问题可能发生在中断恢复后 `next_step`、`intake_status` 或 clarify/scope 相关运行时状态未被正确推进。
* 问题也可能与旧 checkpoint 数据或 resume payload 兼容逻辑有关，而不只是单纯节点实现错误。

## Open Questions

* 暂无阻塞问题；当前按“修复现有恢复链路，不承诺兼容错误排序产生的历史 checkpoint 读取结果”推进。

## Requirements (evolving)

* Deep Research 在需要澄清时，用户回答后只能进入一次后续流程，不应重复进入同一 clarify 问题。
* Deep Research 在 clarify 完成后必须进入 `scope`/`scope_review` 流程，不得无故跳过。
* 若根因与 checkpoint/resume 有关，修复应落在正确的状态恢复边界，而不是仅靠前端规避。
* 为修复行为补充自动化回归测试。

## Acceptance Criteria (evolving)

* [ ] 复现并定位导致 clarify 重复与 scope 跳过的根因。
* [ ] 修复后，含 checkpoint resume 的 Deep Research 流程按 `clarify -> scope -> scope_review -> research_brief` 的预期推进。
* [ ] 修复后，同一 clarify 问题不会在一次有效回答后再次出现。
* [ ] 新增或更新测试，能够在修复前失败、修复后通过。

## Definition of Done (team quality bar)

* Tests added or updated for the affected runtime path
* Relevant lint / targeted tests pass
* No unrelated behavior changes introduced in the Deep Research runtime

## Out of Scope (explicit)

* 不重构整个 Deep Research 架构
* 不顺带处理无关的前端展示问题
* 暂不假设需要兼容所有历史 checkpoint，除非需求明确要求

## Technical Notes

* 初步关注文件：
  * `agent/runtime/deep/orchestration/graph.py`
  * `main.py`
  * `tests/test_deepsearch_multi_agent_runtime.py`
* 已发现 interrupt checkpoint 名称：
  * `deep_research_clarify`
  * `deep_research_scope_review`
* 研究结论：
  * `graph.py` 内部的 `clarify -> scope -> scope_review` 转移在 `MemorySaver` 下已有测试覆盖，基本行为正常。
  * 自定义 `WeaverPostgresCheckpointer` 在未显式传入 `checkpoint_id` 时，使用 `created_at DESC` 获取“最新 checkpoint”。
  * 本地 LangGraph 官方 Postgres saver 使用的是 `checkpoint_id DESC`，而不是 `created_at DESC`。
  * 该差异会使 resume/status 查询有机会拿到旧 checkpoint，进而重复暴露旧的 `deep_research_clarify` interrupt。

## Technical Approach

将 `common/weaver_checkpointer.py` 的 latest-checkpoint 查询与 list 查询改为按 `checkpoint_id DESC` 排序，并补充测试，确保在插入顺序与 checkpoint 时间顺序不一致时仍能选中正确 checkpoint。

## Decision (ADR-lite)

**Context**: Deep Research 的中断恢复依赖“按 thread_id 取最新 checkpoint”，该逻辑由自定义 Postgres checkpointer 提供。  
**Decision**: 与 LangGraph 官方 Postgres saver 对齐，使用 `checkpoint_id DESC` 作为最新 checkpoint 的判定方式。  
**Consequences**: 恢复链路将依赖 LangGraph checkpoint id 的单调可排序特性；不额外引入兼容层或迁移逻辑，保持修复范围最小。
