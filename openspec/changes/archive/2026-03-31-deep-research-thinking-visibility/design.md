## Context

当前 Deep Research 过程展示分为两条彼此没有完全对齐的链路：

- 初始请求走 `/api/chat`，后端通过 `stream_agent_events()` 把 LangGraph 事件、tool 事件和 Deep Research 结构化事件转成前端可消费的流。
- scope 审阅后的恢复走 `/api/interrupt/resume`，后端直接 `ainvoke(Command(resume=...))` 并返回 JSON，前端不会重新进入流式事件消费链路。

这导致两个具体问题：

- 启动阶段同时混用通用 `status/thinking` 文案和 `research_agent_* / research_decision / research_artifact_update` 等结构化事件，前端状态跳动、重复且容易互相覆盖。
- scope 草案审阅后，虽然 graph 会继续执行 planner、dispatch、verify、report 等阶段，但前端只拿到中断结果或最终文本，看不到恢复后的过程事件。

这次变更跨越后端流协议、Deep Research runtime 事件语义、前端中断恢复和过程 UI，因此需要在实现前把流式契约收敛清楚。

## Goals / Non-Goals

**Goals:**
- 让 scope 审阅后的批准或修订可以继续以流式方式展示后续 Deep Research 过程，而不是退化成一次性 JSON 结果。
- 让 multi-agent Deep Research 在启动阶段只暴露一套稳定的 phase-oriented 过程语义，减少重复和冲突文案。
- 让前端初始请求与恢复请求复用同一套事件消费逻辑、同一套过程 UI 结构。
- 为上述行为补齐后端和前端测试，覆盖 clarify、scope、scope_review、approve、revise、plan、report 等关键阶段。

**Non-Goals:**
- 不改变 legacy deep research engine 的行为。
- 不重写现有聊天主协议或引入新的独立 Deep Research API。
- 不在本次设计中重做 Thinking UI 的视觉风格，只收敛其数据来源、事件组织与连续性。
- 不引入新的事件家族；优先复用既有 `research_*`、`status`、`thinking` 契约。

## Decisions

### 1. `interrupt/resume` 扩展为可选流式恢复，默认 JSON 行为保持兼容

`/api/interrupt/resume` 将保留当前 JSON 默认行为，但新增显式的流式恢复模式。当前端请求流式恢复时，后端必须像初始 `/api/chat` 一样持续输出过程事件和最终结果。

这样做的原因：
- 兼容现有测试和调用方，不破坏当前默认 JSON 恢复语义。
- 避免额外引入新的专用 resume endpoint，减少认证、所有权校验和恢复载荷规范的重复定义。
- 能直接复用现有流协议和前端解析器。

备选方案：
- 新增单独的 `/api/interrupt/resume/sse`。
  - 未选原因：API 面扩大，且与现有 `/api/interrupt/resume` 的职责高度重叠。
- 保持 JSON 恢复，再让前端主动轮询状态。
  - 未选原因：无法恢复实时过程展示，仍然不能解决用户当前痛点。

### 2. 后端抽象统一的“新运行 / 恢复运行”流式执行器

后端将把当前 `stream_agent_events()` 背后的执行逻辑抽成统一入口，使其既能从初始 state 开始，也能从 `Command(resume=...)` 继续执行。事件规范化、tool 队列排空、interrupt 处理、sources/completion/done 发射必须走同一条代码路径。

这样做的原因：
- 避免为恢复路径复制一份流式事件桥接逻辑，降低分叉和回归风险。
- 可以保证恢复后的 event ordering、completion 行为和初始运行一致。
- 更容易让测试直接对齐“初始运行”和“恢复运行”的事件序列约束。

备选方案：
- 为恢复路径单独实现一个精简流式生成器。
  - 未选原因：很容易再次遗漏 thinking/status/tool/research 事件或结束态处理。

### 3. multi-agent Deep Research 启动阶段以结构化 `research_*` 事件作为主显示语义

对于 multi-agent Deep Research，前端启动阶段的主要状态文本和过程节点应由 `research_agent_start / complete`、`research_decision`、`research_artifact_update` 等结构化事件驱动。后端的通用 `status/thinking` 仅保留为 legacy 或非 deep 路径的兜底，不再与同一阶段的 multi-agent 事件重复表达相同含义。

