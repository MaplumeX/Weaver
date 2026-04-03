## 1. Brief And Artifact Contracts

- [x] 1.1 为 `research brief`、`task ledger`、`progress ledger`、`coverage matrix`、`contradiction registry`、`missing evidence list` 和更新后的 `coordination request` 扩展 Deep Research schema 与 artifact store
- [x] 1.2 更新公共 artifacts 导出与 runtime snapshot，使新增 artifacts 在 checkpoint/resume 和对外视图中可序列化、可恢复
- [x] 1.3 为收敛后的 request type 建立权威枚举与校验，明确仅允许 `retry_branch`、`need_counterevidence`、`contradiction_found`、`outline_gap`、`blocked_by_tooling`

## 2. Intake And Supervisor Control Plane

- [x] 2.1 在 scope approval 之后新增 `research brief` 生成阶段，并把 `supervisor` 的正式规划输入切换为权威 brief
- [x] 2.2 在 `supervisor` 计划、dispatch、replan、report、stop 路径中接入 `task ledger` 与 `progress ledger` 的读取和更新
- [x] 2.3 调整 `supervisor` 决策逻辑，使其优先消费 brief、ledger 和结构化验证 artifacts，而不是仅依赖计数器与自由文本摘要

## 3. Outline Gate

- [x] 3.1 在 Deep Research graph 中插入 `outline gate`，把它放在 `verify` 与最终 `report` 之间
- [x] 3.2 实现 outline artifact 生成与持久化，并要求 `reporter` 只在 outline 就绪时进入最终成文
- [x] 3.3 当 outline 发现结构缺口时，通过 `outline_gap` request 把控制权交回 `supervisor`

## 4. Verification And Coordination Loop

- [x] 4.1 将 verifier 输出升级为 `coverage matrix`、`contradiction registry` 和 `missing evidence list`
- [x] 4.2 更新 fabric/tool-agent 提交协议，使 `researcher`、`verifier` 和报告准备阶段只能提交注册过的 request type
- [x] 4.3 更新 merge/reduce 逻辑，确保新增验证 artifacts、outline artifacts 和 request 在 graph 边界被确定性合并

## 5. Tests And Documentation

- [x] 5.1 补齐 intake->brief handoff、ledger 持久化、outline gate 和 request taxonomy 的单元测试
- [x] 5.2 补齐 checkpoint/resume、supervisor replan、outline_gap 回路和最终报告 gating 的集成测试
- [x] 5.3 更新 Deep Research 架构文档与实施说明，明确新增阶段、artifact 契约和不包含 `needs_human_decision` 的 request 约束
