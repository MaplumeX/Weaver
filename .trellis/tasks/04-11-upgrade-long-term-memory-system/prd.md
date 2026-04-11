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

* 这次升级的第一优先级到底是哪一类问题？

## Requirements (evolving)

* 升级方案必须基于当前项目自有 memory 主路径演进，不重新引入旧双轨实现。
* 设计必须遵守现有 backend 模块边界：
  * `common/` 负责共享基础设施
  * `main.py` 负责组合根和 API 接线
* 如果改动持久化模型，必须保持 runtime-managed DDL 的 additive / idempotent 约束。
* 如果改动 API 或 runtime payload，必须明确跨层 contract 和回归测试点。
* MVP 需要明确包含什么，不包含什么，避免一次性把长期记忆系统“全能化”。

## Acceptance Criteria (evolving)

* [ ] 明确这次升级的主目标，不再把“升级长期记忆”保持在泛化表述。
* [ ] 给出 1 个推荐方向和 1-2 个备选方向，并说明 trade-off。
* [ ] 明确本轮 MVP 的边界、涉及文件和测试策略。
* [ ] 最终需求说明经用户确认，可进入实现前研究与上下文配置。

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
