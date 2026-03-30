## 1. Runtime 入口与契约

- [x] 1.1 为 Deep Research 增加 `deepsearch_engine=legacy|multi_agent` 配置，并把选择逻辑接入 `deepsearch_node`
- [x] 1.2 新建 multi-agent runtime 模块与基础入口，定义 coordinator、planner、researcher、verifier、reporter 的职责边界
- [x] 1.3 扩展 `AgentState` 与相关运行时状态，补充 task queue、artifact store、agent run 跟踪所需字段

## 2. Artifact 与任务模型

- [x] 2.1 定义 `ResearchTask`、`EvidenceCard`、`KnowledgeGap`、`ReportSectionDraft` 等结构化 artifact schema
- [x] 2.2 实现 task queue 与 artifact store 的创建、更新、完成和查询接口
- [x] 2.3 将现有 context fork/merge 逻辑收敛为 researcher worker 可用的隔离上下文接口

## 3. Multi-Agent 编排闭环

- [x] 3.1 接入 coordinator 循环，使其能够初始化计划、决定 replan、触发汇总并终止研究
- [x] 3.2 将 planner 输出改为结构化任务产物，并写入任务队列
- [x] 3.3 实现 researcher worker 并发领取任务、预算检查、结果回写和状态流转
- [x] 3.4 实现 verifier 基于 evidence/gap 产物执行覆盖度判断，并把结果回传 coordinator
- [x] 3.5 实现 reporter 基于 artifact store 生成最终报告、引用信息和最终输出摘要
- [x] 3.6 为 multi-agent runtime 增加不可恢复错误检测与 legacy runner 安全回退路径

## 4. 事件流与前端展示

- [x] 4.1 在 `agent/core/events.py` 中新增 agent、task、decision、artifact 级事件类型
- [x] 4.2 在 `main.py` 的流式转发链路中透传新增事件，并保持既有 SSE/legacy 输出兼容
- [x] 4.3 更新前端 stream hook 与过程展示组件，按任务和 agent 渲染 multi-agent Deep Research 进度

## 5. 验证与文档

- [x] 5.1 为 engine selection、fallback、task dispatch、artifact merge 和 coordinator loop 补充后端测试
- [x] 5.2 为新增事件流和前端消费补充集成测试或关键交互测试
- [x] 5.3 更新 Deep Research 相关文档，说明 multi-agent engine 开关、回退语义和调试入口