这样做的原因：
- 结构化事件已经包含 role、phase、scope_version、attempt 等上下文，更适合作为单一真相来源。
- 可以减少“同一阶段被两套文案系统同时描述”的闪烁和覆盖问题。
- 与现有 `deep-research-agent-events` spec 更一致。

备选方案：
- 保留后端通用 `status/thinking`，在前端做更激进的去重。
  - 未选原因：前端无法稳定推断后端两套事件到底哪一个更权威，去重规则会越来越脆弱。

### 4. 前端恢复路径复用现有流消费器，并以“continuation message”承接恢复后的过程

前端将把 `processChat()` 中的流消费逻辑抽成可复用的内部执行器，`resumeInterrupt()` 调用同一执行器。对于 scope review，审阅消息本身保持只读草案展示；恢复后的 planner/research/report 过程由新的 continuation assistant message 承接，并继续写入 `processEvents`、`currentStatus`、`sources` 和最终内容。

这样做的原因：
- 保留 scope draft 审阅消息的语义清晰度，不把只读草案和后续研究输出混在一个气泡里。
- 前端实现简单，能最大限度复用现有消息生命周期和 ThinkingProcess 组件。
- 用户仍然能连续看到“审阅 -> 继续规划/研究 -> 最终报告”的完整过程。

备选方案：
- 直接在原 scope review message 上继续流式追加过程和最终答案。
  - 未选原因：会把审阅内容与正式研究输出混杂，弱化 checkpoint 语义。

### 5. ThinkingProcess 从“尾部事件浏览”升级为“保留阶段上下文的过程视图”

本次不强制重做视觉结构，但会调整事件组织策略，使 clarify、scope、scope_review、plan、research、verify、report 等阶段在恢复前后都能被稳定保留。最小要求是：恢复后新增事件不能被当作一条无上下文的新流程，启动阶段的早期 phase 也不能过早被尾部裁剪吞掉。

这样做的原因：
- 用户感知问题本质上是“过程链断了”而不是“缺一个文案”。
- 即使后端恢复流式，如果前端仍然只保留非常短的尾部窗口，用户仍会觉得启动阶段显示异常。

备选方案：
- 只修恢复流，不调整过程面板的数据保留策略。
  - 未选原因：会留下“刚开始显示有点问题”的已知缺陷。

## Risks / Trade-offs

- [同一接口同时支持 JSON 与流式恢复会增加分支复杂度] → 通过显式请求参数区分模式，并保持 JSON 默认值不变。
- [恢复后使用 continuation message 会让一次研究出现多条 assistant 消息] → 仅在 checkpoint 边界发生，并用一致的过程展示语义维持上下文连续。
- [移除或弱化通用 `status/thinking` 可能影响 legacy 或非 multi-agent 路径] → 将结构化事件优先级限制在 multi-agent Deep Research，其他路径维持现状。
- [过程面板保留更多 phase 信息可能导致事件噪声增加] → 在前端按 phase 聚合或去重，避免简单扩大尾部窗口。
- [恢复链路改成流式后测试面明显增大] → 先围绕 scope approve、scope revise、第二次审阅、最终完成四类路径建立最小回归测试集。

## Migration Plan

1. 扩展恢复请求模型和 `/api/interrupt/resume`，增加可选流式恢复模式，同时保留当前 JSON 默认行为。
2. 抽取统一的后端 graph 流桥接逻辑，支持初始执行与 `Command(resume=...)` 两种入口。
3. 调整 multi-agent Deep Research 启动阶段的显示语义，明确结构化 `research_*` 事件为主展示来源。
4. 前端抽取通用流消费器，让 `processChat()` 与 `resumeInterrupt()` 共享同一处理逻辑。
5. 调整 ThinkingProcess 的事件保留与展示策略，确保恢复前后 phase 上下文连续。
6. 补齐后端与前端测试，然后再做必要的文案微调。

## Open Questions

- continuation message 是否需要在 UI 上显式标记“继续研究中”，还是只通过 ThinkingProcess 和状态文案表达？
- 恢复流式模式是否只对 scope review 启用，还是对所有 interrupt checkpoint 统一开放？
- 对于已经依赖 JSON 恢复结果的调用方，是否需要在公共文档里明确推荐切换到流式恢复模式？
