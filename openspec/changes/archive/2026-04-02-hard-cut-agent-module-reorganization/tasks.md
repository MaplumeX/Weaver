## 1. 建立目标目录与 ownership 边界

- [x] 1.1 创建 `agent/builders`、`agent/interaction`、`agent/research` 以及 Deep Research 需要的 role/orchestration/support 子目录，并定义对应的 `__init__` 公开面
- [x] 1.2 将 `agent.workflows.*` 中仍有真实 ownership 的 builder、interaction、research helper 移动到新目录，确保每个目录只承载单一职责
- [x] 1.3 为 Deep Research runtime 明确 role-owned、service-owned、artifact-owned、state-owned 模块边界，并拆出当前由大文件直接持有的辅助逻辑

## 2. 迁移 runtime 与 deep runtime 依赖

- [x] 2.1 更新 `agent.runtime.nodes.*` 导入，使其不再依赖 `agent.workflows.*` 或 `agent.compat.*`
- [x] 2.2 更新 `agent.runtime.deep.*` 与 multi-agent runtime 导入，使 domain/source/tool-agent builder/artifact helper 全部来自新的 owning modules
- [x] 2.3 拆分 oversized deep runtime orchestration 文件，把 agent 执行、dispatcher、artifacts、events、state helper 从主 graph/loop 文件中分离

## 3. 收口 facade、contracts 与 state

- [x] 3.1 更新 `agent.api`、`agent.__init__`、`agent.runtime.*` 的公开入口，移除对 `agent.workflows.*` 和 `agent.core.graph` shim 的依赖
- [x] 3.2 将 `deep_runtime` 嵌套结构设为唯一权威状态，迁移所有 `deepsearch_*` 顶层字段读写点
- [x] 3.3 校正 `agent.contracts.*`、shared helper 与 runtime helper 的依赖方向，确保不再通过历史路径或隐式 re-export 提供实现

## 4. 迁移内部调用方、示例与测试

- [x] 4.1 更新 `main.py`、`common/*`、`tools/*`、examples 中对旧路径的导入，改为 facade、contracts 或新的 owning modules
- [x] 4.2 更新测试中的 import 与 monkeypatch 目标，移除对 `agent.compat.nodes`、`agent.workflows.*` 和 `agent.core.graph` 旧 patch 点的依赖
- [x] 4.3 更新架构文档与模块边界文档，使文档描述与最终目录布局一致

## 5. 删除 legacy 路径并完成验证

- [x] 5.1 删除 `agent.compat/*`、`agent/workflows/*` 中仅承担 compat/聚合职责的文件，以及 `agent/core/graph.py` 等隐藏 shim
- [x] 5.2 运行受影响测试与必要的静态检查，验证 facade、contracts、runtime entrypoints 与 Deep Research 行为未发生回归
- [x] 5.3 清理遗留导入、无用 re-export 和过渡注释，确保仓库内不存在对旧 compat/workflow/shim 路径的残余依赖
