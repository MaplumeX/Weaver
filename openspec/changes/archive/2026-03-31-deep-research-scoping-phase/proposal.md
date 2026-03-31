## Why

当前 Deep Research multi-agent runtime 一进入研究就直接生成任务并启动 planner/researcher 循环，缺少一个面向用户的前置 intake/scoping 阶段。对于背景不足、目标模糊或边界复杂的研究请求，这会导致系统过早开题、任务范围漂移，以及用户无法在真正消耗研究预算前确认此次研究到底要做什么。

现在需要在正式研究前补上一段可恢复、可修订、可确认的 scope 流程，让系统先澄清输入，再产出研究草案，并允许用户通过“提出修改意见”驱动 scope agent 重写，直到用户明确批准后才进入 planner。

## What Changes

- 在 Deep Research multi-agent runtime 中新增 intake/scoping 前置阶段，顺序为 `clarify -> scope -> user review -> planner`。
- 新增专属 `clarify agent`，负责在进入研究前补足背景、目标、约束、时间范围、来源偏好和排除项。
- 新增专属 `scope agent`，负责基于已澄清信息生成结构化 `scope draft`，而不是直接生成研究任务。
- 要求 scope draft 必须先经过用户确认，或由用户提交修改意见后触发 `scope agent` 重写新版本；不支持用户直接编辑结构化字段后绕过 agent。
- 将 `planner` 调整为只消费“已批准的 scope draft”，再把 scope 转译为研究任务、查询计划和后续研究循环。
- 为 intake/scoping 阶段增加可恢复的 checkpoint、状态摘要和事件语义，使其与现有 Deep Research SSE/interrupt 流兼容。
- 前端中断交互从“仅工具审批”扩展为支持 Deep Research scope 草案审阅、反馈和批准。

## Capabilities

### New Capabilities
- `deep-research-intake`: 定义 Deep Research 在正式规划与研究前的澄清、范围草案生成、用户反馈修订和批准契约。

### Modified Capabilities
- `deep-research-orchestration`: 调整 multi-agent Deep Research 的图级编排，使 planner 之前必须经过 intake/scoping 阶段并支持基于用户反馈的 scope 重写。
- `deep-research-agent-fabric`: 扩展 Deep Research 的显式角色拓扑，增加 `clarify` 与 `scope` 角色，并约束它们与 planner 的职责边界。
- `deep-research-agent-events`: 扩展事件模型，使 intake/scoping 阶段的 agent 生命周期、scope draft 修订和用户批准进度可被流式消费。

## Impact

- 后端 Deep Research multi-agent 子图与运行时状态模型
- `interrupt/resume` 在 Deep Research scope 审阅场景下的 payload 约定
- Deep Research 事件发射与前端状态映射
- Deep Research 聊天前端中的 interrupt UI 和 scope 草案审阅交互
- 测试覆盖：multi-agent runtime、interrupt/resume、SSE 事件、前端流式消费
