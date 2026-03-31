## Purpose
定义 Deep Research 中 branch-scoped researcher agent 的执行合同、受控多步循环与结构化结果回传。

## Requirements

### Requirement: Branch research tasks define bounded execution contracts
系统 MUST 将 branch-scoped researcher 工作表示为有边界的执行合同，而不是仅表示为原始搜索 query。

#### Scenario: Planner creates a branch objective task
- **WHEN** planner 基于已批准 scope 生成正式研究任务
- **THEN** 系统 MUST 为每个 branch objective 创建结构化 `ResearchTask`
- **THEN** 该任务 MUST 至少包含唯一标识、`branch_id`、`task_kind`、研究目标、验收标准、允许的工具类别和上游 artifact 引用

#### Scenario: Replan issues a replacement or follow-up branch task
- **WHEN** coordinator 基于验证结果触发 replan
- **THEN** planner 产出的新任务 MUST 能表达它与既有 branch 或父任务之间的关联
- **THEN** 系统 MUST NOT 要求通过读取旧 worker 的完整临时上下文才能理解该任务

### Requirement: Branch researcher agents execute multi-step bounded loops
系统 MUST 允许 researcher 作为 branch-scoped true agent 在受控预算和工具边界内执行多步研究。

#### Scenario: Branch agent gathers evidence
- **WHEN** 某个 branch objective 需要搜索、读取、抓取或抽取证据
- **THEN** researcher MAY 在其允许的工具范围内执行多步工具调用
- **THEN** 该执行过程 MUST 受 graph 级预算、重试和 merge 边界控制

#### Scenario: Branch agent cannot expand the graph unilaterally
- **WHEN** researcher 在执行中发现新的研究线索
- **THEN** 它 MUST 通过结构化产物或回流信号请求 coordinator / planner 处理
- **THEN** 它 MUST NOT 直接自行创建不受控的 sibling branch 或无限派生任务

### Requirement: Branch agents return structured result bundles
系统 MUST 要求 branch researcher agent 将执行结果表示为结构化 bundle，并只在 graph merge 阶段写入共享权威状态。

#### Scenario: Branch agent completes successfully
- **WHEN** researcher 完成一个 branch objective
- **THEN** 它 MUST 返回结构化结果 bundle
- **THEN** 该 bundle MUST 能表达分支结论、证据引用、预算消耗和需要写入的 artifacts

#### Scenario: Branch agent completes partially or fails
- **WHEN** researcher 因预算、来源不足或执行错误而未完成 branch objective
- **THEN** 它 MUST 返回结构化的失败或部分完成状态
- **THEN** graph MUST 能基于该状态决定重试、replan、阻塞或终止，而不是依赖非结构化错误文本
