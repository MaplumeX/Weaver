## Why

当前 Deep Research verifier 持续产出高噪音、阻塞性的缺口，根因不是单点 bug，而是验证对象、证据对象和阻塞策略被错误耦合在一起。现有流程仍会从 `branch_synthesis.summary` 反向抽取 claim、把搜索 snippet 当作权威证据、把粗粒度 verifier verdict 广播到整批 claim/obligation，并在 outline 阶段重复累计 blocker，导致研究流程频繁被伪缺口卡住。

现在需要重构 verifier，因为它已经直接影响 Deep Research 的可收敛性和最终报告质量；继续在现有结构上打补丁，只会放大验证噪音和迁移成本。

## What Changes

- 将 verifier 从基于 `summary` 的 branch 级审判器重构为基于结构化 `AnswerUnit` 与稳定 `EvidencePassage` 的 unit 级验证流水线。
- 明确拆分 `reflection`、`validation`、`evaluation` 三层职责；`knowledge_gap` 只保留为 advisory planning hint，不再作为权威 blocker 来源。
- 要求 researcher 直接提交待验证答案单元、obligation 映射和证据引用；verifier 不再重新抽取 claim，也不再使用 topic/token overlap 作为 coverage 主判断依据。
- 要求 verifier 只消费稳定 passage 级证据；搜索结果的 `summary`、`snippet`、`raw_excerpt` 只能用于召回和线索，不得直接作为 authoritative evidence。
- 将 verifier tool-agent fabric tools 改造成 unit / obligation 可寻址接口，移除面向 `summary` 的 challenge / compare 工具。
- 让 orchestration、outline gate 和 reporter 只消费 canonical branch validation summary，避免 blocker 在 gap list、revision issues 和 outline 中重复累计。
- **BREAKING**：调整 `ClaimUnit`/verification contracts 语义、verifier tool-agent 提交接口、coverage 判定方式以及最终报告前的验证输入契约。

## Capabilities

### New Capabilities

无

### Modified Capabilities

- `deep-research-verification-contracts`: 将 claim-addressable contracts 升级为 researcher-submitted answer units、admissible evidence 和 unit-level validation verdicts。
- `deep-research-artifacts`: 将 canonical artifacts 调整为稳定证据、branch validation summary 与 advisory reflection 分层建模。
- `deep-research-tool-agents`: 将 verifier tool-agent 从 summary-oriented tools 改造为 unit-addressable validation tools。
- `deep-research-orchestration`: 重写 verify / outline gate 的阻塞逻辑和迁移路径，只让权威 validation debt 阻塞最终报告。

## Impact

- 受影响代码主要位于 `agent/runtime/deep/orchestration/graph.py`、`agent/runtime/deep/services/verification.py`、`agent/runtime/deep/services/knowledge_gap.py`、`agent/runtime/deep/support/tool_agents.py`、`agent/runtime/deep/schema.py`、`agent/contracts/claim_verifier.py` 以及相关 artifact store / supervisor 读取路径。
- verifier tool-agent 的 fabric 接口与 submission payload 将发生不兼容变化。
- Deep Research 的 artifact schema、validation stage、outline gate 输入以及测试基线需要同步更新。
