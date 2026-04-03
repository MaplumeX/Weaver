## MODIFIED Requirements

### Requirement: Deep Research engine selection
系统 MUST 将需要真正深入研究的 `deep` 请求固定到单一 canonical Deep Research runtime，并在进入 runtime 前允许执行一次显式 preflight 判断；若该判断认定请求属于简单问题，则系统 MUST 将其转交 `agent` 模式处理，而 MUST NOT 路由到 `direct`、`web`、legacy runtime、`coordinator` 分支或任何 tree/linear 旧路径。

#### Scenario: Deep research enters the only supported runtime
- **WHEN** 请求被路由到 `deep` 模式且 preflight 判断该请求需要真实的深度研究
- **THEN** 系统 MUST 直接启动 canonical Deep Research 子图
- **THEN** 系统 MUST NOT 通过 `deepsearch` 时代的兼容入口、兼容节点名称或兼容 engine alias 启动运行时

#### Scenario: Simple deep request is downgraded to agent
- **WHEN** 请求被路由到 `deep` 模式且 preflight 判断该请求可由简单路径满足
- **THEN** 系统 MUST 将该请求转交 `agent` 执行路径处理
- **THEN** 系统 MUST NOT 调用 `direct_answer_node`、`web` 专用路径、legacy deep runtime 或 outer hierarchical Deep Research 分支

#### Scenario: Obsolete legacy runtime inputs are rejected
- **WHEN** 调用方仍传入 `legacy` engine、`deepsearch_mode`、tree/linear 选择项或其他 deepsearch 时代兼容输入
- **THEN** 系统 MUST 不再路由到任何兼容 runtime，也 MUST NOT 静默迁移这些输入
- **THEN** 系统 MUST 以显式校验错误或配置错误暴露该输入已废弃

### Requirement: Supervisor-controlled research loop
系统 MUST 由 `supervisor` 独占 multi-agent Deep Research 的规划与循环控制语义，并通过显式 graph 转移驱动 clarify、scope、scope review、branch dispatch、验证、汇总和结束阶段；系统 MUST NOT 再公开或保留独立 `coordinator` 角色、outer hierarchical path 或等价兼容控制面。

#### Scenario: Supervisor waits for approved scope before dispatch
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** 系统 MUST 先完成 clarify/scoping 和 scope review
- **THEN** `supervisor` MUST 只在 scope draft 被用户批准后，才将 branch 级任务写入可调度队列并分配唯一任务标识

#### Scenario: Supervisor replans from verifier feedback
- **WHEN** `verifier` 产出了新的 claim/citation 问题、coverage gap 或 follow-up 请求且预算仍允许继续研究
- **THEN** `supervisor` MUST 基于当前证据、scope 和验证结果决定是否触发 replan
- **THEN** 系统 MUST 只将被 `supervisor` 批准的新 branch 任务加入任务队列

#### Scenario: Supervisor owns orchestration decisions directly
- **WHEN** runtime 需要决定继续研究、触发 replan、重试 branch、开始汇总或停止
- **THEN** 系统 MUST 由 `supervisor` 直接产出这些决策
- **THEN** 系统 MUST NOT 再暴露 `coordinator` 角色、`coordinator_action` 状态或 outer hierarchical 决策分支
