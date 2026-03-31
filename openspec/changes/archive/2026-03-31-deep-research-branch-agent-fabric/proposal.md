## Why

当前 Deep Research 的 `multi_agent` 路径虽然已经具备显式 graph 节点与 checkpoint/resume 能力，但研究执行层仍然基本停留在“planner 产出 query，researcher worker 执行单次查询并摘要”的模式。随着研究任务复杂度上升，这个粒度已经不足以支撑真正的多步工具自治、分支级证据沉淀和更稳定的验证回路。

现在需要把并发执行单元从 `query worker` 升级为受 graph 控制的 `branch agent`。这样可以在不打碎现有 Deep Research 顶层角色面的前提下，让 researcher 成为真正的执行型 agent，同时把任务契约、artifact handoff、验证流程和事件模型收紧到 branch 级协作。

## What Changes

- 将 Deep Research 的 planner 输出从“查询列表”升级为“branch objective 列表”，使研究任务的最小调度单位从 query 提升为 branch。
- 将当前 `researcher` 执行路径升级为真正的 branch-scoped agent，允许在受控预算和工具边界内执行多步研究，而不是只做单次搜索与摘要。
- 为 branch agent 引入更细粒度的 artifact handoff，包括分支计划、来源候选、抓取文档、证据片段、分支结论和验证结果。
- 将 verifier 从单一 coverage/gap 检查扩展为显式的验证流水线，至少覆盖 claim/citation 检查与 coverage/gap 检查两个阶段。
- 收紧 Deep Research 的事件契约，使前端和调试工具能够观察 branch agent 的阶段推进、重试、验证回流和最终汇总。

## Capabilities

### New Capabilities
- `deep-research-branch-agent-execution`: 定义 branch-scoped researcher agent 的任务契约、允许的执行阶段、预算边界和向 graph 回流的结构化产物。

### Modified Capabilities
- `deep-research-agent-fabric`: 将 researcher 从 query worker 升级为 branch agent，并明确 planner、coordinator、researcher、verifier、reporter 的新协作拓扑。
- `deep-research-orchestration`: 将正式研究循环的控制语义从 query dispatch 调整为 branch objective dispatch、验证回流和 replan。
- `deep-research-artifacts`: 扩展 Deep Research artifacts，使其能承载 branch agent 的多步执行产物和验证结果。
- `deep-research-scope`: 收紧 graph scope、branch scope、worker scope 的所有权，使 branch 成为正式的一等执行边界。
- `deep-research-agent-events`: 扩展事件契约，使其能表达 branch agent 的生命周期、执行阶段、验证阶段和重试语义。

## Impact

- 影响 Deep Research multi-agent graph 与调度逻辑：`agent/runtime/deep/multi_agent/graph.py`、`agent/runtime/deep/multi_agent/dispatcher.py`
- 影响 Deep Research task / artifact / runtime snapshot schema：`agent/runtime/deep/multi_agent/schema.py`、`agent/runtime/deep/multi_agent/store.py`
- 影响 researcher、planner、verifier、reporter 的角色契约：`agent/workflows/agents/researcher.py`、`agent/workflows/agents/planner.py`、`agent/workflows/knowledge_gap.py`、`agent/workflows/claim_verifier.py`
- 影响通用 agent middleware 与受控工具自治接入点：`agent/workflows/agent_factory.py`
- 影响前端 Deep Research 过程展示与事件消费：`web/hooks/useChatStream.ts`
- 影响测试覆盖范围：branch dispatch、artifact merge、verification pipeline、事件关联与 checkpoint/resume
