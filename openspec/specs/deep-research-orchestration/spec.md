## Purpose
定义 Deep Research 收敛到单一 `multi_agent` 运行时后的入口约束与编排行为。
## Requirements
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
系统 MUST 由 `supervisor` 独占 multi-agent Deep Research 的规划与循环控制语义，并通过显式 graph 转移驱动 clarify、scope、scope review、`research brief` handoff、branch dispatch、验证、outline gate、汇总和结束阶段；系统 MUST NOT 再公开或保留独立 `coordinator` 角色、outer hierarchical path 或等价兼容控制面。

#### Scenario: Supervisor waits for approved brief before dispatch
- **WHEN** multi-agent Deep Research 子图接收到一个新的复杂研究主题且当前不存在活动任务
- **THEN** 系统 MUST 先完成 clarify/scoping、scope review 和 `research brief` 生成
- **THEN** `supervisor` MUST 只在权威 `research brief` 就绪后，才将 branch 级任务写入可调度队列并分配唯一任务标识

#### Scenario: Supervisor replans from verifier or outline feedback
- **WHEN** `verifier` 产出了新的 blocking revision issues、未解决的 obligation debt、矛盾记录、缺失证据列表或 `outline gate` 产出了 `outline_gap` 请求且预算仍允许继续研究
- **THEN** `supervisor` MUST 基于当前 brief、ledger 和权威 verification 结果决定是否触发 replan
- **THEN** 系统 MAY 使用 advisory gap hints 辅助决定后续搜索方向，但 MUST NOT 仅凭 advisory gaps 把流程判定为仍不可报告
- **THEN** 系统 MUST 只将被 `supervisor` 批准的新 branch 任务加入任务队列

#### Scenario: Supervisor owns orchestration decisions directly
- **WHEN** runtime 需要决定继续研究、触发 replan、重试 branch、开始 outline 生成、开始汇总或停止
- **THEN** 系统 MUST 由 `supervisor` 直接产出这些决策
- **THEN** 系统 MUST NOT 再暴露 `coordinator` 角色、`coordinator_action` 状态或等价兼容决策分支

### Requirement: Parallel branch tool-agent dispatch
系统 MUST 支持多个 `researcher` branch tool agent 并发执行研究任务，并通过 graph-native fan-out/fan-in 统一控制并发数、预算和任务状态。

#### Scenario: Multiple branch tasks are ready
- **WHEN** 任务队列中存在多个 `ready` 状态的 branch 级研究任务且未超过并发上限
- **THEN** 系统 MUST 通过 graph 分发机制为不同任务创建独立的 `researcher` branch execution path
- **THEN** 同一 branch 任务 MUST NOT 被多个 agent 同时执行

#### Scenario: Branch execution is budget-gated
- **WHEN** `researcher` branch agent 尝试领取或继续执行任务
- **THEN** 系统 MUST 在 graph 分发前检查时间、搜索次数、token、步骤数或其他预算限制
- **THEN** 若预算不足，系统 MUST 阻止新的 branch fan-out 并将控制权交回 `supervisor`

### Requirement: Surface multi-agent runtime failures explicitly
系统 MUST 在 multi-agent Deep Research runtime 发生不可恢复错误时显式报错，而不是自动回退到 legacy deepsearch runner。

#### Scenario: Multi-agent runtime initialization fails
- **WHEN** multi-agent Deep Research 子图在启动阶段发生不可恢复错误
- **THEN** 系统 MUST 记录失败原因
- **THEN** 系统 MUST 将错误透传到上层 Deep Research 错误处理链路

#### Scenario: Core orchestration becomes invalid during execution
- **WHEN** `supervisor`、artifact store、graph dispatch 或任务调度核心发生不可恢复错误
- **THEN** 系统 MUST 停止继续发放新的 multi-agent 任务
- **THEN** 系统 MUST 进入有界失败路径，而不能无限重试或静默切换 engine

