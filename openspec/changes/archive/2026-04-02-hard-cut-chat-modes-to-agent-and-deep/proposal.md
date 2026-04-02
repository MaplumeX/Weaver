## Why

当前聊天产品面同时保留了 `direct`、`web`、`agent`、`deep` 以及 `mcp` 这组历史模式别名，导致前端入口、会话恢复、后端 `search_mode` 契约、LangGraph 路由和测试文档之间长期存在语义漂移。现在已经明确要把产品面收敛为“默认 `agent` + 显式 `deep`”两种模式，因此需要一次 hard cut，把旧模式相关代码和兼容分支一起删除，而不是继续保留只隐藏入口的历史外壳。

## What Changes

- **BREAKING** 删除 `direct`、`web` 和独立 `mcp` 作为公开聊天模式；前端、API、会话状态和文档只保留 `agent` 与 `deep`。
- **BREAKING** 将默认聊天模式改为 `agent`；旧会话或旧入口中出现的 `direct`/`web`/`mcp` 模式在读取时迁移到 `agent`，外部 API 继续传这些模式时显式报错。
- 删除 `direct_answer_node`、`web_search_plan_node` 及其路由、导出、测试和文档；如果 `agent`/`deep` 仍依赖旧模式代码，则先迁移到 mode-agnostic 或新 owning module，再删除旧模式实现。
- 将 Deep Research 的简单问题降级路径从 `direct_answer_node` 改为 `agent_node`，复用现有 agent fast path，而不是保留 direct 模式兜底。
- 更新 OpenAPI、前端/SDK 生成类型、测试与文档，使“只支持 `agent`/`deep`”成为统一契约。

## Capabilities

### New Capabilities
- `chat-mode-surface`: 定义公开聊天模式只支持 `agent` 与 `deep`，并覆盖默认模式、旧模式迁移、API 校验、前端入口与会话恢复契约。

### Modified Capabilities
- `deep-research-orchestration`: 调整 deep 入口前置守卫与降级语义，使简单 deep 请求降级到 `agent`，并移除对 direct/web 历史模式的外围编排假设。
- `deep-research-scope`: 更新非 deep 模式隔离要求，使 Deep Research 专有状态只需保证不污染 `agent` 模式，而不再为已删除的 `direct`/`web` 保留契约。
- `deep-runtime-modularization`: 更新 deep runtime 与非 deep 模式边界定义，移除 direct/web 兼容表述，并确保删掉旧模式节点后剩余共享逻辑归属清晰。

## Impact

- 受影响前端：`web/components/chat/*`、`web/hooks/*`、`web/lib/session-utils.ts`、i18n 文案、前端模式恢复与空状态入口。
- 受影响后端：`main.py` 的 `SearchMode` 契约与会话恢复、`agent/core/smart_router.py`、`agent/runtime/graph.py`、`agent/runtime/nodes/*`。
- 受影响 API/契约：`/api/chat`、`/api/research/sse`、`/api/interrupt/resume` 的 `search_mode` 输入、OpenAPI 导出、`web/lib/api-types.ts`、`sdk/typescript/src/openapi-types.ts`。
- 受影响质量面：模式相关测试、会话恢复测试、deep 降级测试、文档与 README 中的模式说明都需要同步更新。
