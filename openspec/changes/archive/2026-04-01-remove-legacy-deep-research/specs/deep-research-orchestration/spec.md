## MODIFIED Requirements

### Requirement: Deep Research engine selection
系统 MUST 将 Deep Research 固定到 `multi_agent` runtime，并移除 `legacy` engine、tree/linear 选择以及任何运行时回退分支。

#### Scenario: Deep research enters the only supported runtime
- **WHEN** 请求被路由到 `deep` 模式
- **THEN** 系统 MUST 直接启动 LangGraph 管理的 `multi_agent` Deep Research 子图
- **THEN** 系统 MUST 保持现有 Deep Research 入口、取消语义和最终报告输出契约稳定

#### Scenario: Obsolete legacy runtime inputs are rejected
- **WHEN** 调用方仍传入 `legacy` engine、`deepsearch_mode` 或其他旧 tree/linear 选择输入
- **THEN** 系统 MUST 不再路由到 legacy runtime，也 MUST NOT 静默回退到其他旧流程
- **THEN** 系统 MUST 以显式迁移错误或配置校验失败暴露该输入已废弃