### Requirement: Multi-agent graph execution is checkpoint-aware
系统 MUST 让 multi-agent Deep Research 的权威执行状态落在 LangGraph 可 checkpoint 和恢复的边界上，而不是只存在于进程内循环，并在恢复后继续向调用方暴露 branch 级执行进度、`supervisor` 决策上下文、brief/ledger 状态和 outline gate 阶段。

#### Scenario: Deep research pauses or resumes
- **WHEN** multi-agent Deep Research 因 interrupt、暂停或进程恢复而需要继续执行
- **THEN** 系统 MUST 能从已持久化的 graph 状态恢复任务队列、artifacts、当前阶段、权威 `research brief` 和最近的 `supervisor` 决策上下文
- **THEN** 系统 MUST 不要求重新从头执行整个研究流程

#### Scenario: Outline stage resumes after checkpoint
- **WHEN** `outline gate` 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 保留稳定的研究主题、已验证 branch synthesis、coverage/contradiction 输入和待处理 `outline_gap` 状态
- **THEN** `reporter` MUST 能基于恢复后的 outline 状态继续执行，而不会把该恢复错误地表示为一次全新的报告生成

#### Scenario: Branch execution resumes after checkpoint
- **WHEN** 某个 branch `researcher` agent 在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 恢复该 branch 任务的当前阶段、已提交的中间产物、follow-up request 和重试上下文
- **THEN** 系统 MUST 不把该恢复错误地表示为一个全新的无关 branch

#### Scenario: Validation stage resumes after checkpoint
- **WHEN** verifier challenge、claim/citation 检查或 coverage/gap 检查在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 保留稳定的 `branch_id`、任务标识、验证阶段上下文和待处理 supervisor 决策输入
- **THEN** `supervisor` MUST 能基于恢复后的验证结果继续做 replan、dispatch 或 report 决策

#### Scenario: Resumed execution remains externally observable
- **WHEN** 调用方在 scope review 或其他 checkpoint 之后继续执行 Deep Research
- **THEN** 系统 MUST 支持通过可观察的继续执行路径暴露恢复后的 supervisor、research、verify 和 report 阶段进度
- **THEN** 调用方 MUST 不需要等待隐藏的后台完成或重新发起全新研究请求，才能看到恢复后的执行过程

### Requirement: Outline gate blocks final report until structure is ready
系统 MUST 在最终 `report` 前执行一个独立的 `outline gate`，并要求该 gate 只消费已验证 branch synthesis 与权威 validation 汇总来生成最终报告大纲。

#### Scenario: Outline is generated from verified inputs
- **WHEN** `supervisor` 判断研究事实层面已经具备进入写作准备的条件
- **THEN** 系统 MUST 先运行 `outline gate` 生成结构化 outline artifact
- **THEN** `outline gate` MUST 读取每个 branch 的 `BranchValidationSummary` 或等价权威 validation 汇总
- **THEN** `reporter` MUST NOT 在 outline artifact 尚未生成前直接开始最终报告汇总

#### Scenario: Outline gaps reopen the research loop
- **WHEN** `outline gate` 判断当前已验证 branch 结论不足以支撑完整报告结构
- **THEN** 系统 MUST 记录结构化 `outline_gap` request 并把控制权交回 `supervisor`
- **THEN** `supervisor` MUST 决定补充研究、重排现有任务，或停止继续推进报告生成

### Requirement: Advisory gap planning is non-gating
系统 MAY 在 Deep Research runtime 中保留 heuristic gap planning，但该能力 MUST 作为非权威的 reflection pass 存在，而不是 validation gate 的一部分。

#### Scenario: Verify stage emits planning hints
- **WHEN** validation 或其后置 reflection 阶段识别到可补强的研究方向
- **THEN** 系统 MAY 记录 advisory `suggested_queries`、reflection notes 或 equivalent planning hints
- **THEN** 这些 hints MUST NOT 单独阻止流程进入 `outline_gate` 或 `report`

