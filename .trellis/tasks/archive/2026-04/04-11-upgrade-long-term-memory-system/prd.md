# Upgrade current long-term memory system

## Goal

在不推翻现有长期记忆主路径的前提下，升级 Weaver 当前的长期记忆系统，使其在记忆写入质量、检索命中质量、治理可观测性或演进架构上更进一步，同时保持与现有 backend 模块边界、runtime 注入方式和测试约束一致。

## What I already know

* 用户希望切换到一个新任务：“升级当前的长期记忆系统”。
* 当前仓库已经不是旧的多轨 memory 方案，而是项目自有主路径：
  * `common/memory_service.py`
  * `common/memory_store.py`
  * `common/persistence_schema.py`
  * `main.py` 中的 `/api/memory/*` 路由与 runtime wiring
* 当前长期记忆的已有能力：
  * 仅在用户有明确记忆意图时写入
  * 记忆类型目前只有 `preference` 和 `user_fact`
  * 支持 `stored` / `relevant` 两类 runtime context
  * 支持人工 `invalidate` / `delete`
  * 支持事件记录 `memory_entry_events`
* 当前实现的明显边界与限制：
  * 抽取规则主要靠正则和少量关键词，覆盖面较窄
  * 检索主要依赖简单 token overlap + importance + recency，召回和排序能力较弱
  * 数据模型较轻，缺少更细粒度的生命周期/冲突/可信度语义
  * 目前更像“保守版事实卡片存储”，还没有进入更强治理或更智能召回阶段
* 这次任务属于后端/跨层任务，至少会影响：
  * persistence contract
  * service contract
  * runtime memory injection
  * memory debug/admin API
  * 回归测试

## Assumptions (temporary)

* 这次任务更可能是“现有系统的二阶段升级”，而不是重做一期底座。
* 用户现在最需要的，可能是以下四类升级之一：
  * 提高召回/排序质量
  * 提高写入/去重/冲突处理质量
  * 增强治理与调试能力
  * 朝“session 为事实源”的投影式架构演进
* 在目标明确前，不应直接进入实现，因为这四类方向的改动面和 MVP 完全不同。

## Open Questions

* （当前无阻塞性开放问题，待用户确认后进入实现阶段）

## Requirements (evolving)

* 升级方案必须基于当前项目自有 memory 主路径演进，不重新引入旧双轨实现。
* 设计必须遵守现有 backend 模块边界：
  * `common/` 负责共享基础设施
  * `main.py` 负责组合根和 API 接线
* 如果改动持久化模型，必须保持 runtime-managed DDL 的 additive / idempotent 约束。
* 如果改动 API 或 runtime payload，必须明确跨层 contract 和回归测试点。
* MVP 需要明确包含什么，不包含什么，避免一次性把长期记忆系统“全能化”。
* 本轮主方向已确定为“写入与治理升级”，不以检索排序升级或 session 投影式重构为主线。
* 在“写入与治理升级”内部，本轮优先级已进一步确定为“写入质量优先”。
* 模型辅助抽取只对“明确记忆指令”触发，不对一般稳定事实表达开放。
* 模型抽取失败、超时或结果不稳定时，采取保守跳过策略，不回退为规则写入。
* 本轮不做 memory schema 扩展，优先复用现有 `metadata` 和 `memory_entry_events` 承载抽取来源、跳过原因和覆盖依据。
* 本轮升级重点是提升显式记忆写入质量，而不是扩大记忆覆盖面或重做治理后台。

## Acceptance Criteria (evolving)

* [ ] 明确这次升级的主目标，不再把“升级长期记忆”保持在泛化表述。
* [ ] 给出 1 个推荐方向和 1-2 个备选方向，并说明 trade-off。
* [ ] 明确本轮 MVP 的边界、涉及文件和测试策略。
* [ ] 最终需求说明经用户确认，可进入实现前研究与上下文配置。
* [ ] 已确认本轮主方向为“写入与治理升级”。
* [ ] 已确认本轮子方向为“写入质量优先”。
* [ ] 已确认模型抽取只在明确记忆指令上触发。
* [ ] 已确认模型不稳时采用保守跳过，而不是规则兜底。
* [ ] 已确认本轮先不做 schema 扩展，调试与治理信息通过 `metadata/events` 落地。

## Definition of Done (team quality bar)

* 升级目标被收敛为可实现的 contract 变化
* 涉及的 service / store / API / runtime 边界被明确说明
* 对应测试范围可落地

