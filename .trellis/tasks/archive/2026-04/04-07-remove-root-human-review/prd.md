# Remove root human review node

## Goal
将根 LangGraph 从 `finalize -> human_review -> END` 简化为常规的终态收口方式，移除根图上的人工 review 中间层。

## Requirements
- 根图不再注册或连接 `human_review` 节点。
- chat 路径由 `finalize` 直接完成收口并终止。
- deep research 路径直接终止，不再经过根图 `human_review`。
- 保持现有输出契约稳定，尤其是 `final_report`、`messages`、`is_complete`。
- 删除 `human_review_node` 模块及其运行时公共导出。
- 清理与 `human_review` 相关的死配置注入。

## Acceptance Criteria
- [ ] 根图节点集合中不再包含 `human_review`。
- [ ] `finalize_answer_node()` 返回 `is_complete=True`，可作为终态节点。
- [ ] deep research 完成后无需额外 review 节点即可结束执行。
- [ ] `agent.runtime` 与 `agent.runtime.nodes` 不再导出 `human_review_node`。
- [ ] 根图与输出契约相关测试更新并通过。

## Technical Notes
- 目标文件：
  - `agent/runtime/graph.py`
  - `agent/runtime/__init__.py`
  - `agent/runtime/nodes/__init__.py`
  - `agent/runtime/nodes/finalize.py`
  - `agent/runtime/nodes/review.py`
  - `common/config.py`
  - `main.py`
  - `tests/test_root_graph_contract.py`
  - `tests/test_agent_runtime_public_contracts.py`
  - `tests/test_output_contracts.py`
- 本次修改限定在根图收口，不触碰 deep runtime 内部的 `scope_review` 中断节点。
