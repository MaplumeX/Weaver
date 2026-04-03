## MODIFIED Requirements

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
