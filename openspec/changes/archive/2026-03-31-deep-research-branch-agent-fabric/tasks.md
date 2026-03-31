## 1. Task Contract And Artifacts

- [x] 1.1 扩展 `agent/runtime/deep/multi_agent/schema.py` 中的 `ResearchTask` 契约，使其能表达 branch objective、task kind、acceptance criteria、allowed tools 和上游 artifact 引用
- [x] 1.2 为 branch execution / verification 新增或等价建模权威 artifacts，并更新 `ArtifactStore` 的 snapshot/restore 逻辑
- [x] 1.3 补齐 schema/store 的序列化与 checkpoint-safe 测试，确保 branch 级状态可恢复

## 2. Planning And Dispatch

- [x] 2.1 调整 `ResearchPlanner` 的输出契约，使 initial plan / replan 产出 branch objective 而不是 query list
- [x] 2.2 更新 `dispatcher` 和 task queue 逻辑，使调度单位从 query worker 切换为 branch-scoped researcher task
- [x] 2.3 强化 branch scope / branch brief 的构建与恢复逻辑，确保 dispatch、merge 和 resume 都以 `branch_id` 为正式边界

## 3. Researcher Branch Agent

- [x] 3.1 在 `agent/workflows/agent_factory.py` 或等价位置增加 Deep Research 专用的受限 tool-agent builder，复用共享 middleware 但限制工具集
- [x] 3.2 将 `researcher` 执行路径改造成 branch-scoped true agent loop 或 researcher subgraph，支持多步搜索、读取、抽取和综合
- [x] 3.3 让 researcher 只返回结构化 branch result bundle，并将预算统计改为按 branch agent 实际执行消耗计数

## 4. Verification And Reporting

- [x] 4.1 在 verifier 路径中加入 claim/citation 检查与 coverage/gap 检查的两阶段验证流水线
- [x] 4.2 更新 coordinator 决策逻辑，使其基于 branch 验证结果驱动 retry、replan、dispatch 或 report
- [x] 4.3 调整 reporter 输入契约，使最终报告只消费已验证的 branch synthesis 与可追溯证据

## 5. Events And Test Coverage

- [x] 5.1 扩展 Deep Research 事件负载，补充 `branch_id`、`task_kind`、`stage`、验证阶段等字段，同时保持现有事件家族兼容
- [x] 5.2 更新前端 Deep Research 过程展示逻辑，使其能渲染 branch agent 的执行阶段、验证回流与重试语义
- [x] 5.3 补齐端到端测试，覆盖 branch dispatch、artifact merge、verification pipeline、checkpoint/resume 和事件关联
