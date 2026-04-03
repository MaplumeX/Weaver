## 1. Verification Contracts And Persistence

- [x] 1.1 在 `agent/runtime/deep/schema.py` 中新增 claim、coverage obligation、grounding result、consistency result、revision issue 和 branch revision brief 的结构化 schema
- [x] 1.2 扩展 `agent/runtime/deep/store.py`、runtime snapshot 与 public artifacts，使新增验证/修订 artifacts 可持久化、可恢复、可导出
- [x] 1.3 扩展 ledger 与 coordination payload，使 issue lifecycle、resolution linkage 和 branch revision lineage 能被权威记录

## 2. Verification Pipeline Refactor

- [x] 2.1 从 `agent/runtime/deep/orchestration/graph.py` 中抽出 claim grounding、coverage obligation evaluation、consistency evaluation 和 issue aggregation 服务
- [x] 2.2 重构 `agent/contracts/claim_verifier.py`，使其围绕结构化 claim 与 passage 引用工作，并保留可控的 fallback 启发式路径
- [x] 2.3 重构 `agent/runtime/deep/services/knowledge_gap.py` 或等价服务，使 coverage 判断以 brief/task 派生 obligations 为权威输入，而不是通用 topic checklist
- [x] 2.4 更新 `verify` 节点，使其消费新 contracts、写入新 verification artifacts，并只向 `supervisor` 暴露结构化 findings 与 revision issues

## 3. Branch Revision Loop

- [x] 3.1 扩展 `supervisor` 决策输入与计划逻辑，使其支持 patch existing branch、spawn follow-up branch、spawn counterevidence branch 和 bounded stop
- [x] 3.2 扩展 `dispatcher`、task queue 和 branch brief/update 逻辑，使 revision task 与 follow-up branch 保留稳定 lineage
- [x] 3.3 更新 `researcher` 执行合同与 result bundle，使其支持 revision-oriented execution、claim units 输出和 issue resolution metadata

## 4. Tool-Agent And Event Integration

- [x] 4.1 扩展 `agent/runtime/deep/support/tool_agents.py`，向 researcher / verifier 暴露结构化 claim、obligation、issue 和 revision context 的 fabric tools
- [x] 4.2 更新 verifier / researcher tool-agent 提交协议，使 submissions 能引用 claim ids、obligation ids、consistency finding ids 和 issue ids
- [x] 4.3 扩展 Deep Research 公开事件、topology/public artifacts 视图和 timeline 投影所需字段，使 verification issue 与 revision lineage 对前端可观察

## 5. Validation And Rollout

- [x] 5.1 补齐 verifier contracts、issue aggregation、branch revision lineage 和 supervisor routing 的单元测试
- [x] 5.2 补齐 verify -> revision -> merge -> re-verify -> outline/report 的集成测试与 checkpoint/resume 回归
- [x] 5.3 更新 Deep Research 架构/rollout 文档与 benchmark 指标，覆盖 verification precision、unresolved issue count 和 revision convergence
