## MODIFIED Requirements

### Requirement: Deep Research engine selection
系统 MUST 将需要真正深入研究的 `deep` 请求固定到 `multi_agent` runtime，并在进入 runtime 前允许执行一次显式 preflight 判断；若该判断认定请求属于简单问题，则系统 MUST 将其转交 `agent` 模式处理，而 MUST NOT 路由到 `direct`、`web` 或任何 legacy engine/tree-linear 分支。

#### Scenario: Deep research enters the only supported runtime
- **WHEN** 请求被路由到 `deep` 模式且 preflight 判断该请求需要真实的深度研究
- **THEN** 系统 MUST 直接启动 LangGraph 管理的 `multi_agent` Deep Research 子图
- **THEN** 系统 MUST 保持现有 Deep Research 入口、取消语义和最终报告输出契约稳定

#### Scenario: Simple deep request is downgraded to agent
- **WHEN** 请求被路由到 `deep` 模式且 preflight 判断该请求可由简单路径满足
- **THEN** 系统 MUST 将该请求转交 `agent` 执行路径处理
- **THEN** 系统 MUST NOT 调用 `direct_answer_node`、`web` 专用路径或任何 legacy deep runtime

#### Scenario: Obsolete legacy runtime inputs are rejected
- **WHEN** 调用方仍传入 `legacy` engine、`deepsearch_mode` 或其他旧 tree/linear 选择输入
- **THEN** 系统 MUST 不再路由到 legacy runtime，也 MUST NOT 静默回退到其他旧流程
- **THEN** 系统 MUST 以显式迁移错误或配置校验失败暴露该输入已废弃
