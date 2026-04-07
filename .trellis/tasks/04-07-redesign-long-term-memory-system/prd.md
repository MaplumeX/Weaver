# brainstorm: redesign long-term memory system

## Goal

重新设计 Weaver 的长期记忆系统，明确长期记忆的写入、存储、检索、注入和演进边界，使其与当前 chat-first runtime、session persistence 和现有后端模块边界一致，避免继续在多个 memory 实现之间双写、双检索和语义漂移。

## What I already know

* 用户希望“重新设计长期记忆系统”。
* 用户已明确选择“全量重构”方向，即不只调整运行时接口，还要考虑存储统一、迁移与治理能力。
* 用户已明确选择第一阶段范围为“统一底座 + 基础治理”：
  * 统一数据模型
  * 单一存储后端
  * 统一读写检索接口
  * 迁移旧数据
  * 去重、冲突覆盖规则、重要性/类型字段、基础观测接口
* 用户已明确要求把以下内容纳入 MVP：
  * 主聊天、support、session 抽取入口的一致性
  * 迁移回滚
  * 调试观测
  * 冲突/脏数据处理
* 当前主聊天流在构建初始 agent state 时，会同时注入两类记忆：
  * `stored_memories` 来自 `main.py` 的 `_store_search(...)`
  * `relevant_memories` 来自 `tools/core/memory_client.py` 的 `fetch_memories(...)`
* 当前主聊天流在完成回答后会同时写入三处：
  * `add_memory_entry(final_report)`
  * `store_interaction(input_text, final_report)`
  * `_store_add(input_text, final_report, user_id=user_id)`
* `support_chat` 也单独使用 `_store_search/_store_add`，而 `support_agent.py` 使用 `fetch_memories/store_interaction`，说明 support 路径与主聊天路径同样存在双轨记忆实现。
* 2026-04-06 的 chat-first 设计文档已经明确要求：
  * memory 不再写入 `messages`
  * memory 保持结构化数据或从 store 动态检索
  * 在 `chat_respond` 中按需转成少量上下文块注入 prompt
* 当前基础设施分为两条线：
  * session persistence 走 `common/session_store.py` 的自有 Postgres 表
  * long-term memory store 走 `main.py` 初始化的 LangGraph `PostgresStore/RedisStore`
* 这意味着长期记忆全量重构时，必须明确是继续基于 LangGraph store 抽象，还是下沉为项目自有持久化模型。
* 当前测试已经锁定一部分新约束：
  * `tests/test_agent_state_slices.py` 要求 `messages` 保持干净，记忆进入 `memory_context`
  * `tests/test_agent_prompt_runtime_context.py` 要求运行时 prompt 能正确拼接 profile 和 memory context

## Assumptions (temporary)

* 这次任务的重点应是“长期记忆系统设计与实现路线”，而不是只改一个 retrieval 函数。
* 新设计需要统一并最终替换当前双轨记忆实现，但不能破坏刚落地的 chat-first runtime 约束。
* 这次改造大概率属于后端/跨层任务，至少会涉及 `main.py`、`agent/` runtime state、`tools/core/memory_client.py`，以及 store/checkpointer 相关基础设施。
* 既然目标是全量重构，MVP 也至少要定义清楚统一后端、迁移策略和新旧 contract 的切换边界。
* 既然第一阶段要纳入基础治理，新数据模型里至少会包含 memory type、importance 和某种去重/覆盖依据。

## Open Questions

* （当前无阻塞性开放问题，待最终确认后进入实现阶段）

## Requirements (evolving)

* 明确长期记忆的职责边界，区分它与短期会话状态、checkpoint、session persistence 的责任。
* 统一长期记忆的写入与检索 contract，避免同一轮对话落入多个不一致的 memory 通道。
* 保证长期记忆注入方式符合 chat-first runtime：结构化、按需注入、不污染 `messages`。
* 输出可执行的技术方案，能映射到仓库现有模块边界，而不是引入脱离当前项目风格的新分层。
* 设计必须覆盖统一后端、迁移策略、数据模型、检索接口和运行时注入路径。
* 第一阶段需包含基础治理能力，但范围应收敛到自动去重/冲突处理/重要性字段/基础观测，不默认扩展到完整后台运营系统。
* 主聊天流、support 流和 session 侧的记忆抽取入口必须统一，不再各自维护一套写入逻辑。
* MVP 需要包含稳态保障：迁移回滚、调试观测和脏数据/冲突数据处理。
* 一期采用项目自有 Postgres 记忆系统作为主路径；Session 作为事实源的投影式长期记忆重建能力留作后续演进目标。
* 一期长期记忆采用“纯事实卡片模型”：
  * 长期记忆主表只保存可复用的原子事实/偏好
  * 不把 `session_summary` 或整段任务纪要作为长期记忆主形态
  * 任务连续性优先由 session persistence 承担
