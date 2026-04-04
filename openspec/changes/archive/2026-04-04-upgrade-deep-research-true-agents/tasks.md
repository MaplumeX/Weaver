## 1. Runtime State And Contracts

- [x] 1.1 在 `agent/runtime/deep/schema.py` 中新增 control-plane handoff 所需的数据契约与状态字段，包括 `active_agent`、handoff payload 和 handoff history
- [x] 1.2 更新 `agent/runtime/deep/support/graph_helpers.py` 与相关 snapshot/public artifact 构建逻辑，使新增 handoff 状态可序列化、恢复和对外暴露
- [x] 1.3 为新增 handoff 状态补充校验与默认值策略，确保与现有 `next_step` 兼容共存

## 2. Control-Plane Agents

- [x] 2.1 将 `clarify` 控制流升级为 handoff 驱动的 control-plane agent，并保留现有 intake 判断语义
- [x] 2.2 将 `scope` 控制流升级为 handoff 驱动的 control-plane agent，并让 scope review/approval 产出结构化 handoff
- [x] 2.3 将 `supervisor` 升级为唯一全局控制平面 owner，并收口所有进入 dispatch、replan、outline gate 与 report 的决策入口

## 3. Fabric Tools And Agent Factory

- [x] 3.1 在 Deep Research fabric tools 中增加 control-plane handoff 的读取与提交接口，并限制为 owner-only 调用
- [x] 3.2 调整 `agent/builders/agent_factory.py` 中的 Deep Research 角色工具暴露策略，区分 control-plane handoff agents 与 execution subagents
- [x] 3.3 更新 `agent/runtime/deep/support/tool_agents.py` 与相关会话对象，使控制平面 agent 和执行 agent 使用统一但受限的运行时封装

## 4. Orchestration And Execution Flow

- [x] 4.1 改造 `agent/runtime/deep/orchestration/graph.py` 的 intake/scoping/brief 路径，使其优先由 `active_agent` 与 handoff payload 驱动
- [x] 4.2 保持 `researcher`、`verifier`、`reporter` 为 `supervisor` 调用的 subagent 路径，并明确禁止 execution role 直接改写控制平面 owner
- [x] 4.3 调整 outline gate、report 和 revision 回路，使 execution feedback 通过 request/issue 返回，再由 `supervisor` 决定后续 handoff 或 dispatch
- [x] 4.4 更新 interrupt/resume 恢复逻辑，确保 checkpoint 后能恢复 control-plane owner、handoff 上下文和 branch 执行状态

## 5. Verification And Observability

- [x] 5.1 为 control-plane handoff、新增 owner 约束和 subagent 调度补充单元测试与集成测试
- [x] 5.2 为 scope review、interrupt/resume、outline gap 回退和 branch 并发执行补充回归测试，覆盖 handoff 与 subagent 混合路径
- [x] 5.3 更新 Deep Research 事件、public artifacts 或调试输出，确保外部可观察到当前 `active_agent` 与最近一次 handoff
