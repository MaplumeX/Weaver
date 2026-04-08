# brainstorm: refactor deep research event stream display

## Goal

重构 Deep Research 在聊天消息里的事件流展示，把当前偏内部实现的技术指标改成面向用户的进度表达。目标是让用户一眼看懂“现在在做什么、是否已经开始正式 research、离完成还有多远”，而不是看到 phases / certified / iteration 这类流程内部概念。

## What I already know

* 当前折叠态头部文案由 `web/components/chat/message/ThinkingProcess.tsx` 调用 `web/lib/process-display.ts::buildProcessHeaderText()` 生成。
* Deep Research 的头部 metrics 来自 `web/lib/deep-research-timeline.ts::projectDeepResearchTimeline()` 的 `headerMetrics`。
* 当前 `headerMetrics` 固定拼接了 `phases / sections / certified / sources / latestIteration`，所以会出现“正在整理答案 · 95s · 5 phases · 3 sections · 3 certified · 18 sources · Iteration 2”这类字符串。
* `web/lib/process-display.ts::summarizeDeepResearch()` 当前只根据少量最新事件决定摘要 label，例如“正在检索资料”“正在整理答案”，但把 timeline 的全部 `headerMetrics` 原样暴露给用户。
* `web/lib/deep-research-timeline.ts` 会在 section / iteration / phase 三层都保留 `iteration` 语义；这是领域数据，不只是一个展示字符串。
* 代码里已有回归测试覆盖“research 尚未真正开始前不应显示 section / iteration metrics”这个场景：`web/tests/deep-research-timeline.test.ts`。
* 另有一套逐事件自动状态文案在 `web/hooks/useChatStream.ts::getDeepResearchAutoStatus()` 中维护，文案也带有较强内部术语色彩，例如 `supervisor`、`claim gate`、`章节认证`。

## Assumptions (temporary)

* 本次采用方案 B：重构前端显示投影层，引入“用户态进度模型”，不改后端 SSE 事件协议。
* 本次重点是统一“摘要头部 + 展开态细节 + 自动状态文案”三处的用户语义，不重做整个聊天 UI。
* 展开态采用“章节视图优先”，阶段信息退居辅助，不再作为默认主视角。
* `iteration` 仍可作为内部/调试信息存在，但不应在用户尚未进入正式章节 research 时提前曝光。
* 如果某些统计对用户没有直接决策价值，应下沉到展开态甚至完全移除，而不是继续堆在头部。

## Open Questions

* 对于尚未开始的章节，展开态是逐条列出，还是聚合成“还有 N 个待开始章节”？

## Requirements (evolving)

* 折叠态头部必须优先表达当前阶段和用户可理解的进度，而不是内部流程术语。
* 在正式章节 research 尚未开始前，不得显示 `Iteration` 或伪装成已开始章节执行的信号。
* 头部与展开态职责要清晰：
* 头部用于“一眼理解当前状态”
* 展开态用于“按章节查看当前状态与少量辅助阶段信息”
* header、details、auto status 必须从同一套前端用户态进度模型派生，不能继续各自独立猜测阶段。
* 用户态阶段应收敛为面向用户的稳定流程，例如：明确问题、确认范围、制定计划、检索资料、整理章节、复核结论、生成最终答案。
* 内部术语如 `phase`、`supervisor`、`certified`、`iteration`、`claim gate` 不应直接进入默认用户视图，除非被转译成用户能理解的表达。
* 需要保持现有 `ThinkingProcess` 两层展示模型，不引入新的复杂交互。
* 展开态主信息必须围绕章节组织，例如“检索中 / 整理中 / 待补充 / 已完成”，而不是围绕 phase 或内部 agent 角色组织。
* 为本次改动补充或更新前端单测，覆盖杂乱 header 压缩与 iteration 暴露时机。

## Acceptance Criteria (evolving)

* [ ] Deep Research 折叠态头部不再出现 `phases / certified / sources / Iteration N` 这类面向实现的堆叠指标，除非该指标被明确保留且对用户有实际价值。
* [ ] 在章节 research 仅处于规划/排队阶段时，UI 不显示 `Iteration`，也不把流程误导成已进入正式 research。
* [ ] 展开态仍能提供足够的过程信息，让用户理解范围确认、检索、汇总、审查等主要阶段。
* [ ] header、details、auto status 对同一事件序列给出一致的阶段语义，不再出现头部说“整理答案”、状态流却提前暴露内部调度轮次的情况。
* [ ] `web/tests` 中新增或更新回归测试，覆盖上述两类问题。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 修改后端 deep research 事件 schema
* 调整 LangGraph 编排或 research runtime 行为
* 完整重写聊天消息组件样式系统

## Technical Notes

* 相关文件：
* `web/lib/deep-research-timeline.ts`
* `web/lib/process-display.ts`
* `web/hooks/useChatStream.ts`
* `web/components/chat/message/ThinkingProcess.tsx`
* 相关测试：
* `web/tests/deep-research-timeline.test.ts`
* `web/tests/deep-research-events.test.ts`
* `web/tests/process-display.test.ts`
* 现有代码模式：
* 通用 process display 已经采用“简短摘要 + 少量 metrics + 展开态详情”的两层模型。
* Deep Research 目前的问题不是缺少信息，而是把内部 timeline projection 直接暴露给了用户。
* 本次需要新增一层前端投影，建议由 timeline/raw events 归一化成单一的 `UserFacingResearchProgress`，再供 header/details/auto status 复用。
