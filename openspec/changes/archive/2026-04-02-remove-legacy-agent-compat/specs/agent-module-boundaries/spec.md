## ADDED Requirements

### Requirement: Retired Deep Research modules are not preserved as ownership shims
系统 MUST 在完成本次 hard cut 后删除已退役的 Deep Research 模块与边界 shim，而 MUST NOT 保留 `legacy` runtime 文件、outer `coordinator` 节点路径、历史命名节点模块或仅用于维持旧 monkeypatch 位置的包装层。

#### Scenario: Runtime assembly imports Deep Research owners
- **WHEN** 外层 graph、session 管理、测试或其他内部模块需要导入 Deep Research 运行时组件
- **THEN** 它们 MUST 指向当前 canonical owning modules
- **THEN** 系统 MUST NOT 再通过 `legacy`、`coordinator`、历史命名节点模块或其他退役 shim 间接装配运行时

#### Scenario: Internal callers no longer depend on retired patch paths
- **WHEN** tests、examples 或内部模块需要替换、patch 或验证 Deep Research 行为
- **THEN** 它们 MUST 依赖当前 owner 模块提供的 patch 点
- **THEN** 系统 MUST NOT 仅为保留历史 patch 路径而继续保留退役模块文件
