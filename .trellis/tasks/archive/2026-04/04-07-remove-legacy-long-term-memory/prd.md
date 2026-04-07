# remove legacy long-term memory system

## Goal

清理仓库中旧长期记忆系统留下的兼容逻辑和残余代码，减少双轨实现、迁移分支和废弃配置带来的复杂度。目标是让长期记忆相关实现只保留明确需要的主路径，不再为旧方案保留兼容入口。

## What I already know

* 用户要求“清除旧的长期记忆系统的残余”，并明确“不再考虑兼容”。
* 当前仓库存在项目自有长期记忆主路径：`common/memory_store.py`、`common/memory_service.py`、`main.py` 中的 `/api/memory/*` 路由与 runtime 注入逻辑。
* 当前仓库同时保留了旧兼容残余：
  * `tools/core/memory_client.py` 中的 mem0 客户端、JSON fallback、旧根目录存储迁移逻辑。
  * `main.py` 中的 `legacy_fetch_memories`、`_legacy_memory_fetcher()`、`fetch_memories()`、`add_memory_entry()`、`store_interaction()` 等兼容包装。
  * `common/memory_service.py` 中的 legacy migration 路径：`legacy_message_fetcher`、`legacy_store_loader`、`ensure_user_migrated()`、`_extract_candidate_from_legacy_text()` 等。
  * `common/config.py` 中的 `mem0_api_key`、`enable_memory`、`memory_store_backend` 的兼容语义，以及 `redis` / `memory` / `postgres` 多分支。
  * `common/persistence_schema.py` 中的 `memory_user_migrations` 表定义用于兼容迁移状态记录。
* 当前前端代码未发现直接消费 `/api/memory/*` 的业务调用，`web/lib/api-types.ts` 里只有类型声明。
* 当前支持侧流程和 agent runtime 使用的是结构化 `memory_context`，不直接依赖 mem0 客户端。

## Scope Decision

* 已确认：只删除旧兼容路径，保留当前项目自有长期记忆主路径。
* 保留内容：`/api/memory/*`、`MemoryService`、`MemoryStore`、runtime `memory_context`、session 侧显式用户记忆写入。
* 删除内容：mem0 / JSON fallback / legacy migration / 旧 helper 包装 / 冗余兼容配置。

## Requirements (evolving)

* 删除旧长期记忆系统残余代码，避免同时维护新旧两套路径。
* 删除与旧长期记忆系统绑定的兼容配置、迁移逻辑和废弃辅助函数。
* 保证改动后代码路径更单一，模块职责更清晰。
* 为被触及的行为补齐或更新回归测试。

## Relevant Specs

* `.trellis/spec/backend/directory-structure.md`: 约束清理应继续落在 `main.py` 与 `common/` 的既有职责边界内。
* `.trellis/spec/backend/database-guidelines.md`: 约束长期记忆的持久化逻辑继续由 `common/memory_store.py` 持有，并删除兼容迁移表路径。
* `.trellis/spec/backend/error-handling.md`: 约束 memory 初始化失败继续走显式 `ValueError` / `HTTPException` 路径。
* `.trellis/spec/backend/logging-guidelines.md`: 约束 memory backend 初始化日志保持高信号、低噪声。
* `.trellis/spec/guides/cross-layer-thinking-guide.md`: 约束配置、startup wiring、service、API 返回和类型生成一起收口。
* `.trellis/spec/guides/code-reuse-thinking-guide.md`: 约束删除并行旧路径，而不是继续保留壳函数或双轨入口。

## Code Patterns Found

* 运行时组合根集中在 `main.py`：memory store/service 初始化、FastAPI response model、路由和 health/status 汇总都在这里。
* 长期记忆主逻辑集中在 `common/memory_service.py` 和 `common/memory_store.py`：适合直接删 legacy migration，而不需要引入新层。
* Session 对显式用户记忆写入已经通过 `common/session_service.py` 收口：说明可以安全删除 `main.py` 里的旧 helper 包装。

## Files to Modify

* `common/config.py`: 删除 mem0 和旧 memory store 兼容配置。
* `main.py`: 删除 legacy helper、删 redis / memory_store_url 兼容分支、收紧 `/api/memory/status` 与 entries 返回。
* `common/memory_service.py`: 删除 legacy migration 路径。
* `common/memory_store.py`: 删除 migration 状态表的读写接口。
* `common/persistence_schema.py`: 删除 `memory_user_migrations` DDL。
* `tools/core/memory_client.py`: 删除旧 mem0 / JSON fallback 客户端。
* `tools/data/memory_store.json`: 删除旧 fallback 数据文件。
* `tests/*`: 删除对旧 helper / migration 的依赖，更新初始化与 API 回归测试。

## Acceptance Criteria (evolving)

* [ ] 长期记忆相关代码中不再存在旧系统兼容入口或迁移逻辑。
* [ ] 被保留的长期记忆主路径清晰可运行，或如果决定彻底移除，则系统中不再暴露长期记忆能力。
* [ ] 测试随最终范围更新并通过。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 未确认前，不做与长期记忆无关的运行时重构。
* 未确认前，不调整短期 session/checkpointer 机制。

## Technical Notes

* 已阅读：`.trellis/spec/backend/index.md`
* 已阅读：`.trellis/spec/backend/directory-structure.md`
* 已阅读：`.trellis/spec/backend/database-guidelines.md`
* 已阅读：`.trellis/spec/backend/error-handling.md`
* 已阅读：`.trellis/spec/backend/logging-guidelines.md`
* 已检查文件：`main.py`、`common/config.py`、`common/memory_service.py`、`common/memory_store.py`、`common/session_service.py`、`common/persistence_schema.py`、`tools/core/memory_client.py`、`tests/test_memory_api.py`
