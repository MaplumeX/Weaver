## Context

当前 Deep Research 的 thinking 展示链路大致是：

- 后端通过 `main.py` 把 `research_*`、`quality_update`、`search`、`task_update`、`tool_*` 等事件流式发给前端。
- 前端在 `useChatStream.ts` 中把这些事件原样追加到 `message.processEvents`。
- `chat-stream-state.ts` 只做少量相邻去重和“anchor + tail”裁剪。
- `ThinkingProcess.tsx` 直接把保留后的事件按时间顺序平铺成列表，并用原始事件数量作为 `steps` 统计。

这个方案在普通 agent/tool 流程里还能工作，但在 multi-agent Deep Research 下有三个结构性问题：

- 同一语义会被多类事件重复表达，例如 `research_task_update` 与通用 `task_update` 会同时出现。
- 展示单元停留在“原始事件”，没有提升到“阶段 / 分支 / 轮次”这样的用户级语义。
- 多轮次研究虽然已有部分 `iteration / epoch` 信息，但任务和 artifact 的轮次归属并不总是稳定显式，前端只能依赖时间顺序猜测。

这次变更跨越后端事件契约、前端事件保留策略和 thinking 面板投影逻辑，属于典型的跨模块显示协议收敛问题，适合先明确设计再实现。

## Goals / Non-Goals

**Goals:**
- 让 Deep Research 的 thinking 面板默认展示“阶段摘要 + 分支聚组 + 轮次进展”，而不是原始事件日志。
- 让前端仍然保留原始 `processEvents`，但把它们降级为二级下钻信息，而非主视图。
- 让 Deep Research 事件在正式研究循环中具备稳定的轮次归属，避免前端靠时间窗口猜测任务和 artifact 属于哪一轮。
- 让重复或低价值的公开事件不会在 thinking 默认视图里形成第二条顶层步骤。
- 为多分支、多轮次、重试和恢复场景补齐测试，确保 timeline 连续且可读。

**Non-Goals:**
- 不重做整个聊天界面的视觉风格，只调整 thinking 面板的数据组织与信息层级。
- 不改变最终答案主气泡或 citation 展示方式。
- 不重构 Deep Research 的研究编排逻辑，只补齐显示所需的事件字段和前端投影层。
- 不引入新的流协议或独立的 thinking API，继续沿用现有 SSE / data stream 契约。

## Decisions

### 1. 引入独立的 Deep Research timeline 投影层，而不是在组件里直接消费原始事件

前端将保留 `message.processEvents` 作为原始事实源，但新增一个专用的 timeline projection 层，把 Deep Research 事件投影成更高层的显示模型，例如：

- `header summary`
- `phase summary`
- `branch summary`
- `raw event drilldown`

这样做的原因：
- 把“事件采集”与“事件展示”解耦，避免 `ThinkingProcess.tsx` 持续膨胀成大量条件分支。
- 可以单独测试事件归一化、去重、聚组和统计逻辑。
- 原始事件仍然可用于调试、兼容旧逻辑和未来扩展。

备选方案：
- 继续在 `ThinkingProcess.tsx` 内部直接做事件筛选与 UI 渲染。
  - 未选原因：复杂度会继续向组件堆积，难以测试，也不利于多轮次/多分支逻辑演进。

### 2. 默认视图按稳定 phase 组织，研究阶段再按 branch 聚组

Deep Research timeline 默认视图将使用一组稳定 phase buckets：

- `intake`
- `scope`
- `planning`
- `branch_research`
- `verify`
- `report`

其中 `branch_research` 内部再按 `branch_id` 聚组，并展示该分支的最新状态、来源数、文档数、证据数、验证状态等摘要。默认视图不直接暴露 `task_id / node_id / branch_id` 等内部标识；只有在展开分支详情或 raw events 时才显示。

这样做的原因：
- 这组 phase 已经与现有 Deep Research runtime 角色和用户心智对齐。
- 研究阶段最容易爆炸的维度是 branch，而不是 event type；先按 branch 聚组才能真正降低噪音。
- 用户关心“这个分支现在做到哪了”，而不是“第几个事件类型是什么”。

备选方案：
- 完全按 event type 分组。
  - 未选原因：仍然会把一个 branch 的搜索、artifact、验证分散在多个区块里，用户难以形成连续理解。
- 完全按时间轴分组。
  - 未选原因：多 branch 并发时会再次退化成调试日志。

### 3. Thinking header 改为聚合指标，而不是原始 step 数

`Thinking` 头部将基于投影层输出聚合指标，例如：

- 已识别 phase 数
- branch 数
- 来源数或文档数
- 当前 iteration
- 当前全局状态

默认不再把原始 `processEvents` 数量作为主指标；原始事件数只允许出现在 raw drilldown 或调试信息中。

