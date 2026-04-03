## MODIFIED Requirements

### Requirement: Role autonomy is bounded by ownership
系统 MUST 将 `clarify`、`scope`、`supervisor` 保持为控制平面 agents，并将 `researcher`、`verifier`、`reporter` 限定为受策略约束的执行型 agents；所有角色 MUST 只在其拥有的工具表面和状态边界内行动，并通过 `research brief`、ledger、验证 artifacts 和 outline handoff 协作。

#### Scenario: Clarify or scope executes
- **WHEN** `clarify` 或 `scope` 角色被触发
- **THEN** 它们 MUST 只负责补足用户背景、目标和约束，或生成与修订 scope draft，并把已批准结果交接到 `research brief` 生成阶段
- **THEN** 它们 MUST NOT 直接驱动 world-facing 的外部研究工具循环

#### Scenario: Supervisor executes
- **WHEN** `supervisor` 角色被触发
- **THEN** 它 MUST 只通过 fabric tools 消费 `research brief`、ledger、task、artifact 和 verification 状态并产出调度决策
- **THEN** 它 MUST NOT 直接执行 branch 级证据采集、跳过 outline gate 或绕过 graph merge 改写权威状态

#### Scenario: Research, verification or reporting executes
- **WHEN** `researcher`、`verifier` 或 `reporter` 被触发
- **THEN** 它们 MUST 仅在角色允许的工具边界内执行多步动作并返回结构化结果
- **THEN** 它们 MUST NOT 直接创建不受控 graph 分支、直接改写共享权威状态，或绕过权威 brief/outline handoff

## ADDED Requirements

### Requirement: Report handoff remains outline-gated
系统 MUST 将最终报告前的结构整理保持为 graph-controlled handoff，而不是让 `reporter` 直接从已验证 branch synthesis 跳到最终报告。

#### Scenario: Outline gate consumes verified branch knowledge
- **WHEN** 系统准备把研究结果交给 `reporter`
- **THEN** 系统 MUST 先基于已验证 branch synthesis、coverage matrix、contradiction registry 和 missing evidence list 生成 outline artifact
- **THEN** `reporter` MUST 只消费该 outline artifact 与其引用的已验证研究结果，而不是自行重建独立写作计划

#### Scenario: Outline gaps return to supervisor instead of bypassing the graph
- **WHEN** 结构整理阶段发现当前研究结果无法支撑目标报告结构
- **THEN** 系统 MUST 将该缺口表示为结构化 `outline_gap` coordination request
- **THEN** `reporter` MUST NOT 直接跳过该缺口进入最终成文
