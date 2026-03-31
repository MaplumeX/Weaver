## 1. Graph Skeleton

- [x] 1.1 为 `multi_agent` Deep Research 新建 LangGraph 子图入口，并从 `deepsearch` 入口接入 engine 选择后的 graph 执行路径
- [x] 1.2 将现有 runtime 主循环拆分为 graph 节点或子图阶段：bootstrap、plan、dispatch、merge、verify、coordinate、report、finalize
- [x] 1.3 保持 legacy engine 与现有 `deep` 外部入口、取消语义和最终输出契约兼容

## 2. Scope And State

- [x] 2.1 定义 Deep Research 专用 state schema，明确 graph scope、branch scope、worker scope 的字段边界
- [x] 2.2 将 `task_queue`、`artifact_store`、`runtime_state`、`agent_runs` 收敛为 checkpoint-safe 的序列化快照
- [x] 2.3 为现有 helper 提供基于快照的 facade 或 view，避免恢复逻辑依赖进程内对象身份

## 3. Agent Fabric

- [x] 3.1 将 planner、coordinator、verifier、reporter 接入显式 graph role 节点，并保持窄职责输入输出契约
- [x] 3.2 将 researcher 执行迁移为 graph-native fan-out/fan-in worker 路径，替代 runtime 内线程池分发
- [x] 3.3 实现 worker 返回 payload 到统一 merge 阶段的 artifact 合并、任务状态更新和预算计数

## 4. Events And Compatibility

- [x] 4.1 扩展 multi-agent 事件字段，补齐 graph run、branch、task、attempt 等关联信息
- [x] 4.2 更新 Deep Research 事件透传和前端消费逻辑，确保新增字段不破坏旧客户端兼容
- [x] 4.3 维持最终报告、基础事件和错误透传行为与现有 Deep Research 调用方兼容

## 5. Verification

- [x] 5.1 为 graph orchestration、checkpoint/resume、task retry 和 artifact merge 增加后端测试
- [x] 5.2 为 multi-agent 事件关联与前端 timeline 消费增加回归测试
- [x] 5.3 验证 legacy 与 `multi_agent` engine 共存场景，确保显式选择 `multi_agent` 时失败路径不会静默回退
