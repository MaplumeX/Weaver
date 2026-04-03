## Why

当前 Deep Research 已经具备 `research brief -> supervisor -> branch dispatch -> verify -> outline gate -> report` 的正确骨架，但 `verify` 仍然主要依赖摘要文本、关键词覆盖和粗粒度 follow-up request 做判断，无法稳定回答“哪个 claim 被哪段证据支持、哪个 coverage obligation 尚未满足、哪些 branch 之间存在冲突”。继续在现状上叠加更多 branch agent 行为，只会放大误判、重跑和不可解释性，因此需要先把验证协议和修订闭环收紧为结构化合同。

## What Changes

- 将 `verifier` 从“对 branch summary 做粗粒度检查”的阶段，升级为消费结构化 claims、coverage obligations 和 cross-branch consistency inputs 的 contract-first verification pipeline。
- 为 Deep Research 引入结构化验证 artifacts，包括 claim 单元、coverage obligation、claim grounding result、coverage result、consistency result 和 branch revision brief，使验证结果能够直接驱动后续修订。
- 在 `verify` 与 `supervisor` 之间新增 branch revision loop 语义，让系统能够选择“修补现有 branch”或“派生 counterevidence / follow-up branch”，而不是只做整条 branch 的重试或全局 replan。
- 调整 `researcher` / `verifier` bounded tool-agent 协议，使其围绕结构化验证对象工作；`verifier` tool agent 负责补证据与裁决边界 case，而不是继续充当唯一 coverage 判官。
- 扩展 `task ledger`、`progress ledger`、coordination request 和公开事件，使 revision issue、resolution、lineage 和 cross-branch contradiction 对前端、测试和恢复路径可观察。

## Capabilities

### New Capabilities
- `deep-research-verification-contracts`: 定义 claim、coverage obligation、grounding、consistency 和 revision issue 的结构化验证合同。
- `deep-research-branch-revision-loop`: 定义 verifier 结果如何驱动 branch 修订、反证分支派生和 revision lineage 收敛。

### Modified Capabilities
- `deep-research-orchestration`: 将 `verify -> supervisor -> dispatch/report` 的循环升级为可消费结构化 verification issues 与 revision briefs 的控制协议。
- `deep-research-artifacts`: 扩展 artifact store，使其能够承载结构化验证对象、revision briefs 和 resolution lineage。
- `deep-research-agent-fabric`: 收紧 researcher / verifier / supervisor 的职责边界，使验证与修订保持 graph-controlled handoff。
- `deep-research-branch-agent-execution`: 要求 researcher 支持 revision-oriented branch execution，而不只是初始 branch research。
- `deep-research-tool-agents`: 调整 bounded tool-agent 契约，使 verifier / researcher 基于结构化 claims 与 obligations 工作。
- `deep-research-agent-events`: 扩展公开事件，使 claim-level verification、revision issue、resolution 和 cross-branch contradiction 可观察。

## Impact

- 影响模块：`agent/runtime/deep/orchestration/*`、`agent/runtime/deep/schema.py`、`agent/runtime/deep/store.py`、`agent/runtime/deep/support/tool_agents.py`
- 影响角色与服务：`agent/runtime/deep/roles/supervisor.py`、`agent/runtime/deep/roles/researcher.py`、`agent/contracts/claim_verifier.py`、`agent/runtime/deep/services/knowledge_gap.py`
- 影响契约：verification payload、coordination request、progress ledger、coverage matrix、contradiction registry、outline gate 输入
- 影响公开可观察面：Deep Research SSE 事件、public artifacts、checkpoint/resume 恢复语义
- 影响测试与评估：verifier 单测、verify->revision 集成测试、benchmark 指标与 golden 回归