这样做的原因：
- 原始事件数在 Deep Research 场景下与用户感知的“步骤数”严重失真。
- 聚合指标更接近用户真正想知道的进度面。

备选方案：
- 保留 step count，同时额外显示阶段数。
  - 未选原因：step count 会持续制造噪音，并弱化更有意义的指标。

### 4. Deep Research 默认视图优先使用 canonical structured events，并主动去噪 companion events

前端 timeline projection 将把 `research_*` 结构化事件视为 canonical display source。对于 Deep Research 场景中的以下低价值或重复事件，默认视图将降级或抑制：

- 通用 `task_update`
- 与同一阶段结构化事件重复表达的 `status`
- 无额外摘要信息的 `deep_research_topology_update`
- 连续且只改变查询文本的 `search`
- 只提供中间细节、但不会改变分支摘要状态的局部 progress 行

原始事件仍保留在 drilldown 中。

这样做的原因：
- 真正的用户问题不是“缺日志”，而是“日志太多且重复”。
- 公开的结构化事件已经足够承载默认展示语义，没必要把所有 companion events 都抬到顶层。

备选方案：
- 后端完全停止发送通用 companion events。
  - 未选原因：会影响兼容客户端，也让非 Deep Research 路径失去复用能力。优先让前端按场景选择 canonical source。

### 5. 为 branch-scoped 任务和 artifact 事件补齐稳定 `iteration` 归属

后端在正式研究循环中发出的 branch-scoped 公开事件必须具备稳定的轮次归属。具体要求是：

- `research_task_update` 必须在正式研究循环中携带 `iteration`
- `research_artifact_update` 必须在 branch-scoped artifact / verification artifact 上携带 `iteration`
- 已有的 `research_agent_start / complete`、`research_decision` 继续保留 `iteration`
- 恢复和重试场景继续保留 `graph_run_id`、`resumed_from_checkpoint`、`attempt`

这样做的原因：
- 多轮次展示能否稳定，关键不在 UI，而在事件是否能无歧义地归档到某一轮。
- 如果任务和 artifact 没有显式 `iteration`，前端只能依赖时序推断，这在并发、重试和恢复场景下不可靠。

备选方案：
- 仅靠前端根据 decision/时间窗口推断轮次。
  - 未选原因：实现脆弱，且一旦事件顺序变化就会产生错归档。

### 6. 保留 raw event drilldown，但降级为二级信息层

默认视图聚焦摘要和进度，raw event 列表仍然存在，但放在：

- branch details 内的二级展开，或
- debug/raw events 区域

这样做的原因：
- 研发和调试仍然需要原始事件。
- 只做摘要会丢失排障能力；只做日志又无法解决当前 UX 问题。

备选方案：
- 完全移除 raw events。
  - 未选原因：调试成本会上升，且会失去对未来新事件类型的兼容兜底。

## Risks / Trade-offs

- [事件映射规则会随着新 event type 增加而漂移] → 把 phase/branch/iteration 投影逻辑集中到单独模块，并为每类 canonical event 建立前端单测。
- [新增 `iteration` 字段会让部分公开事件 payload 变大] → 仅对正式研究循环中的 branch-scoped 事件补齐，不对所有事件无差别扩张。
- [旧会话或历史数据可能缺少 `iteration`] → 前端对缺失值提供降级 bucket，但新流式会话必须使用显式字段。
- [去噪过度可能掩盖对调试有价值的细节] → 保留 raw drilldown，且不丢弃原始 `processEvents`。
- [phase / branch 摘要统计实现复杂度高于简单列表] → 用纯投影层承接复杂度，避免把复杂度扩散到组件树和 hooks 各处。

## Migration Plan

1. 先补齐后端 Deep Research branch-scoped 事件的 `iteration` 归属字段，并保持旧客户端兼容。
2. 在前端新增 timeline projection 层，先不改组件外观，只让组件读取投影后的显示模型。
3. 把 Deep Research 默认视图切换为 phase/branch/iteration 摘要，并保留 raw events 下钻。
4. 更新 header 指标计算与去噪策略，移除以原始事件数作为主进度指标的逻辑。
5. 补齐前端和后端测试，覆盖多轮次、重试、恢复和重复 companion events。

回滚策略：
- 若前端投影存在问题，可临时回退到 raw event 列表渲染，因为原始 `processEvents` 仍保留。
- 若后端新增字段出现兼容问题，可先保留字段为可选，前端继续支持缺省降级。

## Open Questions

- `search` 连续事件的默认合并粒度应该按 branch、按 iteration，还是按 provider 再细分？
- 默认视图是否要向普通用户完全隐藏 raw events，只对 debug 模式暴露？
- header 中“来源数”应基于 `source_candidate`、`fetched_document` 还是最终去重 citation 统计？
- 某些无 `branch_id` 但有 `task_id` 的过渡事件，是否需要在 runtime 中统一补齐 branch 归属，而不是让前端 fallback？