### Requirement: Verification is a structured multi-pass pipeline
系统 MUST 将 `verify` 实现为结构化多阶段流水线，至少覆盖 contract check、evidence admissibility、answer-unit validation、obligation coverage evaluation、scoped consistency evaluation 和 branch validation summary aggregation。

#### Scenario: Verify stage runs after branch merge
- **WHEN** 一个或多个 branch bundle 被 graph merge 接收后进入 `verify`
- **THEN** 系统 MUST 运行结构化的 contract check、evidence admissibility、answer-unit validation、coverage、consistency 和 summary aggregation 阶段，或与之等价的 graph-controlled 子阶段
- **THEN** `supervisor` 接收到的输入 MUST 不只是 summary 文本、gap 数量或粗粒度 pass/fail 状态
- **THEN** 系统 MUST NOT 通过重新抽取 `branch_synthesis.summary` 作为权威 answer targets
- **THEN** 若系统运行了额外的 reflection pass，该 pass MUST 只产出 advisory hints，而 MUST NOT 替代上述权威阶段

#### Scenario: Verify stage remains checkpoint-safe
- **WHEN** 验证流水线在 checkpoint 之后恢复执行
- **THEN** 系统 MUST 能恢复当前验证子阶段、待处理的 answer unit / obligation / issue 上下文和已完成的验证结果
- **THEN** 恢复后的验证 MUST 不会把同一 branch 误表示为一轮全新的无关检查

### Requirement: Blocking revision issues gate outline and report
系统 MUST 在存在未解决 blocking revision issues 时阻止流程直接进入 outline gate 或 final report，除非 `supervisor` 明确给出 bounded stop 或风险接受决策。

#### Scenario: Supervisor receives blocking issues
- **WHEN** `supervisor` 决策输入中存在 blocking 的 revision issues
- **THEN** 系统 MUST 优先回到 patch / follow-up / counterevidence 路径
- **THEN** 系统 MUST NOT 在这些 issues 仍未解决时直接把控制权交给 `reporter`

#### Scenario: Outline gate sees unresolved verification debt
- **WHEN** `outline gate` 启动时仍存在未解决的 blocking validation debt
- **THEN** 系统 MUST 将这些问题视为阻塞性结构前提问题或等价阻塞状态
- **THEN** `outline gate` MUST 不将其静默忽略并直接生成可写作的最终 outline
- **THEN** 系统 MUST NOT 因为 advisory reflection、派生 blocker 列表重复记录了同一问题，就重复升级阻塞状态

#### Scenario: Outline gate receives advisory gaps only
- **WHEN** `outline gate` 看到的剩余缺口仅来自 heuristic planning、弱覆盖建议或其他未映射到正式 issue 的 advisory signal
- **THEN** 它 MUST NOT 将这些信号直接视为 blocking validation debt
- **THEN** 系统 MAY 将这些信号传递给 `supervisor` 或 UI 作为补强建议，但 MUST 允许流程继续进入最终报告

### Requirement: Reflection, validation and evaluation are separated
系统 MUST 将 Deep Research 中的 reflection、runtime validation 和 final evaluation 视为三个职责不同的阶段，而不是让单个 verifier 同时承担 planning hint、事实裁决和最终报告评测。

#### Scenario: Runtime needs more research direction
- **WHEN** 系统在 branch 或全局层面识别到可补强的研究方向
- **THEN** 它 MUST 通过 reflection pass 产出 advisory hints
- **THEN** 这些 hints MUST 不直接改变已存在的 authoritative validation verdict

#### Scenario: Final report quality is assessed
- **WHEN** 系统需要对最终报告执行 citation、completeness 或 factuality 评估
- **THEN** 它 MUST 在 runtime validation 之后执行独立 evaluation pass，或暴露等价的离线评测入口
- **THEN** 该 evaluation pass MUST 不替代 branch-level authoritative validation contract
