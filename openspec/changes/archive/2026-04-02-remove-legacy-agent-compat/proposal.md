## Why

当前仓库虽然已经把公开聊天模式收敛到 `agent` 与 `deep`，但内部仍保留旧模式迁移、旧 Deep Research runtime、旧导出和大量 `deepsearch_*` 过渡命名。这些兼容层让 `agent` 模块继续暴露多套历史语义，增加了状态恢复、测试维护和模块边界治理的复杂度，也阻碍了后续继续演进当前的 canonical runtime surface。

## What Changes

- 删除后端会话与前端缓存中的历史聊天模式迁移逻辑，只保留规范模式 `agent` / `deep`。**BREAKING**
- 删除旧 Deep Research runtime 实现、旧 facade 导出与 re-export、旧 `direct answer` / `web` / `coordinator` 兼容残留，并将调用方迁移到当前权威入口。**BREAKING**
- 将当前主路径上仍保留的 `deepsearch_*` 旧命名统一迁移到新的 canonical Deep Research 命名，包括节点、artifacts、checkpoint、配置键、事件与测试基线。**BREAKING**
- 收缩内部模式与 runtime 配置载荷，移除 `use_web`、`use_agent`、`use_deep_prompt`、`deepsearch_engine` 等过渡字段，只保留当前实现真正需要的 canonical 字段。**BREAKING**
- 删除旧 fallback artifact 拼装与旧 session/resume 兼容逻辑，要求恢复路径只依赖当前权威 runtime store 和新命名契约。**BREAKING**

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-mode-surface`: 停止对历史模式别名和旧缓存 route 做自动迁移，要求恢复后的会话与请求只使用 `agent` / `deep`
- `agent-public-api-surface`: 删除废弃的 Deep Research 公开导出、兼容 re-export 和历史 patch 点，只保留当前 canonical facade surface
- `deep-research-orchestration`: 删除 legacy runtime、hierarchical/coordinator 兼容路径，并将当前 runtime 的节点、checkpoint 与入口命名收敛到单一 canonical Deep Research 语义
- `deep-research-artifacts`: 用当前权威 runtime store 与新命名 artifacts 替代 `deepsearch_artifacts` 及其 legacy fallback 拼装逻辑
- `deep-research-agent-events`: 将 Deep Research 事件、checkpoint 和进度语义从 `deepsearch_*` / `research_tree_update` 等旧名迁移到新的 canonical 事件契约，不保留别名
- `agent-module-boundaries`: 删除剩余 compat/shim 风格边界与旧命名节点，使 `agent.runtime.*` 与 facade surface 只暴露当前权威实现

## Impact

- 影响代码范围：
  - `main.py`
  - `agent/__init__.py`
  - `agent/api.py`
  - `agent/runtime/graph.py`
  - `agent/runtime/nodes/*`
  - `agent/runtime/deep/*`
  - `agent/core/state.py`
  - `common/session_manager.py`
  - `web/lib/chat-mode.ts`
  - `web/lib/session-utils.ts`
  - `web/hooks/useChatHistory.ts`
  - 相关测试、文档、生成类型与示例
- 影响接口与契约：
  - Python facade imports
  - session / resume payload shape
  - Deep Research event and checkpoint names
  - Deep Research artifact field names
  - frontend local cache compatibility
- 外部影响：
  - 依赖旧导出、旧 route 别名、旧 checkpoint 名或旧 artifact key 的调用方需要同步迁移
