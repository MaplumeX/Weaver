## Why

当前 Deep Research 已经具备 `supervisor + branch dispatch + verify + report` 的正确骨架，但正式研究协议仍然偏轻：`scope` 到计划的 handoff 过于隐式、`supervisor` 的决策状态不够结构化、验证信号过于粗粒度、最终报告前缺少统一的 outline 整理阶段。继续在现状上堆功能，会让调度、验证和汇总越来越难以解释、测试和重构，因此需要先重构 research 协议本身。

## What Changes

- 在 `scope` 审批之后引入结构化 `research brief`，作为 `supervisor` 进入正式规划前的唯一机器契约。
- 为 `supervisor` 引入 `task ledger` 与 `progress ledger` 两类控制平面 artifacts，用于表达 branch 目标、coverage target、未决请求、失败原因和重规划依据。
- 在 `verify` 与最终 `report` 之间插入 `outline gate`，要求系统先基于已验证 branch synthesis 生成统一的报告大纲，再进入最终汇总。
- 将验证输出从单一 coverage/gap 判断升级为 `coverage matrix`、`contradiction registry` 和 `missing evidence list` 等结构化验证 artifacts。
- 标准化 Deep Research 的 `coordination request` 类型，仅允许 `retry_branch`、`need_counterevidence`、`contradiction_found`、`outline_gap`、`blocked_by_tooling` 进入控制回路。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deep-research-intake`: 已批准 scope 不再直接作为 supervisor 的临时输入，而是必须先转换为结构化 `research brief`。
- `deep-research-orchestration`: 正式研究编排改为 `scope approval -> research brief -> supervisor -> verify -> outline gate -> report` 的协议驱动循环。
- `deep-research-agent-fabric`: agent fabric 需要表达 `research brief` handoff、ledger 驱动决策和 outline gate 前后的角色协作边界。
- `deep-research-artifacts`: artifact contract 需要扩展 `research brief`、supervisor ledgers、coverage matrix、contradiction registry、missing evidence list 和收敛后的 coordination request 类型。
- `deep-research-tool-agents`: bounded tool-agent 协作协议需要消费新的 request 类型与验证 artifacts，并遵守新的 outline gate handoff。

## Impact

- 影响模块：`agent/runtime/deep/orchestration/*`、`agent/runtime/deep/roles/*`、`agent/runtime/deep/services/*`、`agent/runtime/deep/artifacts/*`、`agent/runtime/deep/store.py`
- 影响契约：scope handoff、supervisor 决策输入、verification payload、coordination request schema、最终报告前的报告大纲阶段
- API 影响：外部 `deep` 入口保持不变，但 Deep Research 的内部阶段语义、artifact 形态和可观察事件会扩展
- 依赖：复用现有 LangGraph 子图、artifact store、task queue、bounded tool agents 和 checkpoint/resume 机制
