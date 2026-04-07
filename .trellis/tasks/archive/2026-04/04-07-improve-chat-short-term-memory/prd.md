# Improve chat short-term memory pipeline

## Goal

修复当前 chat 短期记忆链路职责分裂的问题，让多轮会话的运行态上下文、会话转录和长期记忆注入保持一致，并删除未接入主链路的 `ContextWindowManager`。

## Requirements

- 统一 chat 短期记忆的真源，避免 session store 与 checkpoint runtime state 各自维护不一致的历史。
- 在新一轮 chat 请求进入图执行前，将最近的会话历史回填到 runtime `messages`，保证模型能看到真实多轮上下文。
- 为 runtime `messages` 提供可控的裁剪与可选摘要策略，避免上下文无限增长。
- 删除未接入主链路的 `ContextWindowManager` 及其无效导出/引用。
- 保持现有 session snapshot、resume、share、长期记忆注入接口不出现行为回归。

## Acceptance Criteria

- [ ] 同一 `thread_id` 的 follow-up chat 请求会把最近用户/助手消息带入 runtime `messages`。
- [ ] session snapshot / share / runtime state 的消息来源和行为更加一致，不再依赖不完整的运行态历史。
- [ ] 现有 `trim_messages` / `summary_messages` 配置在主链路上真正生效，且行为有测试覆盖。
- [ ] `ContextWindowManager` 被删除，仓库内不再保留无效实现或悬空导出。
- [ ] 相关后端回归测试通过。

## Technical Notes

- 范围限定为 chat/runtime/session/memory 相关后端代码。
- 不调整 Deep Research 的 artifact、checkpoint、resume 外部契约。
- 优先复用现有 `AgentState.messages` 聚合器与 `summarize_messages()`，避免引入第二套上下文管理实现。
