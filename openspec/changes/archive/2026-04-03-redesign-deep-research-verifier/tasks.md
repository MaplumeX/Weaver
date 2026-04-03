## 1. 拆分权威验证与辅助 gap planning

- [x] 1.1 重构 `agent/runtime/deep/services/knowledge_gap.py` 的角色边界，使其只产出 advisory planning hints 而不再充当权威 verifier gate
- [x] 1.2 调整 `agent/runtime/deep/orchestration/graph.py` 中 coverage 阶段的 fallback gap 接入方式，移除 heuristic gap 对 authoritative verification verdict 的覆盖或降格
- [x] 1.3 重构 `agent/runtime/deep/services/verification.py` 中 `build_gap_result()` 的语义，使其不再用 fallback gap 结果降低已满足 obligation 的 authoritative coverage

## 2. 收紧 coverage 与 revision issue 判定

- [x] 2.1 重构 `evaluate_obligations()`，让 obligation verdict 基于 grounded claims、evidence passages 和 completion criteria 的映射，而不是 summary/topic overlap
- [x] 2.2 调整 coverage 结果到 `RevisionIssue` 的映射规则，使 `partially_satisfied` 默认生成 non-blocking follow-up 而不是强制阻塞
- [x] 2.3 调整 verify 阶段的 `verification_summary`、`retry_task_ids` 和 supervisor 输入，只让 authoritative blocking debt 触发 revision loop

## 3. 修正 outline gate、missing evidence 与 verifier tool-agent 契约

- [x] 3.1 重构 `missing_evidence_list` 和 `outline.blocking_gaps` 的生成逻辑，确保它们只引用 authoritative unresolved debt，而不直接吸收 advisory `knowledge_gap`
- [x] 3.2 更新 `agent/runtime/deep/support/tool_agents.py` 与 verifier merge 逻辑，要求 verifier tool-agent 提交 claim/obligation/issue 级可追溯裁决
- [x] 3.3 调整 public artifacts 与质量事件输出，明确区分 blocking verification debt 和 advisory research gaps

## 4. 补齐回归测试

- [x] 4.1 更新 `tests/test_deepsearch_verification_services.py`，移除“fallback gaps 覆盖 contract pass”的旧语义并补充新的 service 断言
- [x] 4.2 更新 `tests/test_deepsearch_multi_agent_runtime.py`，覆盖 advisory gaps 不得单独阻断 report 的 runtime 行为
- [x] 4.3 为 verifier tool-agent 增加 contract-addressable 提交约束测试，防止 blanket `passed` 再次回归
