## Why

当前 Deep Research 的过程展示在两个关键阶段存在断裂。启动阶段同时混用了通用 `status/thinking` 文案和 multi-agent 结构化事件，导致思考过程跳动、重复且语义不稳定；scope 草案进入审阅后，`interrupt/resume` 只恢复执行结果，不恢复流式过程事件，导致用户在批准或修订草案后看不到后续 planner、research、report 阶段的持续过程展示。

这个问题已经开始影响 Deep Research 的可理解性和可控性。既有 specs 已经要求事件流具备 resume-safe 语义，但当前实现只保证“能恢复执行”，没有保证“恢复后仍能连续呈现过程”，因此需要把显示契约补齐。

## What Changes

- 为 Deep Research 的 interrupt 恢复路径补齐流式过程展示契约，使 scope 审阅后的批准或修订可以继续产出可消费的过程事件，而不是只返回最终 JSON 结果。
- 收敛启动阶段的过程展示语义，避免同一阶段同时被通用 `status/thinking` 与 multi-agent 事件重复表达，确保前端能稳定映射 clarify、scope、plan、research、verify、report 等阶段。
- 明确前端在 Deep Research 过程中需要保留连续的 phase-oriented 过程视图，而不是只展示中断前尾部事件或在恢复后开启一条无上下文的新流程。
- 为上述行为补齐后端流协议、前端消费链路和测试覆盖，确保 scope review 前后、修订重写、批准后正式研究三段体验连续一致。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deep-research-agent-events`: 调整 Deep Research 事件流契约，使启动阶段的过程事件语义稳定，且 checkpoint 恢复后仍能连续产出并消费过程事件。
- `deep-research-orchestration`: 调整 multi-agent Deep Research 的恢复行为，要求 scope review 后继续执行时保留同一研究流程的可视化进度，而不是退化为一次性结果返回。
- `deep-research-intake`: 调整 scope 审阅后的用户体验契约，要求 scope 草案批准或修订后，后续 planner 与正式研究阶段的进展对用户持续可见。

## Impact

- 后端流式入口与恢复接口：`main.py`
- multi-agent Deep Research runtime 事件与 scope review 恢复链路：`agent/runtime/deep/multi_agent/graph.py`、`agent/runtime/deep/multi_agent/events.py`
- 前端聊天流消费与 interrupt 恢复：`web/hooks/useChatStream.ts`、`web/lib/interrupt-review.ts`
- 过程展示组件：`web/components/chat/message/ThinkingProcess.tsx`、相关消息组件
- 测试：Deep Research SSE、interrupt/resume、multi-agent runtime、前端事件映射测试
