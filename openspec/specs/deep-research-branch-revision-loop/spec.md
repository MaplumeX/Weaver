## Purpose
定义 Deep Research 中由结构化 verification issues 驱动的 branch 修订闭环、修订简报和 lineage 追踪契约。
## Requirements
### Requirement: Verification issues reopen bounded branch revision loops
系统 MUST 让结构化 verification issues 重新打开受控 branch revision loop，而不是把所有验证失败折叠为泛化的重试或全局 replan。

#### Scenario: Blocking verification issues require supervisor routing
- **WHEN** `verifier` 产出 blocking 的 revision issues 且预算仍允许继续研究
- **THEN** `supervisor` MUST 决定是 patch 现有 branch、派生 follow-up branch、派生 counterevidence branch，还是进入有界停止路径
- **THEN** 系统 MUST NOT 在缺少 issue-level 意图的情况下直接把该 branch 当作一次无差别重跑

#### Scenario: Non-blocking issues do not reopen the full loop unnecessarily
- **WHEN** `verifier` 产出仅影响补充说明或弱证据的 non-blocking issues
- **THEN** `supervisor` MAY 选择记录待办、接受风险或继续进入后续阶段
- **THEN** 系统 MUST 不要求每个 non-blocking issue 都派生新的 branch 执行

### Requirement: Branch revision briefs define repair contracts
系统 MUST 用结构化 `BranchRevisionBrief` 定义每次 branch 修订需要解决的问题、允许复用的上下文和完成标准。

#### Scenario: Supervisor patches an existing branch
- **WHEN** `supervisor` 决定修补现有 branch
- **THEN** 系统 MUST 创建 `BranchRevisionBrief`
- **THEN** 该 brief MUST 至少包含 target branch、target task、issue ids、建议动作、允许复用的已有证据和修订完成标准

#### Scenario: Supervisor spawns counterevidence or follow-up work
- **WHEN** `supervisor` 决定为某个 issue 派生 counterevidence 或 follow-up branch
- **THEN** 系统 MUST 创建引用源 issue 的 `BranchRevisionBrief`
- **THEN** 下游 branch MUST 能基于该 brief 理解自己是对既有 branch 的补充、反证还是替代，而不是一个无上下文的新任务

### Requirement: Revision lineage is preserved end-to-end
系统 MUST 保留 branch revision 的 lineage，使任务、artifact、事件和最终报告都能追踪问题如何被修复、替代或保留。

#### Scenario: Branch is revised in place
- **WHEN** 同一 `branch_id` 在后续轮次中进入修订
- **THEN** 系统 MUST 为新的 revision task 保留与原 branch 的 lineage 关联
- **THEN** 客户端和测试 MUST 能看到该修订解决了哪些 issue，以及仍有哪些 issue 未解决

#### Scenario: Follow-up work resolves prior issues
- **WHEN** 某个 follow-up 或 counterevidence branch 成功解决上游 issue
- **THEN** 系统 MUST 记录 issue resolution 与 source branch / target branch 之间的关联
- **THEN** `supervisor` 与 `reporter` MUST 能判断最终被采纳的是原结论、修订结论还是保留争议的并行结论
