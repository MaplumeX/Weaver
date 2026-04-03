## 1. Schema And Contracts

- [x] 1.1 在 Deep Research schema 和 artifact store 中引入 `AnswerUnit`、增强版 `EvidencePassage` 与 `BranchValidationSummary` 的 canonical 持久化契约
- [x] 1.2 为旧 `ClaimUnit` / 旧 verification artifacts 增加兼容适配层，支持迁移期双写与读取
- [x] 1.3 将 advisory reflection artifacts 与 authoritative validation debt / public artifacts 视图彻底分离

## 2. Validation Pipeline

- [x] 2.1 重写 researcher -> verifier handoff，使 verifier 直接消费 researcher 提交的 `AnswerUnit`，不再从 `branch_synthesis.summary` 反抽 claim
- [x] 2.2 实现 evidence admissibility 检查，拒绝 snippet-only 证据进入 authoritative validation
- [x] 2.3 实现按 `unit_type` 分流的 answer-unit validation，并输出 unit-scoped validation results
- [x] 2.4 用 obligation-to-answer-unit mapping 重写 coverage evaluation，移除 token-overlap 主判定逻辑
- [x] 2.5 重写 cross-branch consistency 检查与 branch summary aggregation，生成唯一权威 `BranchValidationSummary`

## 3. Tool Agents And Orchestration

- [x] 3.1 替换 verifier 的 summary-oriented fabric tools，为 unit / obligation 可寻址的 validation tools
- [x] 3.2 更新 verifier tool-agent submission merge 逻辑，禁止 branch-level verdict 广播到整批 objects
- [x] 3.3 更新 supervisor、outline gate、reporter 和 public artifact 读取路径，只消费 `BranchValidationSummary`
- [x] 3.4 将 `knowledge_gap` / reflection pass 降级为 advisory non-gating 流程，并保留 feature flag / shadow mode 迁移开关

## 4. Tests And Cutover

- [x] 4.1 为中文语义改写、数值/日期/趋势冲突、组合结论依赖和 snippet 拒收补充验证测试
- [x] 4.2 为 verifier tool-agent 增加 unit-addressable 提交、非广播 merge 和 obligation coverage 的集成测试
- [x] 4.3 增加 shadow compare / migration 指标，对比新旧 verifier 的 blocker、coverage 与 consistency 输出
- [x] 4.4 在 cutover 稳定后删除旧 summary-based verifier、旧 coverage matcher 和重复 blocker 聚合逻辑
