## 1. Backend Resume Streaming

- [x] 1.1 扩展 `GraphInterruptResumeRequest` 与 `/api/interrupt/resume`，在保持现有 JSON 默认行为的前提下支持显式流式恢复
- [x] 1.2 抽取统一的后端执行桥接逻辑，使初始请求与 `Command(resume=...)` 共用同一套事件流、completion 和 done 发射路径
- [x] 1.3 确保 scope review 批准或修订后的恢复执行能够继续输出 planner、research、verify、report 阶段的过程事件

## 2. Deep Research Event Semantics

- [x] 2.1 调整 multi-agent Deep Research 启动阶段的事件语义，明确 `research_*` 结构化事件为前端主展示来源
- [x] 2.2 收敛或降级与 multi-agent 启动阶段重复的通用 `status/thinking` 发射，避免 clarify、scope、plan 阶段重复表达
- [x] 2.3 补齐恢复后事件的关联字段和顺序约束，确保前端能把恢复后的事件识别为同一研究流程的继续阶段

## 3. Frontend Process Continuity

- [x] 3.1 抽取 `useChatStream` 的共享流消费器，让 `processChat()` 与 `resumeInterrupt()` 复用同一套事件解析和消息更新逻辑
- [x] 3.2 为 scope review 恢复实现 continuation message 流程，使批准或修订后继续显示 thinking/process，而不是只追加最终 JSON 结果
- [x] 3.3 优化 Deep Research 启动阶段和恢复阶段的状态映射与 `ThinkingProcess` 事件保留策略，确保 phase 上下文连续可见

## 4. Verification

- [x] 4.1 为后端补充 resume streaming 测试，覆盖 approve_scope、revise_scope、再次 interrupt 和最终完成路径
- [x] 4.2 为 Deep Research 事件语义补充测试，覆盖启动阶段结构化 phase 显示和恢复后事件关联
- [x] 4.3 为前端补充流消费与 interrupt 恢复测试，验证 continuation message、processEvents 连续性和状态文案映射
