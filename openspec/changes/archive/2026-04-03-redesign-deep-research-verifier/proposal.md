## Why

当前 Deep Research 的 verifier 同时混用了两套标准：一套是基于 `ClaimUnit` / `CoverageObligation` 的结构化验证，另一套是基于 topic checklist 的 `KnowledgeGapAnalyzer` 回退判断。后者仍会通过 `knowledge_gap`、`missing_evidence_list` 和 `outline_gate` 进入最终报告门禁，导致即使结构化 obligation 已满足，runtime 仍持续判定“有缺口”，无法稳定产出报告。

这个问题已经直接影响 deep research 的主流程收敛。现在需要把 verifier 重构为单一、可解释、可收敛的 contract-first gate，并把启发式 gap 分析降级为 replan 辅助信号。

## What Changes

- 重构 Deep Research verifier，使最终通过/阻塞判断只由结构化 claim grounding、coverage obligation evaluation、consistency evaluation 和 revision issues 决定。
- 将 `KnowledgeGapAnalyzer` 从权威 verification gate 中剥离，改为仅产出非权威的 replan hints / search hints。
- 调整 verification summary、missing evidence artifact、outline gate 和 report handoff，避免 heuristic gaps 被提升为 blocking final-report gate。
- 收紧 verifier tool-agent 契约，要求其提交 obligation-addressable 的裁决结果，而不是用单个 `passed` 覆盖整条 branch。
- 细化 blocking / non-blocking verification issue 语义，避免 `partially_satisfied` 等弱缺口无差别重开全量研究闭环。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deep-research-verification-contracts`: 明确 contract-first verification 是唯一权威 gate，启发式 gap 分析不得覆盖或降格已满足的 obligation 结果。
- `deep-research-orchestration`: 调整 verify、supervisor_decide、outline_gate 和 report 的编排语义，只允许结构化 blocking issues 阻断最终报告。
- `deep-research-artifacts`: 调整 `knowledge_gap`、`missing_evidence_list`、verification summary 和公开 artifacts 的语义边界，避免非权威 gap 污染 canonical gate。
- `deep-research-agent-fabric`: 收紧 verifier tool-agent 的 fabric 契约，要求提交 obligation/issue 级裁决，而不是 blanket pass。
- `deep-research-branch-revision-loop`: 细化哪些 verification findings 会打开 bounded revision loop，哪些只作为非阻塞补充信号保留。

## Impact

- Affected code:
  - `agent/runtime/deep/services/verification.py`
  - `agent/runtime/deep/services/knowledge_gap.py`
  - `agent/runtime/deep/orchestration/graph.py`
  - `agent/runtime/deep/support/tool_agents.py`
  - `agent/runtime/deep/artifacts/public_artifacts.py`
  - `tests/test_deepsearch_verification_services.py`
  - `tests/test_deepsearch_multi_agent_runtime.py`
- Affected systems:
  - Deep Research verification pipeline
  - Supervisor revision routing
  - Outline/report gating
  - Public deep research artifacts and SSE quality signals