## Out of Scope (explicit)

* 在需求尚未收敛前直接开始大面积代码改造
* 同一轮同时覆盖“检索、抽取、治理、投影架构”四条升级线
* 引入与现有项目风格不一致的新持久化框架或新分层

## Technical Notes

* 当前已检查文件：
  * `common/memory_service.py`
  * `common/memory_store.py`
  * `common/persistence_schema.py`
  * `main.py`
  * `agent/chat/prompting.py`
  * `tests/test_memory_service.py`
  * `tests/test_session_service_memory_ingest.py`
  * `tests/test_internal_api_auth.py`
* 当前已检查规范：
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/backend/database-guidelines.md`
  * `.trellis/spec/backend/error-handling.md`
  * `.trellis/spec/backend/logging-guidelines.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/backend/tool-runtime-contracts.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`
* 已发现的现状限制：
  * `_extract_candidate_from_user_text()` 以显式模式匹配为主
  * `_select_relevant_entries()` 以 lexical overlap 打分为主
  * `memory_entries` 当前缺少更细的状态/冲突字段
  * API 更偏调试接口，尚不是完整治理接口

## Research Notes

### Current system snapshot

当前长期记忆已经完成一期底座统一，核心是“显式意图写入 + 原子 fact/preference 卡片 + 保守召回 + 人工治理接口”。

### Feasible upgrade directions here

**Approach A: 检索质量升级** (Recommended by default)

* How it works:
  * 强化 query normalization、排序与过滤
  * 改善 relevance score 与命中原因
  * 视范围决定是否引入更强的相似度策略
* Pros:
  * 最直接提升“记住了但用不上”的问题
  * 对现有写入链路侵入较小
* Cons:
  * 不能解决抽取覆盖率或事实质量问题

**Approach B: 写入与治理升级**

* How it works:
  * 扩充显式记忆表达识别
  * 增强去重、冲突覆盖、状态演进和治理字段
* Pros:
  * 能提升长期记忆内容本身的质量
  * 为后续检索质量提升打基础
* Cons:
  * 改动会触及 schema、service、API、测试

**Approach C: 架构升级为 session 投影式 memory**

* How it works:
  * session/message 作为事实源
  * 长期记忆由投影/提炼管线生成
* Pros:
  * 长期治理、回放、重建能力最强
* Cons:
  * 范围最大，明显不是最小可行升级

### Working recommendation

如果用户暂时没有更明确偏好，先做 **Approach A：检索质量升级** 最合理，因为它能最快提升当前可感知效果，并且不会过早把范围扩展到“重做 memory 架构”。

## Decision Update

用户已确认本轮优先选择 **Approach B：写入与治理升级**。
用户已确认在该方向下优先选择 **写入质量优先**。
用户已确认技术路线采用 **规则准入 + 模型辅助抽取**。
用户已确认模型抽取的触发边界为 **只在明确记忆指令上触发**。
用户已确认模型失败或结果不稳定时采用 **保守跳过**。
用户已确认本轮 **不做 schema 扩展，先复用 `metadata/events`**。

当前需要继续收敛的问题：

* 无

## Write-Quality Direction

### Current bottlenecks

* `_extract_candidate_from_user_text()` 目前主要依赖固定正则和关键词。
* “明确记忆意图”识别过于保守，容易漏掉合法表达。
* 去重键只有 `normalized_key`，对“轻微改写但语义相同”不够稳健。
* 当前没有显式记录“为何跳过写入”或“为何覆盖旧值”的细粒度原因。

### Feasible sub-approaches

**Sub-approach A: 纯规则增强** (Recommended by default)

* 扩展显式记忆意图模式
* 增强清洗、规范化、去重和临时态拦截规则
* 增加最小必要的写入原因/覆盖原因字段
* 优点：
  * 可预测、可测试、低风险
  * 不引入模型调用成本和不稳定性
* 缺点：
  * 覆盖率提升有限
  * 对复杂表达仍可能漏判

**Sub-approach B: 规则 + 模型辅助抽取**

* 对显式记忆意图已成立的消息，使用结构化抽取来生成 fact card
* 规则负责准入和拦截，模型负责标准化内容、类型与覆盖判断候选
* 优点：
  * 写入质量提升空间更大
  * 对复杂自然语言表达更友好
* 缺点：
  * 实现和测试复杂度明显更高
  * 需要处理模型不稳定、超时和降级路径

### Implementation notes discovered

* 仓库已经有结构化输出的现成模式：
  * `agent/foundation/smart_router.py`
  * `agent/execution/intake/domain_router.py`
  * `agent/tooling/agents/provider_safe_middleware.py`
* 因此 memory 抽取不需要发明新的模型调用协议，更合理的实现是：
  * 规则先做准入与拦截
  * 命中后走结构化输出抽取
  * 模型失败时降级回纯规则提取或直接跳过

### Confirmed guardrails

* 只有匹配明确记忆意图的用户消息才允许进入模型抽取链路。
* 一般性的“我更喜欢...”“我主要用...”这类表达，本轮不自动升级为模型抽取范围。
* 本轮的目标是提升显式记忆写入质量，而不是扩大长期记忆的覆盖面。
* 模型抽取失败、超时、空结果、低稳定性结果时，直接跳过写入，不走规则兜底。

### Schema options for this round

**Option A: 不改 schema，先复用 `metadata` + `memory_entry_events`** (Recommended)

* 在 `memory_entries.metadata` 记录：
  * `ingestion_method`
  * `extractor_model`
  * `extractor_version`
  * `ingestion_reason`
  * `dedupe_basis`
* 在 `memory_entry_events` 记录：
  * skip reason
  * extraction failure
  * overwrite / supersede decision
* 优点：
  * 改动最小
  * 不引入新的 API 主字段和 DDL 成本
  * 更适合先验证模型辅助抽取是否值得长期保留
* 缺点：
  * 调试信息更偏次级字段，不如一等列清晰

**Option B: 做最小 additive schema 扩展**

* 为 memory entry 增加少量一等字段，例如：
  * `ingestion_method`
  * `extraction_status`
  * `superseded_by_entry_id`
* 优点：
  * 读写、调试和治理更显式
* 缺点：
  * 本轮复杂度明显上升
  * 需要同步 API payload、DDL、测试

## Proposed MVP

### Goal of this iteration

把当前长期记忆写入链路升级为：

* 规则负责准入与临时态拦截
* 仅对明确记忆指令触发模型结构化抽取
* 模型成功时写入更干净的 fact/preference card
* 模型失败或结果不稳时直接跳过写入
* 抽取方式、跳过原因和覆盖依据通过 `metadata/events` 留痕

### In scope

* `common/memory_service.py`
  * 引入结构化抽取模型与 schema
  * 增强显式记忆意图准入规则
  * 增加模型成功/失败/跳过/覆盖留痕
  * 保留保守降级语义
* `common/session_service.py`
  * 继续复用现有唯一写入入口，必要时透传抽取上下文
* `main.py`
  * 组合并初始化 memory extractor 依赖
  * 如有必要，仅补充最小调试可见性，不改现有 memory API 主合同
* `tests/test_memory_service.py`
  * 覆盖模型成功、失败跳过、显式意图准入、临时态拦截、metadata/events 留痕
* 相关回归测试
  * `tests/test_session_service_memory_ingest.py`
  * 必要时补 memory API 调试字段断言

### Out of scope for this iteration

* 不扩大长期记忆自动覆盖范围
* 不对普通稳定事实表达启用模型抽取
* 不增加新的 memory 表字段
* 不实现候选池、人工审核流或在线编辑
* 不做检索排序升级
* 不做 session 投影式长期记忆重构

### Candidate contracts

#### Extraction contract

新增一个结构化抽取结果模型，至少包含：

* `should_store: bool`
* `memory_type: "preference" | "user_fact"`
* `fact: str`
* `normalized_key_hint: str | None`
* `importance: int | None`
* `reasoning: str`
* `stability: "high" | "medium" | "low"`

写入门槛：

* 只有规则准入通过的消息才调用抽取模型
* 只有 `should_store=true` 且 `stability=high` 的结果才允许落库
* 其余情况直接跳过并写事件/元数据原因

#### Metadata / events contract

`memory_entries.metadata` 预计补充：

* `ingestion_method: "explicit_rule_llm"`
* `extractor_model: str`
* `extractor_version: str`
* `ingestion_reason: str`
* `dedupe_basis: str`

`memory_entry_events` 预计补充事件：

* `ingest_skipped`
* `extract_failed`
* `extract_rejected`
* `ingested`

### Files likely to change

* `common/memory_service.py`
* `common/session_service.py`
* `main.py`
* `tests/test_memory_service.py`
* `tests/test_session_service_memory_ingest.py`
* 可能新增一个与 memory 抽取相关的测试文件
