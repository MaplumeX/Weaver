## 1. 迁移共享入口与公开契约

- [x] 1.1 提取仍被当前 Deep Research 使用的 legacy helper 或 contract 到显式 shared/runtime 模块，并替换 `agent.workflows.deepsearch_*` 相关导入
- [x] 1.2 为 `multi_agent` runtime 增加稳定公开入口，替换 `deepsearch_node` 与其他调用点对 selector / compat facade 的依赖
- [x] 1.3 实现从 `multi_agent` task queue、artifact store 和验证结果生成公开 `deepsearch_artifacts` 的适配层

## 2. 收口 runtime 与配置

- [x] 2.1 将 Deep Research 入口改为只启动 `multi_agent` runtime，并为旧 engine / mode 输入提供显式迁移失败
- [x] 2.2 删除 selector、legacy deep runtime 模块和 `agent.workflows.deepsearch_*` compat facade，清理遗留导出
- [x] 2.3 删除 legacy-only 配置项并重命名仍由 `multi_agent` 使用的 deep research 配置，更新所有读取点

## 3. 对齐事件、前端与外部消费方

- [x] 3.1 更新 session/common/API 消费逻辑，使其读取新的公开 artifacts 适配层而不是 legacy 拼装结果
- [x] 3.2 统一前端 Deep Research 状态映射到 `supervisor` / `researcher` / `verifier` / `reporter` 语义，移除 `planner` / `coordinator` 旧映射
- [x] 3.3 更新 backend SSE、web 事件和相关单元测试，使其断言单一路径 multi-agent runtime 与新的公开事件/artifacts 契约

## 4. 验证与清理

- [x] 4.1 补充或更新围绕公开 `deepsearch_artifacts`、配置校验和 runtime 入口收口的回归测试
- [x] 4.2 运行 Deep Research 相关后端与前端测试，修复因 legacy 删除产生的回归
- [x] 4.3 更新与 Deep Research 配置、导入入口和流式角色语义相关的文档或迁移说明
