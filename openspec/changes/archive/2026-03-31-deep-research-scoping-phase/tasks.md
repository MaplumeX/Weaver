## 1. Deep Runtime Intake Flow

- [x] 1.1 为 multi-agent deep runtime 增加 intake/scoping graph state 与 runtime_state 字段，显式区分当前 scope、已批准 scope、修订计数和反馈历史
- [x] 1.2 在 deep runtime 子图中新增 `clarify`、`scope`、`scope_review` 节点，并把 `plan` 的前置条件改为存在已批准 scope
- [x] 1.3 调整 planner 输入契约，使其基于已批准 scope draft 而不是原始 topic 生成研究任务

## 2. Clarify / Scope Review Contract

- [x] 2.1 实现 Deep Research 专属 `clarify agent`，在信息不足时生成补充问题，在信息充分时输出可进入 scope 的 intake 摘要
- [x] 2.2 实现 `scope agent`，生成结构化 scope draft，并在收到 `scope_feedback` 后基于上一版草案重写新版本
- [x] 2.3 为 `scope_review` 增加专用 interrupt/resume payload，支持 `approve_scope` 与 `revise_scope`，并显式拒绝直接字段编辑作为权威输入

## 3. Events And Frontend Review UI

- [x] 3.1 扩展 Deep Research 事件发射，补齐 clarify/scope 角色生命周期、scope draft 进度和 scope 审阅决策事件
- [x] 3.2 扩展流式状态映射，使前端能把 intake/scoping 阶段显示为可理解的自动状态与过程事件
- [x] 3.3 将前端 interrupt 面板从“工具审批”抽象为通用 review UI，并为 scope 审阅场景提供只读草案展示、反馈输入和批准动作

## 4. Verification

- [x] 4.1 为 multi-agent runtime 增加 intake/scoping 状态机测试，覆盖初始草案、修订重写、批准后进入 planner 和 checkpoint 恢复
- [x] 4.2 为 interrupt/resume API 增加 scope review payload 测试，覆盖 `approve_scope`、`revise_scope` 和非法直接编辑输入
- [x] 4.3 为 SSE/前端流式消费增加事件与 UI 测试，覆盖 clarify/scope 进度可见性和恢复后事件关联
