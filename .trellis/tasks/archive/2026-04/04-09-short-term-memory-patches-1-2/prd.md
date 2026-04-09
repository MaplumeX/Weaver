# Implement short-term memory patches 1 and 2

## Goal

为 chat 短期记忆系统补齐两块基础能力：

- Patch 1：为 `sessions` 持久层增加结构化 `context_snapshot`，用于保存滚动摘要和短期上下文快照。
- Patch 2：新增可复用的短期记忆组装器，用于从 session transcript 构建最近运行态消息和结构化上下文。

本次实现只打底层能力，不提前改 prompt 注入和主 chat 执行链路。

## Requirements

- 在 `sessions` 表上增加 `context_snapshot` 字段，并保持 DDL 幂等、兼容已有数据库。
- `SessionStore` / `SessionService` 能读写 `context_snapshot`，并保持现有 snapshot/session 行为兼容。
- 新增短期记忆组装器模块，负责：
  - 选取最近运行态消息窗口
  - 生成结构化短期记忆快照
  - 提取 pinned items、open questions、recent tools、recent sources
- 为增量摘要预留 `summarized_through_seq` 等字段，避免后续设计受限。
- 不修改现有 `build_chat_runtime_messages()` 和主 chat 请求链路的外部行为。
- 为新增持久层契约和组装器逻辑补充回归测试。

## Acceptance Criteria

- [ ] `SESSION_DDL_STATEMENTS` 为 `sessions` 表新增 `context_snapshot JSONB`，启动时可重复执行。
- [ ] `SessionStore.get_snapshot()` / `get_session()` 可返回 `context_snapshot`，`update_session_metadata()` 可更新该字段。
- [ ] `SessionStore` 提供按 `seq` 增量读取消息的能力，供滚动摘要后续使用。
- [ ] 新的短期记忆组装器可基于 session messages 生成：
  - 最近运行态消息
  - `rolling_summary`
  - `pinned_items`
  - `open_questions`
  - `recent_tools`
  - `recent_sources`
- [ ] `SessionService` 能基于当前 transcript 刷新 `context_snapshot`。
- [ ] 相关后端测试通过，且现有 session snapshot 行为无回归。

## Technical Notes

- 数据流范围：`session_messages` -> short-term context builder -> `sessions.context_snapshot`
- 本次不改 `AgentState` / prompt 注入；这些属于后续 Patch 3/4。
- `context_snapshot` 目标结构：

```json
{
  "version": 1,
  "summarized_through_seq": 0,
  "rolling_summary": "",
  "pinned_items": [],
  "open_questions": [],
  "recent_tools": [],
  "recent_sources": [],
  "updated_at": ""
}
```

- Good case：
  长会话写入后，`context_snapshot` 能保留结构化摘要，后续可直接给 runtime 组装器消费。
- Base case：
  短会话或空会话仍返回合法默认快照。
- Bad case：
  schema 已升级但 store/service 没有返回 `context_snapshot`，导致跨层字段丢失。
