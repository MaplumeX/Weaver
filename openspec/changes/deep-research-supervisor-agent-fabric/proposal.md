## Why

当前 Deep Research 已经具备 LangGraph 子图、任务队列和 artifact store，但正式研究仍由脚本化 researcher worker 驱动，离真正的 tool-agent 系统还有明显差距。现在推进这次变更，是因为 `clarify/scope` 前置门控、受限 tool-agent middleware 和结构化 artifacts 三块基础都已具备，可以把 Deep Research 升级成更清晰、更可扩展的执行架构。

## What Changes

- 保留 `clarify` 与 `scope` 作为正式前置阶段，并把它们收敛为窄职责 fabric agents。
- 引入 `supervisor agent` 作为 Deep Research 的唯一控制平面角色，统一负责计划、调度、重试、replan、停止与汇总推进。
- 将 `researcher`、`verifier`、`reporter` 升级为真正的 bounded tool agents，并为不同角色定义独立工具白名单与预算策略。
- 引入 blackboard/fabric 协作模型，通过结构化任务、artifact、result bundle 和 follow-up request 协调 agent，而不是依赖隐式共享上下文。
- 将当前脚本化 branch execution 重构为 graph 管理下的 tool-agent loop，同时保留现有入口、checkpoint、resume 和最终报告契约。

## Capabilities

### New Capabilities

- `deep-research-tool-agents`: 定义 clarify、scope、supervisor、researcher、verifier、reporter 的 tool-agent 契约、角色工具表面与 fabric tools。

### Modified Capabilities

- `deep-research-agent-fabric`: 角色拓扑从 planner/coordinator 中心化运行时升级为 clarify/scope + supervisor + execution agents 的 fabric。
- `deep-research-branch-agent-execution`: branch 执行从脚本化 worker 流程升级为受控的 researcher tool-agent loop。
- `deep-research-orchestration`: 编排循环从 coordinator 驱动升级为 supervisor 驱动，并保留 graph 级预算、并发、checkpoint 和 merge。
- `deep-research-intake`: clarify/scope 前置门控改为向 supervisor 提供批准后的范围契约，而不是交给 planner/coordinator 对。
- `deep-research-scope`: scope 边界从 graph/branch/worker 扩展为 graph/branch/agent，并通过 blackboard handoff 暴露给 tool agents。
- `deep-research-artifacts`: artifact 契约扩展为 blackboard 风格的 request、submission、verification 和 report handoff。
- `deep-research-agent-events`: 事件模型扩展为 supervisor 与 tool-agent 生命周期、阶段推进和 blackboard 提交可观测。

## Impact

- 影响模块：`agent/runtime/deep/multi_agent/`、`agent/workflows/agent_factory.py`、`agent/workflows/agents/`、`agent/core/context.py`、`agent/core/events.py`
- 影响契约：Deep Research runtime snapshot、artifact store、task queue、agent event payload、resume/retry 语义
- 兼容性：保留 `deep` 入口、`legacy` engine 和最终报告输出；`multi_agent` 内部角色与事件语义会调整
- 依赖：复用现有 LangGraph 子图、工具中间件、受限工具注册与 HITL/limit/retry 机制
