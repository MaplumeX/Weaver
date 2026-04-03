## Why

当前 Deep Research 的 `Thinking` 面板仍然以“保留部分原始事件后按时间平铺”为主。在分支数量增加、事件粒度变细、进入多轮迭代后，同一件事会被 `research_agent_*`、`research_task_update`、`task_update`、`research_artifact_update`、`research_decision` 等多类事件重复表达，用户看到的是拥挤的调试日志，而不是可理解的研究过程。

现有事件模型已经具备 role、branch、stage、validation、resume 等结构化语义，但前端没有把这些低层事件投影成更高层的阶段、分支和轮次视图。随着 multi-agent Deep Research 已成为正式公开能力，这个显示问题已经直接影响可读性、可控性和用户对研究进度的判断，因此需要把展示契约和支撑字段一起补齐。

## What Changes

- 新增一个面向前端展示的 Deep Research `thinking timeline` 能力，要求客户端将原始事件归一化为“阶段摘要 + 分支卡片 + 原始事件下钻”，而不是直接平铺原始事件。
- 明确 `Thinking` 头部和默认视图应展示用户可理解的聚合指标，例如阶段数、分支数、来源数、当前轮次和关键状态，而不是原始事件步数。
- 要求 Deep Research 默认视图按 `intake / scope / planning / branch research / verify / report` 等稳定阶段组织内容，并在研究阶段按 `branch` 聚组，而不是暴露大量内部 `task_id / node_id / branch_id` 调试字段。
- 要求前端对重复或低价值事件做去噪与合并，例如 Deep Research 场景下的通用 `task_update`、连续 `search`、低信息量 topology 事件和重复状态文案。
- 调整 Deep Research 事件契约，确保前端能够稳定把任务、产物、决策和 agent 生命周期映射到同一轮次、同一分支和同一阶段；对于正式迭代循环中的 branch 任务与 artifact 更新，事件必须具备稳定的 `iteration` 归属语义。
- 为上述行为补齐前端事件投影、后端事件字段和测试覆盖，确保多轮次、多分支、重试和恢复后的显示仍然连续且可读。

## Capabilities

### New Capabilities

- `deep-research-thinking-timeline`: 定义 Deep Research 在聊天界面中的 thinking timeline 投影规则，包括阶段摘要、分支聚组、多轮次展示、去噪与原始事件下钻。

### Modified Capabilities

- `deep-research-agent-events`: 调整 Deep Research 事件契约，要求前端消费侧无需猜测时间窗口即可稳定识别轮次、分支和阶段归属，并避免同一语义被多套公开事件重复表达。

## Impact

- 前端事件消费与保留策略：`web/hooks/useChatStream.ts`、`web/lib/chat-stream-state.ts`
- 前端 thinking 过程面板：`web/components/chat/message/ThinkingProcess.tsx`、`web/components/chat/MessageItem.tsx`
- 后端 Deep Research 事件发射与流桥接：`agent/runtime/deep/orchestration/events.py`、`agent/runtime/deep/orchestration/graph.py`、`main.py`
- 测试：`web/tests/deep-research-events.test.ts`、Deep Research SSE/runtime 相关测试