* 一期长期记忆的作用域限定为“用户稳定事实 / 用户偏好”：
  * 不把任务级临时状态作为长期记忆主表内容
  * 不把共享 workspace/repo 事实混入用户长期记忆
* 一期调试/治理入口采用“读 + 人工失效/删除”：
  * 允许查看事实卡片、来源、命中原因、冲突状态
  * 允许将脏数据标记失效或删除
  * 不允许一期直接在线编辑事实内容
* 一期事实卡片准入规则采用最保守策略：
  * 只收录用户明确表达的稳定事实 / 用户偏好
  * 不接受基于行为模式的推断
  * 不接受模型高置信猜测
  * 进一步要求存在明确记忆意图，例如“记住”“以后请一直这样”“我的长期偏好是”

## Acceptance Criteria (evolving)

* [ ] 明确给出长期记忆系统的目标边界、输入输出 contract 和核心数据流。
* [ ] 明确给出当前实现中的重复路径、冲突点和需要收口的模块。
* [ ] 明确给出 1 个推荐方案和备选方案，并说明权衡。
* [ ] 明确给出 MVP 范围与显式 out-of-scope。
* [ ] 明确给出全量重构第一阶段与后续阶段的拆分方式，避免一次性过大改动。
* [ ] 明确给出基础治理的最小规则集合和对应可观测入口。
* [ ] 明确给出跨场景统一写入入口和迁移/回滚方案。
* [ ] 明确给出一期与后续“session 为事实源”的边界，避免一期设计阻断后续演进。
* [ ] 明确给出事实卡片的允许类型和不允许进入长期记忆主表的内容范围。
* [ ] 明确给出一期长期记忆的作用域边界与非目标范围。
* [ ] 明确给出事实卡片的准入规则与人工失效/删除的审计边界。
* [ ] 明确给出“明确表达”的判定标准和写入触发条件。
* [ ] 最终需求说明经用户确认，可进入实现前研究与上下文配置。

## Definition of Done (team quality bar)

* 设计结论能落到具体代码模块与可测试 contract
* 涉及的跨层边界有明确的数据格式和错误处理
* 实现阶段需要补充/更新测试
* 如果行为变化影响已有设计约束，需要同步更新文档或 specs

## Out of Scope (explicit)

* 现阶段不直接开始大范围实现，先完成需求和方案收敛
* 不把短期 session/checkpointer 设计与长期记忆混为一个系统
* 不在尚未确认范围前引入新的外部基础设施或供应商依赖

## Technical Notes

* 当前已检查文件：
  * `tools/core/memory_client.py`
  * `main.py`
  * `agent/application/state.py`
  * `agent/runtime/nodes/prompting.py`
  * `agent/domain/state.py`
  * `common/session_store.py`
  * `common/persistence_schema.py`
  * `support_agent.py`
  * `tests/test_agent_state_slices.py`
  * `tests/test_agent_prompt_runtime_context.py`
