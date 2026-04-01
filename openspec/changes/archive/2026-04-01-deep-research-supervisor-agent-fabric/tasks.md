## 1. Fabric Contracts

- [x] 1.1 定义 `supervisor`、`researcher`、`verifier`、`reporter` 的角色枚举、运行时快照字段和配置开关
- [x] 1.2 为 blackboard request/result bundle 扩展 schema、artifact store 和 task queue 契约
- [x] 1.3 实现 Deep Research fabric tools，并为不同角色建立工具白名单与策略限制

## 2. Control Plane

- [x] 2.1 在 multi-agent graph 中引入 `supervisor` 计划/决策节点，替代公开的 planner/coordinator 控制回路
- [x] 2.2 保持 `clarify`、`scope`、`scope_review` 前置门控，并把批准后的 scope handoff 到 `supervisor`
- [x] 2.3 持久化 `supervisor` 的计划、dispatch、replan 和 stop 决策到 runtime snapshot 与 artifacts

## 3. Execution Agents

- [x] 3.1 将 branch `researcher` 重构为真正的 bounded tool-agent runner，并让其返回结构化 result bundle
- [x] 3.2 将 `verifier` 升级为可执行 challenge/search/read/compare 的 tool agent，并返回结构化 verification bundle
- [x] 3.3 将 `reporter` 改为只消费已验证 artifacts 的报告 agent，并补齐必要的格式化或导出工具接入

## 4. Merge And Events

- [x] 4.1 更新 graph merge/reduce 阶段，使其消费 agent submissions、follow-up requests 和 verification bundles
- [x] 4.2 更新 Deep Research 事件模型，暴露 `supervisor` 与 tool-agent 生命周期、阶段推进和 blackboard 提交
- [x] 4.3 调整前端或流式消费映射，确保 clarify/scope/supervisor/research/verify/report 阶段都可观察

## 5. Verification And Rollout

- [x] 5.1 补齐 clarify/scope gate、supervisor dispatch、tool allowlist 和 budget enforcement 的单元测试
- [x] 5.2 补齐 branch execution、verification follow-up、merge、resume/retry 的集成测试
- [x] 5.3 更新运行文档与 rollout 指南，明确新 `multi_agent` 架构与回滚路径
