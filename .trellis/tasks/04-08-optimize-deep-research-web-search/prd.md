# Optimize deep research web_search

## Goal

明确 deep research 中 researcher 角色使用 `web_search` 的现状、瓶颈与可行优化路径，形成可落地的演进方案。

## Requirements

- 梳理 `researcher` 与 `web_search` 的调用链和职责边界
- 识别当前在延迟、结果质量、重复搜索、事件可观测性上的主要问题
- 给出 2-3 种可落地优化方案，并说明 trade-off
- 给出推荐的 MVP 路线，尽量控制改动范围

## Acceptance Criteria

- [ ] 能说明当前 `deep research` 中 `researcher -> web_search` 的主要执行路径
- [ ] 能指出至少 3 个具体优化点，并关联到现有代码位置
- [ ] 能给出分阶段实施建议，而不是只给抽象方向

## Technical Notes

- 本任务当前处于方案设计阶段，不直接修改业务代码
- 重点关注后端 runtime/tooling，必要时补充前端事件展示影响
