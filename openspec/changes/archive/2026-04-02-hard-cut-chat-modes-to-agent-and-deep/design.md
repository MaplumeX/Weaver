## Context

当前聊天模式在不同层面使用了多套不一致的表示方式：前端主聊天页实际使用 `'' | web | agent | ultra | mcp`，后端 `search_mode` 仍兼容字符串、布尔对象与历史别名，LangGraph 主图继续维护 `direct_answer`、`web_plan`、`agent`、`deepsearch` 四条公开分支，Deep Research 的简单问题降级还依赖 `direct_answer_node`。这导致产品只想保留 `agent/deep` 时，仍需要持续维护旧模式入口、别名翻译、死代码导出、测试 patch 点和文档说明。

这次变更是一次真正的 hard cut，而不是 UI 隐藏。约束包括：

- 删除 `direct`、`web`、独立 `mcp` 模式相关代码，而不是保留隐藏入口。
- 如果 `agent` 或 `deep` 仍依赖被删模式代码，必须先迁移到共享或正确 owning module，再删除旧实现。
- 默认模式改为 `agent`，显式 `deep` 保留。
- 外部 API 需要明确反映新契约；本地/远端已保存会话需要可恢复。
- OpenAPI、前端生成类型、SDK 类型、测试和文档必须一起收敛。

## Goals / Non-Goals

**Goals:**

- 将公开聊天模式收敛为 `agent` 与 `deep` 两种规范值，并在前端、API、会话状态和后端路由中统一。
- 让新建聊天、重置聊天和旧会话恢复都默认落到 `agent`，不再回到 `direct` 或其他历史别名。
- 删除 `direct_answer_node`、`web_search_plan_node` 以及对应图路由、导出、兼容分支和文档。
- 将 Deep Research 的简单请求降级切换到 `agent_node`，复用现有 agent fast path，而不是保留 direct 模式兜底。
- 让外部 API、OpenAPI 和生成类型显式拒绝已删除模式，避免继续保留历史输入形状。

**Non-Goals:**

- 不重写 Deep Research 的多 agent 内核、artifact 模型或事件协议，除非删除旧模式必须触碰这些边界。
- 不新增第三种产品模式，也不把 MCP 发展为新的独立执行路径；MCP 仅作为 agent 能力的一部分存在。
- 不改变现有模型供应商、工具审批策略或 Deep Research 最终报告格式，除非模式删除直接要求调整。

## Decisions

### 1. 规范模式词汇只保留 `agent` 和 `deep`

前端、后端、会话快照、OpenAPI 与测试统一使用 `agent` 和 `deep` 这两个规范值。`ultra`、`mcp`、`direct`、`web` 不再作为可存储、可恢复或可传输的模式标识保留。

选择原因：

- 先统一词汇，再删除代码，才能避免“模式删了但别名还在流动”的继续腐化。
- 前端当前 `ultra -> deep`、`mcp -> agent`、空串 `-> direct` 的多段映射是本次复杂度的重要来源。

备选方案：

- 保留前端别名、只在后端归一化。未选，因为会话恢复、测试与 UI 高亮仍会继续漂移。

### 2. `search_mode` 改为显式对象契约，而不是历史布尔组合

保留 OpenAPI 中“`search_mode` 是对象”的总体形态，但将其收敛为显式模式选择，而不是继续使用 `useWebSearch/useAgent/useDeepSearch` 这组三布尔字段。实现上应以一个明确模式字段表达 `agent|deep`，并拒绝历史布尔对象、字符串别名和已删除字段。

选择原因：

- 历史三布尔组合天然允许无效状态，也让删除 `web/direct` 后仍保留旧概念残影。
- 现有测试已经要求 `search_mode` 公开契约是对象而不是字符串；延续对象形态可以减少前端/SDK 契约震荡，但语义要显式收口。

备选方案：

- 继续使用布尔对象，只把非法组合映射到 `agent/deep`。未选，因为这会保留已删除模式的结构性残留。
- 直接改成字符串枚举。未选，因为当前 OpenAPI 契约和生成类型已经围绕对象工作，改成字符串会扩大无关改动面。

### 3. 新建聊天默认 `agent`，旧会话读取时迁移到 `agent`

`agent` 成为唯一默认模式。新建聊天、重置聊天、无模式请求都以 `agent` 运行。本地或远端已保存会话如果携带 `direct`、`web`、`mcp`、空模式或旧别名，读取时迁移为 `agent` 并以规范值重新保存。

选择原因：

