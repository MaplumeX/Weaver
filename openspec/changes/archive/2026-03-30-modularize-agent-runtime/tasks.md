## 1. 边界与公开入口脚手架

- [x] 1.1 为 `agent/` 建立新的 runtime/shared contracts 目录边界，并补充必要的 `__init__.py` 与兼容 re-export
- [x] 1.2 为 facade、shared contracts 和内部实现定义公开/私有访问规则，并在代码中收敛现有公开入口
- [x] 1.3 为模块边界补充最小回归检查，确保新目录结构下现有 `agent` facade 仍可导入

## 2. Graph Nodes 拆分

- [x] 2.1 将 `agent/workflows/nodes.py` 按职责拆分为 route、answer、planning/review、deepsearch 等节点模块
- [x] 2.2 更新 `agent/core/graph.py` 与相关导出入口，使其从新节点模块装配 graph 而不是依赖单一大文件
- [x] 2.3 清理节点拆分后遗留的循环依赖和内部 helper 泄漏，保持节点模块可以独立测试

## 3. Deep Runtime 模块化

- [x] 3.1 从现有 deep runtime 实现中抽离独立的 runtime selector，分离 engine 选择与执行细节
- [x] 3.2 拆分 legacy deep runtime，把 query strategy、tree/linear orchestration、质量回环和共享 helper 分离到独立模块
- [x] 3.3 拆分 multi-agent runtime，把 artifact schema、task queue、artifact store、dispatcher、event helper 和 runtime entrypoint 分离

## 4. 共享概念与状态收敛

- [x] 4.1 重命名并收敛重复的 `ContextManager` 概念，明确区分上下文窗口管理与 worker context 管理
- [x] 4.2 统一 `SearchCache` 的权威实现，移除或降级重复实现为显式 adapter
- [x] 4.3 收敛 `AgentState` 中 deep runtime 私有字段，引入嵌套且 mode-scoped 的运行时状态块并保留过渡兼容读取

## 5. 外围依赖迁移

- [x] 5.1 将 `main.py` 对 `agent` 内部实现的直接依赖迁移到 facade 或显式公开入口
- [x] 5.2 将 `common/*` 对 `agent.workflows.*` 内部模块的直接依赖迁移到 facade 或 shared contracts
- [x] 5.3 将 `tools/*` 对事件、registry、cache 等内部实现位置的依赖迁移到显式公开契约

## 6. 验证与清理

- [x] 6.1 为 runtime selector、节点拆分、状态兼容和 shared contracts 导入路径补充回归测试
- [x] 6.2 删除迁移完成后不再需要的兼容层、重复类型和过时导出
- [x] 6.3 更新架构与开发文档，说明新的 agent 模块组织、依赖方向和公开入口
