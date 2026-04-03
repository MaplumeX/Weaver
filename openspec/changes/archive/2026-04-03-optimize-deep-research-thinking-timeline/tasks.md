## 1. Backend Event Contract

- [x] 1.1 为正式研究循环中的 `research_task_update` 补齐稳定的 `iteration` 归属字段
- [x] 1.2 为 branch-scoped `research_artifact_update` 与相关 verification artifact 事件补齐稳定的 `iteration` 归属字段
- [x] 1.3 校验重试与恢复路径上的 `research_*` 事件继续稳定携带 `graph_run_id`、`resumed_from_checkpoint`、`attempt` 和 `iteration`

## 2. Frontend Timeline Projection

- [x] 2.1 新增 Deep Research timeline projection 层，把原始 `processEvents` 归一化为 phase / branch / iteration 显示模型
- [x] 2.2 在 projection 中实现 Deep Research 默认视图的 companion event 去噪规则，抑制重复 `task_update`、低信息量 topology 事件和搜索噪音
- [x] 2.3 基于投影结果计算 thinking header 聚合指标，替换原始事件步数作为主进度文案

## 3. Thinking UI Rendering

- [x] 3.1 更新 `ThinkingProcess`，默认按 `intake / scope / planning / branch research / verify / report` 渲染阶段摘要
- [x] 3.2 在研究阶段按 `branch` 渲染分支摘要，并在默认视图隐藏 `branch_id`、`task_id`、`node_id` 等内部标识
- [x] 3.3 为 Deep Research 增加 raw event drilldown，使原始事件保留为二级信息层
- [x] 3.4 确保多轮次、重试和恢复后的分支进展被显示为同一 branch 历史的连续阶段，而不是新的平铺行

## 4. Verification

- [x] 4.1 为后端补充 Deep Research 事件测试，覆盖 task/artifact 的 `iteration` 字段以及 resume/retry 连续性
- [x] 4.2 为前端补充 timeline projection 测试，覆盖 phase 分组、branch 聚组、轮次区分和 companion event 去噪
- [x] 4.3 为 thinking UI 补充测试，验证 header 聚合指标、默认摘要视图和 raw event drilldown 行为
