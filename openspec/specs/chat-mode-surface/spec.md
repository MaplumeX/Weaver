# chat-mode-surface Specification

## Purpose
TBD - created by archiving change hard-cut-chat-modes-to-agent-and-deep. Update Purpose after archive.
## Requirements
### Requirement: Public chat mode surface is limited to agent and deep
系统 MUST 将公开聊天模式限制为 `agent` 与 `deep` 两种规范值，并在前端界面、会话状态、API 负载和运行路由中使用同一组模式标识。

#### Scenario: User opens chat mode controls
- **WHEN** 用户打开主聊天页的模式标签、命令菜单或空状态快捷入口
- **THEN** 系统 MUST 只展示 `agent` 与 `deep` 两种模式
- **THEN** 系统 MUST NOT 再展示 `direct`、`web`、`mcp`、`ultra` 或其他历史模式别名

#### Scenario: Client serializes mode selection
- **WHEN** 前端发送聊天请求、保存会话快照或恢复当前模式
- **THEN** 系统 MUST 只序列化规范模式值 `agent` 或 `deep`
- **THEN** 客户端与服务端 MUST NOT 依赖 `ultra -> deep`、`mcp -> agent` 或空串 `-> direct` 之类的别名翻译

### Requirement: Agent mode is the default conversation mode
系统 MUST 将 `agent` 作为默认聊天模式，并且恢复路径只允许继续使用规范模式 `agent` 或 `deep`；系统 MUST NOT 再维护历史模式别名到规范模式的迁移表。

#### Scenario: User starts a new conversation
- **WHEN** 用户新建会话、清空当前会话或请求未显式指定模式
- **THEN** 系统 MUST 以 `agent` 作为默认模式
- **THEN** 系统 MUST NOT 再回到 `direct` 或无模式状态

#### Scenario: Restored session lacks a canonical mode
- **WHEN** 本地缓存、远端会话或恢复快照未携带规范模式 `agent` 或 `deep`
- **THEN** 系统 MUST 回到默认模式 `agent`
- **THEN** 系统 MUST NOT 将 `direct`、`web`、`mcp`、`ultra`、空串或其他历史别名解释为受支持模式

### Requirement: Removed chat modes are explicitly retired
系统 MUST 将 `direct`、`web` 和独立 `mcp` 模式视为已删除能力；外部调用若继续使用这些模式或历史字段，系统 MUST 显式拒绝，而不是静默兼容。

#### Scenario: External client sends a removed mode
- **WHEN** 外部 API 请求显式传入 `direct`、`web`、`mcp` 或其他已删除模式标识
- **THEN** 系统 MUST 返回显式校验错误
- **THEN** 错误信息 MUST 指示调用方改用 `agent` 或 `deep`

#### Scenario: External client sends legacy search_mode fields
- **WHEN** 外部 API 请求继续传入 `useWebSearch`、`useAgent`、`useDeepSearch` 或其他历史模式布尔字段
- **THEN** 系统 MUST 返回显式校验错误
- **THEN** 系统 MUST NOT 再根据这些字段推导 `direct`、`web`、`agent` 或 `deep` 的历史组合语义

