## Context

当前 Deep Research 仍处于“新 runtime + 旧兼容层”并存状态。`agent/runtime/nodes/deepsearch.py` 通过 `agent/runtime/deep/selector.py` 进入运行时，而 selector 仍依赖 `agent.workflows.deepsearch_optimized` 来决定 `legacy`、tree/linear 和 `multi_agent` 分支。与此同时，`multi_agent` graph 已经能够独立产出任务队列、artifact store、验证结果和最终报告，但 `common/session_manager.py` 仍以 legacy 风格的 `deepsearch_artifacts` 作为公开对象，前端状态映射也仍保留 `planner`/`coordinator` 旧语义。

这次 change 的约束很明确：不再为旧 Deep Research 流程保留兼容代码，只保留当前 `multi_agent` runtime；如果旧流程里有仍有价值的 helper 或公开字段，需要迁移到新的权威边界，而不是继续挂在 legacy 模块下。

## Goals / Non-Goals

**Goals:**
- 将 Deep Research 入口收敛为单一 `multi_agent` runtime，删除 selector 和 legacy runner 分支。
- 将对外公开的 artifacts、事件语义和导入路径迁移到 `multi_agent` 权威实现与显式 facade/shared contracts。
- 删除 `agent.workflows.deepsearch_*` compat facade，并迁移仍有复用价值的 helper。
- 清理 legacy-only 配置项，并为仍保留的 multi-agent 配置使用非 legacy 命名。

**Non-Goals:**
- 不重写 `multi_agent` graph 的研究策略、prompt 或 verifier 质量算法。
- 不改变 `direct`、`web`、普通 `agent` 模式的非 Deep Research 行为。
- 不保留“再兼容一个版本”的 legacy runtime 回退路径。

## Decisions

### 1. Deep Research 入口改为直接委托给唯一的 multi-agent runtime

`deepsearch_node` 将直接依赖 `agent.runtime.deep.multi_agent` 的公开入口，删除 `agent/runtime/deep/selector.py` 中的 engine 选择和对 legacy workflow 的转发。这样可以把“入口稳定”与“内部实现重组”保留下来，但移除已经没有产品价值的双 runtime 分支。

备选方案：
- 保留 selector，但把它简化成永远返回 `multi_agent`。放弃，因为这会保留一个只服务历史包袱的抽象层，继续掩盖真实依赖边界。
- 保留 legacy runtime 作为失败兜底。放弃，因为这会让测试、配置和故障路径继续绑在已废弃实现上。

### 2. 公开 artifacts 由 multi-agent artifact store 派生，runtime 快照与公开视图分离

`multi_agent` graph 继续保留完整的 `artifact_store`、task queue 和 runtime bookkeeping 作为权威内部快照；同时新增一个面向 session/API/UI 的公开 artifacts 适配层，把 `fetched_documents`、`evidence_passages`、`verification_results`、`final_report` 等结构 flatten 成当前调用方仍依赖的 `fetched_pages`、`passages`、`claims`、`sources`、`quality_summary`、`final_report` 等字段。

这样可以做到：
- 调用方继续消费稳定的公开对象，而不是被迫解析内部 store 结构。
- 实现侧不再依赖 legacy runner 风格的手工拼装或二次推导。

备选方案：
- 直接把嵌套 `artifact_store` 暴露给前端和 session。放弃，因为这会把 runtime 内部结构泄漏为公共契约。
- 继续让 `SessionManager` 通过 `scraped_content`/legacy verifier 回填 claims。放弃，因为 `multi_agent` 已经在验证产物中记录 claims，重复推导会制造双重事实源。

### 3. 复用价值保留，但必须迁移到显式 ownership

凡是旧流程中仍被当前功能使用的逻辑，例如复杂问题启发式、公开 research contract、共享 event helper，都必须迁移到 `agent.runtime.deep`、`agent.contracts` 或其他显式 shared 模块；`agent.workflows.deepsearch_*` 不再作为这些能力的长期宿主。

备选方案：
- 继续从 `agent.workflows.deepsearch_optimized` re-export helper。放弃，因为这会把已废弃流程继续伪装成公开依赖。

### 4. 流式事件和前端状态统一使用 runtime 实际角色语义

运行时已经发出 `supervisor`/`researcher`/`verifier`/`reporter` 角色事件，因此前端状态映射、SSE 测试和任何自动状态文案都必须基于这些角色和结构化 phase 字段工作，不再把 planning/orchestration 阶段映射为 `planner` 或 `coordinator`。

备选方案：
- 在服务端继续发 legacy 角色别名给前端。放弃，因为这会固化一套与真实 runtime 不一致的公共词汇。

### 5. 配置直接做 breaking cleanup，不保留旧字段别名

legacy-only 配置项如 `deepsearch_mode`、tree exploration 开关和 tree-only 深度/分支参数会被删除。仍被 `multi_agent` 使用但命名带 legacy/tree 语义的配置，会重命名为面向当前 runtime 的中性命名，并同步更新读取点和文档。

备选方案：
- 保留旧字段并在内部映射到新字段。放弃，因为这会继续留下需要维护的 legacy 解析逻辑，与本次收口目标相违背。

## Risks / Trade-offs

- [破坏旧配置与内部导入] → 通过 spec 和任务显式标记 BREAKING，实施时同步更新调用点、测试与迁移说明。
- [公开 artifacts 形态回归] → 为 session/API 层增加基于 `multi_agent` store 的契约测试，覆盖 `sources`、`claims`、`fetched_pages`、`passages` 和最终报告字段。
- [前端状态文案与实际事件脱节] → 用现有 SSE 测试和 web 事件测试对齐 `supervisor` 及恢复态 phase 语义。
- [删除 legacy 后缺少临时回退] → 在删除前先完成入口 reroute、核心 smoke tests 和 config/test 清理，保证唯一 runtime 路径可运行。

## Migration Plan

1. 先引入 `multi_agent` 公开 artifacts 适配层和稳定公开入口，替换 session/common/web 对旧 compat 模块的依赖。
2. 统一前端和测试的角色语义，确保 `supervisor` 成为唯一公开 planning/orchestration 角色。
3. 删除 selector、legacy runtime、`agent.workflows.deepsearch_*` compat facade，以及旧配置读取逻辑。
4. 清理失效测试和文档，补齐围绕公开 artifacts、事件和配置的回归测试。

回滚策略：该变更是明确的 breaking cleanup，不设计运行时级别的双轨回滚；如需回退，应整体回退本 change。

## Open Questions

- 公开 `deepsearch_artifacts` 最终需要保留哪些字段名才能满足现有 API/UI，而又不继续泄漏内部 store 结构。
- 仍存活的 `tree_parallel_branches`、`deepsearch_tree_max_searches` 最终应采用什么中性命名，以避免继续绑定到 tree/legacy 词汇。