* 当前已检查设计/规范：
  * `docs/superpowers/specs/2026-04-06-agent-chat-first-runtime-design.md`
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`
* 重要约束：
  * 仓库 backend 仍以 `main.py` 为组合根，避免凭空引入 controller/service/repository 分层
  * 当前 `.trellis/spec/frontend/index.md` 缺失，因此本轮先按后端/跨层语境收敛问题

## Research Notes

### 当前系统诊断

基于当前仓库证据，现有“长期记忆”实现明显偏离成熟 agent memory / application memory 的一般形态，更像“多路历史文本缓存”而不是统一的长期记忆系统。

### 偏离点

* 记忆单元不清晰：
  * `add_memory_entry(final_report)` 直接写整段最终回答
  * `store_interaction(input_text, final_report)` 直接写整轮对话拼接文本
  * `_store_add(input_text, final_report, ...)` 再写一份 query/content
  * 这不是稳定的记忆原子，更接近原始日志片段
* 双轨甚至三轨写入：
  * LangGraph store 一套
  * `tools/core/memory_client.py` 一套
  * `support_chat` / `support_agent.py` 还各自走不同路径
* 语义层缺失：
  * 没有明确区分 preference / profile / fact / task context / summary
  * 没有 importance、source、scope、freshness、conflict state 等治理字段
* 检索层过弱：
  * 一条路径是最近项反转返回
  * 一条路径依赖外部 mem0 搜索
  * 没有统一 ranking、过滤、去重、作用域控制
* 生命周期缺失：
  * 没有 consolidation、overwrite、decay、archive、delete、invalidated 等机制
* 可观测与调试不足：
  * 只有 `/api/memory/status` 这类后端状态，不足以解释“为什么命中了这条记忆”
* 与 session / runtime 边界仍不够清晰：
  * 虽然 runtime 已收敛到 `memory_context` 注入，但长期记忆的生成、存储、检索仍是拼接式实现

### 结论

这说明当前系统已经不适合继续在现有抽象上局部修补，更合理的方向是：

* 定义统一 memory contract
* 定义明确的 memory entry 数据模型
* 统一写入/检索/注入入口
* 把 session、support、chat 的 memory 生产过程纳入同一治理规则

### Constraints from our repo/project

* `main.py` 是组合根，适合保留 runtime wiring，但不适合继续承载 memory 读写细节。
* `common/session_store.py` 已经建立了“项目自有 Postgres 表 + runtime-managed DDL + 直接 psycopg”的持久化模式。
* 当前长期记忆却走 LangGraph store 抽象，说明仓库里已经存在“session 是项目自有模型，memory 不是”的不一致。
* graph runtime 已经接受 `store=...`，所以如果短期内不替换底层 store，也有技术路径包裹统一服务层。
* 既然 MVP 包含迁移/回滚/调试观测/脏数据处理，底层存储必须支持比“存一段文本然后 search”更强的查询和治理能力。

### Feasible approaches here

**Approach A: 项目自有 Postgres 记忆系统** (Recommended)

* How it works:
  * 新增项目自有 memory 表与适配器，例如 `common/memory_store.py`
  * 统一定义 `MemoryEntry` 数据模型和 `MemoryService`
  * chat / support / session 全部通过统一写入入口产生命忆
  * LangGraph store 与 mem0 仅作为迁移源或兼容读路径，最终退出主路径
* Pros:
  * 最适合做去重、冲突覆盖、importance/type/scope 等基础治理
  * 最适合做观测、回滚、人工调试接口
  * 与现有 `SessionStore` 模式一致，项目边界清晰
* Cons:
  * 需要新增 DDL、迁移逻辑和更多测试
  * 一期改动面最大

**Approach B: 保留 LangGraph Store，外包统一 MemoryService**

* How it works:
  * 底层继续使用 `PostgresStore/RedisStore`
  * 项目内新增 `MemoryService`，统一 chat / support / session 的记忆写入和召回
  * 治理逻辑尽量在服务层完成
* Pros:
  * 对现有 runtime 侵入较小
  * 可以继续保留多后端能力
* Cons:
  * 底层可查询性与治理能力受限
  * 迁移/回滚/冲突解释会比较别扭
  * 很容易继续停留在“包了一层但本质还是缓存文本”的状态

**Approach C: Session 为事实源，长期记忆为投影层**

* How it works:
  * 把 session/message 作为唯一事实源
  * 长期记忆由抽取管道从 session 中投影生成
  * 记忆可重建、回放和再提炼
* Pros:
  * 审计和回滚能力最强
  * 长期形态最干净，适合后续高级治理
* Cons:
  * 一期复杂度过高
  * 需要引入抽取管线、重放策略、幂等机制

### Current recommendation

推荐先采用：

* **一期主方案：Approach A**
* **长期演进目标：吸收 Approach C 的“session 为事实源”思想**

理由：

* 它最符合“全量重构 + 基础治理 + 跨场景一致性 + 稳态保障”的当前范围
* 它能在一期就把 memory 从“双轨缓存”提升为“项目自有可治理模型”
* 它不会像 Approach C 那样一次性把范围拉爆，但又为后续投影式演进留空间

## Code-Spec Depth Check

### Target Code-Spec Files To Update

* `common/persistence_schema.py`
* `common/memory_store.py` (new)
* `common/memory_service.py` (new)
* `common/session_service.py`
* `main.py`
* `support_agent.py`
* `tests/test_*.py` covering memory store, service, API auth, ingestion, runtime context

### Concrete Contract

#### Persistence Contract

`memory_entries`

* `id: UUID`
* `user_id: TEXT`
* `memory_type: TEXT` (`preference` | `user_fact`)
* `content: TEXT`
* `normalized_key: TEXT`
* `source_kind: TEXT`
* `source_thread_id: TEXT`
* `source_message: TEXT`
* `importance: INTEGER`
* `status: TEXT` (`active` | `invalidated`)
* `retrieval_count: INTEGER`
* `last_retrieved_at: TIMESTAMPTZ | NULL`
* `invalidated_at: TIMESTAMPTZ | NULL`
* `invalidation_reason: TEXT`
* `metadata: JSONB`
* `created_at: TIMESTAMPTZ`
* `updated_at: TIMESTAMPTZ`

Unique key:

* `(user_id, memory_type, normalized_key)`

`memory_entry_events`

* `id: UUID`
* `entry_id: UUID | NULL`
* `user_id: TEXT`
* `event_type: TEXT` (`ingested` | `invalidated` | `deleted` | `migration_skipped` | `migration_completed`)
* `actor_type: TEXT`
* `actor_id: TEXT`
* `reason: TEXT`
* `payload: JSONB`
* `created_at: TIMESTAMPTZ`

`memory_user_migrations`

* `user_id: TEXT`
* `source: TEXT`
* `status: TEXT`
* `imported_count: INTEGER`
* `skipped_count: INTEGER`
* `details: JSONB`
* `updated_at: TIMESTAMPTZ`

Primary key:

* `(user_id, source)`

#### Service Contract

`MemoryService`

* `ingest_user_message(user_id, text, source_kind, thread_id=None) -> list[dict]`
* `build_runtime_context(user_id, query, limit=None) -> dict[str, list[str]]`
* `debug_context(user_id, query, limit=None) -> dict[str, Any]`
* `list_entries(user_id, limit, status=None) -> list[dict]`
* `invalidate_entry(user_id, entry_id, actor_id, reason) -> dict | None`
* `delete_entry(user_id, entry_id, actor_id, reason) -> bool`
* `list_events(user_id, entry_id=None, limit=50) -> list[dict]`

#### API Contract

* `GET /api/memory/status`
* `GET /api/memory/entries`
* `GET /api/memory/context`
* `POST /api/memory/entries/{entry_id}/invalidate`
* `DELETE /api/memory/entries/{entry_id}`

### Validation And Error Matrix

* `503`:
  * memory store / memory service 未配置
* `400`:
  * 无效状态筛选值
  * `invalidate` 请求体不合法
* `403`:
  * 内部鉴权开启时，访问了其他 `principal_id` 的记忆
* `404`:
  * 目标记忆条目不存在
* `500`:
  * 数据库初始化、查询或更新失败
* 降级规则:
  * 无 memory store 时不影响聊天主流程，记忆检索返回空，写入跳过并记录 warning/debug

### Good / Base / Bad Cases

* Good:
  * 用户说“请记住我喜欢简洁回答”
  * 系统写入一条 `preference` 卡片
  * 后续 `build_runtime_context()` 能在 prompt 中注入该偏好
* Base:
  * 普通聊天消息不包含显式记忆意图
  * 系统不写入长期记忆，但正常返回已有 memory context
* Bad:
  * 用户说“记住这次任务先改 main.py”
  * 因为这是任务级临时状态，不写入长期记忆；必要时记录 `migration_skipped` 或 ingestion skip reason

## Research Output

### Relevant Specs

* `.trellis/spec/backend/directory-structure.md`: 确认新增 memory store/service 应放在 `common/`，`main.py` 只保留组合与路由
* `.trellis/spec/backend/database-guidelines.md`: 确认使用 runtime-managed DDL、直接 `psycopg`、`Jsonb`
* `.trellis/spec/backend/error-handling.md`: 确认基础设施异常包装与 API 边界错误形态
* `.trellis/spec/backend/logging-guidelines.md`: 确认 memory 初始化、迁移、治理操作的日志级别和字段
* `.trellis/spec/backend/quality-guidelines.md`: 确认本次需要补 persistence/API/regression tests
* `.trellis/spec/guides/cross-layer-thinking-guide.md`: 确认 memory 数据在 API/service/store/runtime prompt 间的边界
* `.trellis/spec/guides/code-reuse-thinking-guide.md`: 确认不要继续复制聊天、support、session 三套 memory 写入逻辑

### Code Patterns Found

* 持久化适配器模式:
  * `common/session_store.py`
* 服务层模式:
  * `common/session_service.py`
* runtime-managed DDL:
  * `common/persistence_schema.py`
* graph/runtime 组合根:
  * `main.py`
  * `agent/runtime/graph.py`
* 结构化 prompt 上下文注入:
  * `agent/application/state.py`
  * `agent/runtime/nodes/prompting.py`
* 内部 API 鉴权与 principal 过滤:
  * `main.py` sessions/triggers routes
  * `tests/test_internal_api_auth.py`
  * `tests/test_sessions_api_auth_filter.py`
* 配置与初始化测试模式:
  * `tests/test_checkpointer_config.py`

### Files To Modify

* `common/persistence_schema.py`: 增加 memory DDL
* `common/memory_store.py`: 新增长期记忆持久化适配器
* `common/memory_service.py`: 新增长期记忆服务、抽取规则、迁移与调试逻辑
* `common/session_service.py`: 将 user message 写入与 memory ingestion 收口
* `main.py`: 初始化 memory store/service、替换旧 memory 主路径、增加 debug/admin API
* `support_agent.py`: 改为消费结构化 memory context，不再自带旧 memory 逻辑
* `tests/test_checkpointer_config.py`: 更新 memory store 初始化断言
* `tests/test_internal_api_auth.py`: 扩展 memory 新接口鉴权测试
* `tests/` 新增 memory store/service/API/runtime context 回归测试

## Decision (ADR-lite)

**Context**:
当前长期记忆实现存在双轨/三轨写入、语义粒度混乱、治理能力缺失的问题；而本次任务范围已经明确包含统一底座、基础治理、跨场景一致性和稳态保障。

**Decision**:
一期采用 **Approach A：项目自有 Postgres 记忆系统** 作为主路径；
后续演进目标保留 **Approach C：Session 为事实源，长期记忆为投影层**。

**Consequences**:
* 一期需要新增自有 memory 持久化模型、统一写入/检索服务和迁移逻辑。
* 现有 LangGraph store 与 mem0 路径不再作为主读写路径，最多保留兼容/迁移用途。
* 一期不会直接实现完整投影重建系统，但数据模型和接口必须为该演进保留空间。

## Semantic Direction

**Chosen semantic unit**: 纯事实卡片模型

* 长期记忆以原子化 fact/preference card 为主
* 不以会话摘要或任务摘要作为长期记忆主载体
* session summary / task narrative 保留在 session 层，后续如需投影到长期记忆，必须先提炼成结构化事实

**Chosen scope for phase 1**: 仅覆盖用户稳定事实 / 用户偏好

* 例如：回答风格偏好、稳定使用习惯、明确声明的长期约束
* 不包括：当前任务进度、单次会话纪要、repo 共享知识、临时执行状态

## Governance Direction

**Chosen admin/debug capability for phase 1**: 读 + 人工失效/删除

* 调试接口复用现有内部 API 鉴权与 `principal_id` 隔离模式
* 支持查看记忆条目、来源、命中原因、冲突/失效状态
* 支持对错误记忆执行失效或删除
* 一期不支持直接编辑事实内容，避免把治理入口膨胀成后台运营系统

## Ingestion Direction

**Chosen admissibility rule for phase 1**: 只接收用户明确表达的稳定事实 / 偏好

* 不基于多轮行为模式自动推断
* 不接受模型主观归纳出的“可能偏好”
* 宁可漏记，也不把长期记忆写脏
* 只有当用户表达中包含明确的“记忆意图”时才触发写入
