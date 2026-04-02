## 1. Public API And Compatibility Foundation

- [x] 1.1 盘点仓库内对 `agent.workflows.*`、旧 deep runtime 路径和重复 facade 入口的直接导入，并为每类导入定义替代入口。
- [x] 1.2 引入显式 compat 模块或等价临时 shim，承接仍需保留的旧导入路径，并禁止新增对 workflow internals 的依赖。
- [x] 1.3 收敛 `agent`、`agent.api` 和 `agent.contracts` 的公开导出，明确受支持入口与内部实现目录的边界。

## 2. Runtime Ownership Migration

- [x] 2.1 将 Deep Research runtime-owned roles 从 `agent.workflows.agents.*` 迁移到 `agent.runtime.deep.*` 下的明确位置，并更新内部导入。
- [x] 2.2 将 verifier、gap analysis、artifact/source helper、result aggregation 等 runtime-owned services 从 `agent.workflows.*` 迁移到 runtime 或 shared contract 模块。
- [x] 2.3 拆分 `agent.runtime.deep.multi_agent.graph` 中混合的 loop、role coordination、service orchestration 和 event helper 责任，同时保持公开 runtime 入口稳定。

## 3. Core, Contracts And State Cleanup

- [x] 3.1 将 graph 装配从 `agent.core.graph` 迁移到 runtime-owned 模块，并通过 facade 保持外部调用方式稳定。
- [x] 3.2 清理 `agent.contracts.*` 对 workflow internals 的反向依赖，使 contracts 只指向共享定义、稳定 wrapper 或 runtime-owned schema。
- [x] 3.3 将新增或重构的 deep-only 运行时数据统一收敛到嵌套 `deep_runtime` 状态块，并限制历史顶层字段只作兼容用途。

## 4. Callsite Migration And Cleanup

- [x] 4.1 更新 `agent/` 包内部以及 `common/*`、`tools/*`、`web/*`、测试代码中的导入路径，迁移到 facade、contracts 或新的 runtime 入口。
- [x] 4.2 删除已无调用方的 workflow compatibility re-export 和过期 shim，确保 `agent.workflows.*` 不再承载 Deep Research runtime 的长期兼容层。
- [x] 4.3 运行覆盖 facade、runtime entrypoints 和 Deep Research 主路径的针对性验证，确认重组后行为语义保持不变。