- 用户明确要求“默认为 agent 模式”。
- 只改默认值但不迁移历史会话，会导致旧会话重新把已删除模式带回 UI 和会话缓存。

备选方案：

- 保持历史会话原值，仅对新会话默认 `agent`。未选，因为这会延长旧模式的生命周期。

### 4. 外部 API 对已删除模式显式报错，本地持久化做兼容迁移

对外部请求，已删除模式或旧字段不再静默接受，而是返回带迁移指引的 `400`。对仓库内会话快照、历史缓存和会话恢复路径，则执行读取时迁移到 `agent`。

选择原因：

- hard cut 的目标是完成契约收口；若对外继续隐式兼容，旧模式会永久留存。
- 本地用户数据属于我们可控持久化，迁移成本低，用户体验要求也更高。

备选方案：

- 对外部 API 也静默迁移到 `agent`。未选，因为客户端将无法感知自己的调用已经依赖废弃模式。

### 5. 删除 `direct_answer_node`，Deep 简单请求降级到 `agent_node`

`direct_answer_node` 以及 `direct` 公开路由整体删除。当前 Deep Research 对简单事实问题的 preflight 降级改为委托 `agent_node`，并要求保留 agent 现有 fast path，避免简单问题因进入完整 agent loop 而显著变慢。

选择原因：

- 用户已明确要求 `direct_answer_node` 可以删除，降级目标改为 `agent`。
- 保留 direct 兜底会让模式代码删除不彻底，并继续维持一条独立回答栈。

备选方案：

- 抽出共享 “fallback answer” 节点替代 `direct_answer_node`。未选，因为这只是 direct 模式逻辑换名保留。

### 6. LangGraph 主图只保留 `agent`、`deepsearch` 与内部 `clarify`

主图删除 `direct_answer` 和 `web_plan` 路径；`clarify` 仍可作为内部 guardrail，但不再是用户可选产品模式。Smart Router、主图条件边、运行指标与状态恢复只再承认 `agent` 与 `deep` 作为公开业务模式。

选择原因：

- 删除节点、导出和路由，才能真正完成删码。
- `clarify` 是内部控制流，不属于用户产品模式，不需要作为公开模式保留。

备选方案：

- 保留 `direct/web` 节点但不暴露 UI。未选，因为这与本次 hard cut 的删码约束冲突。

## Risks / Trade-offs

- [外部客户端会因旧模式输入失败] → 通过明确的 `400` 迁移错误、更新 OpenAPI 与生成类型，避免静默行为变化。
- [旧会话恢复后模式与界面状态不一致] → 在读取历史快照、远端会话状态和前端缓存时统一迁移并回写规范模式。
- [删除 direct 后简单 deep 请求变慢] → deep preflight 直接委托 `agent_node`，并保留 agent fast path 的回归测试。
- [删除 web 路径后共享搜索规划逻辑被误删] → 先梳理 `agent/deep` 是否仍复用相关 helper；复用的部分迁到 mode-agnostic helper，再删除 `web_search_plan_node` 外壳。
- [内部测试或导出路径继续引用已删除节点] → 删除 runtime 导出并同步迁移 monkeypatch 点、测试断言和文档图示，避免历史 patch surface 存活。

## Migration Plan

1. 先定义新的 `chat-mode-surface` 能力与相关 spec delta，明确只支持 `agent/deep` 的公开契约。
2. 收敛前端模式状态、空态入口、命令菜单、会话恢复和 i18n 文案，统一使用 `agent/deep`，默认 `agent`。
3. 收敛后端 `search_mode` 请求模型、校验、状态恢复和 OpenAPI 导出，拒绝旧输入并支持本地会话迁移。
4. 调整 Smart Router、LangGraph 主图与 runtime nodes：删除 `direct_answer_node`、`web_search_plan_node` 与对应路由，把 deep 简单请求降级迁到 `agent_node`。
5. 删除 runtime 导出、兼容别名、旧测试与旧文档说明；更新受影响的共享 helper 归属。
6. 重新生成 `web/lib/api-types.ts` 与 `sdk/typescript/src/openapi-types.ts`，并执行前后端相关测试。

回滚策略：

- 这是契约收口型 breaking change，不适合部分回滚。若发布后必须回退，应整体回退到变更前提交，同时恢复旧 OpenAPI 和生成类型。

## Open Questions

- 当前不保留开放问题；实现时若发现仍有第三方入口依赖历史 `search_mode` 布尔对象，再以追加任务或 follow-up issue 记录，而不在本次设计中继续保留兼容分支。
