## Why

当前 Deep Research 虽然已经有 `multi_agent` runtime，但控制流仍然主要封装在单个 deep runtime 节点内部，尚未真正升级为由 LangChain/LangGraph 显式编排、可 checkpoint、可恢复、可解释的 multi-agent 系统。随着并行研究、长时任务恢复、agent 级观测和后续工具自治需求增加，这个边界已经开始限制架构演进速度。

## What Changes

- 将 Deep Research 的 `multi_agent` 执行路径升级为 LangGraph 管理的深度研究子图，而不是继续依赖单节点内部的黑盒循环。
- 为 planner、coordinator、researcher、verifier、reporter 建立显式的角色拓扑、输入输出契约和 graph-level 生命周期。
- 引入面向 Deep Research 的 scope 模型，明确 graph scope、branch scope、worker scope 的状态所有权与交接边界。
- 将 researcher 并发从 runtime 内部线程池迁移为 LangGraph fan-out/fan-in 调度，统一纳入 checkpoint、恢复和事件模型。
- 收紧 artifact、event 和 orchestration 契约，使其能够表达真正的 graph-native multi-agent 执行过程，同时保持现有 Deep Research 外部入口和最终输出兼容。

## Capabilities

### New Capabilities
- `deep-research-agent-fabric`: 定义 Deep Research 的 LangGraph 角色拓扑、节点职责边界和 graph-native fan-out/fan-in 协作契约。
- `deep-research-scope`: 定义 Deep Research 的 graph、branch、worker 三层 scope 及其状态所有权、交接与隔离规则。

### Modified Capabilities
- `deep-research-orchestration`: 将现有 multi-agent 编排要求收紧为 LangGraph 子图驱动的研究循环、分发和恢复语义。
- `deep-research-artifacts`: 将 artifacts 契约收紧为 checkpoint-safe、scope-aware、可序列化的 graph handoff 介质。
- `deep-research-agent-events`: 将 agent/task/decision 事件收紧为 graph-native 生命周期与关联标识语义。

## Impact

- 影响 Deep Research 图级入口与运行时装配：`agent/core/graph.py`、`agent/runtime/nodes/deepsearch.py`、`agent/runtime/deep/selector.py`
- 预计新增或调整 Deep Research graph/subgraph、state reducer、dispatch 和 checkpoint 相关模块
- 影响 multi-agent runtime 内部组件：`agent/runtime/deep/multi_agent/*`
- 影响 Deep Research 专有状态与 artifacts 的序列化、恢复和事件透传
- 影响测试覆盖范围：deep graph orchestration、checkpoint/resume、fan-out worker dispatch、artifact merge、事件关联与兼容性
