## 1. Remove public compatibility surface

- [x] 1.1 删除后端旧聊天模式迁移与旧 `search_mode` 兼容辅助，收缩 `mode_info` 到 canonical 字段
- [x] 1.2 删除前端 history / snapshot / session route 的历史模式归一化逻辑，并统一恢复时的默认模式行为
- [x] 1.3 删除废弃的 facade 导出与旧 prompt shim，更新 repo 内部 imports、examples 和 monkeypatch 位置

## 2. Remove retired Deep Research runtime paths

- [x] 2.1 删除 legacy Deep Research runtime 实现文件与其调用链
- [x] 2.2 删除 outer hierarchical / `coordinator` Deep Research 分支，并将剩余决策逻辑收敛到 `supervisor`
- [x] 2.3 删除与 retired runtime 绑定的配置项、状态字段和测试 patch 点

## 3. Rename canonical Deep Research namespace

- [x] 3.1 将 runtime 节点、入口函数、checkpoint 名称从 `deepsearch_*` 迁移到 canonical `deep_research_*`
- [x] 3.2 将公开 artifacts、resume 载荷、event 名称中的 `deepsearch_artifacts`、`research_tree`、`research_tree_update` 等旧名迁移到 canonical 命名
- [x] 3.3 将配置键、文档引用和运行时日志中的 `deepsearch_*` 前缀统一迁移到 canonical Deep Research 命名

## 4. Simplify artifact and resume contracts

- [x] 4.1 重写 `SessionManager` 的公开 artifact 提取逻辑，只依赖权威 runtime snapshot 与 canonical public artifacts
- [x] 4.2 删除 resume 时对旧顶层 state 与旧 artifact key 的回填兼容
- [x] 4.3 更新 API 响应、前端 consumers 与 interrupt review 解析逻辑，使其只消费 canonical artifact / checkpoint 名称

## 5. Align tests, docs, and generated surfaces

- [x] 5.1 更新后端与前端测试，使其不再断言旧模式、旧导出、旧 checkpoint 或旧 `deepsearch_*` 命名
- [x] 5.2 更新文档、OpenSpec 引用、示例和说明文本，明确本次 hard cut 的 breaking behavior
- [ ] 5.3 重新生成并校验受影响的类型/契约输出，运行聚焦验证覆盖 facade、session/resume、Deep Research 事件和 artifacts
