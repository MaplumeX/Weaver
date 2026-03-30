## Why

当前 Weaver 的 Deep Research 默认执行路径仍然是单个 `deepsearch_node` 包裹 tree/linear runner，而不是一个真正的 multi-agent 研究内核。随着复杂研究任务、并行分支、质量回环和可视化要求持续增加，现有“单 runner + 大 state”模式已经开始限制扩展性、可解释性和后续演进速度。

## What Changes

- 引入一个可切换的 Deep Research multi-agent runtime，由 coordinator 统一驱动 planner、researcher、verifier、reporter 等专业 agent 协作完成研究任务。
- 将 Deep Research 内部的任务拆分、证据产物、知识缺口和阶段性报告草稿抽象成结构化 artifacts，替代当前松散附着在共享 state 中的隐式数据流。
- 为并行 researcher agent 建立明确的任务队列、上下文隔离、预算控制、失败回退和结果汇总机制。
- 扩展 Deep Research 流式事件语义，让前端能够感知 agent 级别的启动、领取任务、产出结果、回环决策和最终汇总，而不只看到搜索和 tree 更新。
- 保留 legacy deepsearch runner，并通过配置开关允许在 legacy 与 multi-agent runtime 之间切换，降低迁移风险。

## Capabilities

### New Capabilities

- `deep-research-orchestration`: 定义 Deep Research 在 multi-agent runtime 下的编排、任务分配、回环和回退行为。
- `deep-research-artifacts`: 定义 Deep Research 运行过程中共享的结构化研究 artifacts、证据汇总和上下文隔离契约。
- `deep-research-agent-events`: 定义 Deep Research multi-agent 运行时对外发出的流式事件语义和前端可消费状态。

### Modified Capabilities

- 无

## Impact

- 影响后端研究编排与执行路径：`agent/core/graph.py`、`agent/core/state.py`、`agent/core/context.py`、`agent/workflows/nodes.py`、`agent/workflows/deepsearch_optimized.py`、`agent/workflows/research_tree.py`
- 预计新增 multi-agent runtime、任务/artifact schema 与 orchestration 相关模块
- 影响流式事件转发与前端过程展示：`agent/core/events.py`、`main.py`、`web/hooks/useChatStream.ts`、相关 thinking/timeline 组件
- 影响测试覆盖范围：deepsearch mode selection、质量回环、事件流、并行 branch/agent 调度与回退策略
