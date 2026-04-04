## Why

当前 Deep Research 运行时已经具备 branch-scoped `researcher` / `verifier` tool agent 和 graph fan-out/fan-in 能力，但控制平面仍主要由 graph 节点和普通 LLM role 驱动，缺少显式的 handoff 语义、活动控制者状态和可恢复的控制权移交契约。这让 runtime 在角色边界、恢复语义和与 LangChain 官方 multi-agent 模式的对齐上仍然不够彻底。

现在需要把 Deep Research 升级为真正的混合多智能体系统：让 `clarify`、`scope`、`supervisor` 成为 handoff 驱动的控制平面 agent，由 `supervisor` 统一拥有总调度权；同时保留并强化 `researcher`、`verifier`、`reporter` 的 subagent 执行路径，以获得更清晰的职责边界、更稳定的 checkpoint 恢复行为和更贴近官方模式的架构。

## What Changes

- 引入控制平面 handoff 模型，把 `clarify`、`scope`、`supervisor` 建模为显式可移交控制权的 control-plane agents。
- 让 `supervisor` 成为唯一的全局控制平面 owner，统一负责计划、派发、重试、replan、outline gate 回路和最终收敛。
- 保留 `researcher`、`verifier`、`reporter` 的 bounded tool-agent 执行能力，并将其明确收敛为由 `supervisor` 调用的 subagent 路径。
- 引入结构化 handoff payload、活动 agent 状态与 handoff 历史，使 checkpoint/resume 可以恢复“谁当前持有控制权”，而不只是恢复 `next_step`。
- 明确 handoff 与 coordination request 的边界：handoff 负责控制平面所有权转移，coordination request 负责 branch 级纠偏与结构化反馈。
- 调整 outline/report 阶段，使 `reporter` 默认以 subagent 角色工作，只有在 outline 准备完成且不存在阻塞缺口时才被 `supervisor` 调用。

## Capabilities

### New Capabilities
- `deep-research-control-plane-handoffs`: 定义 Deep Research 控制平面 agent 的 handoff 所有权、结构化 payload、恢复语义和 `active_agent` 状态契约。

### Modified Capabilities
- `deep-research-intake`: 调整 intake/scoping 阶段的控制权语义，使 `clarify` 与 `scope` 通过显式 handoff 交接，而不是仅以隐式 graph 步骤串联。
- `deep-research-agent-fabric`: 将角色拓扑正式收敛为 “handoff 控制平面 + subagent 执行平面”，并强化 `supervisor` 的总控制权边界。
- `deep-research-orchestration`: 修改 graph 编排与 checkpoint 恢复语义，使运行时恢复的是 handoff 控制者与结构化移交流，而不只是节点步骤。
- `deep-research-tool-agents`: 调整角色 agent/tool 暴露策略，明确 `clarify`、`scope`、`supervisor` 为 fabric-only handoff agents，`researcher`、`verifier`、`reporter` 为 supervisor 驱动的 subagents。

## Impact

- 受影响代码主要位于 `agent/runtime/deep/orchestration/graph.py`、`agent/runtime/deep/schema.py`、`agent/runtime/deep/support/tool_agents.py`、`agent/builders/agent_factory.py` 以及 `agent/runtime/deep/roles/` 下的控制平面角色实现。
- 会新增或扩展 Deep Research runtime state、artifact/public snapshot 和事件负载，以暴露 `active_agent`、handoff payload 与 handoff 历史。
- 会影响 interrupt/resume、scope review、outline gap 回路和 Deep Research UI/调试可观测性，但不应改变对外 mode 入口或放宽现有工具权限边界。
