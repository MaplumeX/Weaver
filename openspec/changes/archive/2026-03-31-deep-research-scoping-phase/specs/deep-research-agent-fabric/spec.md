## MODIFIED Requirements

### Requirement: Deep research role topology is explicit
系统 MUST 将 Deep Research 的 `clarify`、`scope`、`planner`、`coordinator`、`researcher`、`verifier`、`reporter` 建模为显式的 graph-level 角色，而不是仅存在于单个 runtime 内部的隐式函数调用关系。

#### Scenario: Initializing the deep research subgraph
- **WHEN** 系统为一个 `multi_agent` Deep Research 请求构建执行图
- **THEN** 系统 MUST 为上述角色建立明确的节点或子图归属
- **THEN** 每个角色 MUST 具有稳定且可测试的输入输出契约

#### Scenario: Inspecting runtime topology
- **WHEN** 开发者或测试需要理解 multi-agent Deep Research 的控制流
- **THEN** 系统 MUST 能够从 graph 拓扑上辨认 intake/scoping 与正式研究循环之间的前后关系
- **THEN** 系统 MUST NOT 依赖阅读单个大循环函数才能理解角色协作结构

### Requirement: Role autonomy is bounded by ownership
系统 MUST 将 clarify、scope、planner、coordinator、verifier、reporter 保持为窄职责角色，只允许 researcher 作为执行层向工具自治演进。

#### Scenario: Clarify or scope executes
- **WHEN** `clarify` 或 `scope` 角色被触发
- **THEN** clarify MUST 只负责补足用户背景、目标和约束信息
- **THEN** scope MUST 只负责生成或重写 scope draft，而 MUST NOT 直接生成研究任务或驱动外部工具循环

#### Scenario: Planning or coordination executes
- **WHEN** planner、coordinator、verifier 或 reporter 被触发
- **THEN** 这些角色 MUST 只消费其职责范围内的结构化输入并产出结构化结果
- **THEN** 这些角色 MUST NOT 自主派生无限任务或绕过 graph 控制直接驱动外部工具循环

#### Scenario: Research execution requires tool autonomy
- **WHEN** 研究任务需要搜索、读取或抽取外部信息
- **THEN** 系统 MAY 将该执行能力集中在 researcher worker
- **THEN** researcher 的 fan-out、预算边界和回流路径 MUST 仍由 graph 统一控制
