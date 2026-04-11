# brainstorm: optimize rag system

## Goal

在现有 Weaver RAG MVP 基础上继续升级优化，使知识文件检索在效果、稳定性、运维性或性能上达到下一阶段可交付水平，而不是重做一套新的 RAG 系统。

## What I already know

* 仓库当前已经有可运行的知识文件 RAG 链路，不是从零开始。
* 后端上传与查询入口已经存在，核心 API 在 `main.py`：
  * `GET /api/knowledge/files`
  * `POST /api/knowledge/files`
  * `GET /api/knowledge/files/{file_id}/download`
* 知识文件的核心后端服务已经落在 `tools/rag/service.py`，并包含：
  * MinIO 对象存储
  * OpenAI embedding 调用
  * Milvus collection 初始化、插入和检索
  * 文件解析、切分、索引和下载
* researcher 主链路已经接入 RAG 结果，`agent/deep_research/branch_research/research_pipeline.py` 里存在 `document_from_rag_result(...)`。
* 前端 `web/components/views/Library.tsx` 和 `web/hooks/useKnowledgeFiles.ts` 已经支持知识文件上传与列表展示。
* 仓库已有针对 knowledge API、knowledge service、deep research RAG 集成的测试。
* 之前的任务 `04-10-researcher-rag-search-channel` 已经完成首期决策：Milvus + MinIO + 独立 embedding 配置 + researcher 中 `Web + RAG` 混合召回。

## Assumptions (temporary)

* 这次任务重点是“升级优化现有 RAG”，不是改产品方向。
* 这轮主目标已收敛为“入库与运维能力”，不同时推进检索质量、异步基础设施等多个大方向。
* 仍然沿用当前主链路和模块边界，除非现有设计已经明显挡路。
* 用户当前倾向同时做两类能力：
  * 删除 + 从原始对象重建索引
  * 重复文件治理 / 去重策略

## Requirements (evolving)

* 保持现有知识文件 RAG 基础能力可用。
* 本轮优化主目标为“入库与运维能力”。
* 本轮能力范围包含：
  * 删除知识文件
  * 从原始对象重建索引
  * 一种明确的重复文件治理策略
* 重复文件治理采用“严格去重”：
  * 以文件内容哈希为准
  * 命中重复时拒绝新上传
* 改动需要兼容当前 researcher 链路和现有知识文件 API/UI。
* 保持当前独立 RAG embedding 配置约束，不回退到复用主 LLM 配置。

## Acceptance Criteria (evolving)

* [ ] 本轮优化目标有清晰范围边界。
* [ ] 实现后的行为能通过自动化测试或回归测试验证。
* [ ] 现有知识文件上传、索引、researcher 检索主链路不回退。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 不重做一套新的 RAG 架构。
* 不在需求尚未收敛前同时引入多个独立大特性。
* 不默认扩成完整知识库平台、多租户权限系统或复杂运营后台。
* 本轮默认不引入完整版本历史、审批流、多租户隔离或后台任务编排系统。

## Technical Notes

* 相关代码：
  * `main.py`
  * `tools/rag/service.py`
  * `tools/rag/file_parser.py`
  * `common/knowledge_registry.py`
  * `agent/deep_research/branch_research/research_pipeline.py`
  * `web/components/views/Library.tsx`
  * `web/hooks/useKnowledgeFiles.ts`
  * `tests/test_knowledge_api.py`
  * `tests/test_knowledge_service.py`
  * `tests/test_deepsearch_researcher.py`
* 相关规范：
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/backend/error-handling.md`
  * `.trellis/spec/backend/logging-guidelines.md`
  * `.trellis/spec/backend/tool-runtime-contracts.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`
* 已观察到的现状：
  * 上传链路当前是同步逐文件处理。
  * UI 目前以“上传 + 列表”为主，未看到删除、重试、重建索引等运维动作。
  * 当前检索主要是 dense vector search，尚未看到 hybrid retrieval、metadata filter、rerank 等增强层。
  * `common/knowledge_registry.py` 当前只有 `list/get/upsert`，没有删除记录或按状态批量操作能力。
  * `web/components/library/KnowledgeFileItem.tsx` 当前操作菜单只有下载，没有运维动作入口。
  * 现有测试主要覆盖上传、下载、索引和检索契约，尚未覆盖 delete / retry / reindex / dedupe 语义。
  * `main.py` 已存在多个 `@app.delete(...)` 路由，可复用现有 API 边界风格。
  * 前端已有 `ConfirmDialog` 和条目级 `Popover` 删除交互模式，可直接复用到知识文件列表。

## Research Notes

### Constraints from our repo/project

* 现有 registry 只保存文件级元数据，没有内容哈希字段；如果要做去重，必须新增稳定指纹字段。
* 当前索引写入时已把 `file_id` 带进 Milvus 动态字段，这意味着删除/重建可以围绕 `file_id` 做单文件级清理与重建。
* 原始对象已经存进 MinIO，因此“重建索引”不必要求用户重新上传文件。
* 现有上传 API 是同步串行处理；如果这轮继续保持同步，删除和重建的接口语义会更简单、测试面更小。

### Feasible approaches here

**Approach A: 严格去重，命中重复即拒绝上传** (Recommended)

* How it works:
  * 上传前计算文件内容哈希。
  * 若存在未删除记录且哈希相同，则直接返回已有记录或 409/业务错误，阻止重复入库。
  * 删除会清理 registry、对象存储对象和该 `file_id` 对应的向量。
  * 重建索引从原始对象重新解析并重写该 `file_id` 的向量数据。
* Pros:
  * 语义最简单，运维成本最低。
  * 不会无意间把同一文件重复写进向量库。
  * 与当前“单文件单记录”模型最贴合。
* Cons:
  * 不支持“同内容不同用途”的业务场景。

**Approach B: 允许重复上传，但给出显式重复提示和标记**

* How it works:
  * 仍然计算内容哈希，但命中重复时允许继续创建新记录，只是前端高亮为 duplicate。
* Pros:
  * 对业务限制最小。
* Cons:
  * 运维面复杂度高，重复索引会继续污染 Milvus。
  * 删除和重建时更难让用户理解自己在操作哪一份副本。

**Approach C: 把重复上传解释为“覆盖/替换旧索引”**

* How it works:
  * 命中重复时不创建新记录，而是把新上传视为对现有记录的替换或 refresh。
* Pros:
  * 对用户而言接近“幂等上传”。
* Cons:
  * 需要定义更多边界：是否保留原 `file_id`、更新时间语义、失败回滚、前端提示文案。
  * 比严格去重更复杂。

## Decision (ADR-lite)

**Context**: 当前知识文件链路已经具备上传/索引/检索能力，但缺少真正的运维闭环，而且仓库内已出现同文件重复失败记录。  
**Decision**: 本轮采用“删除 + 从原始对象重建索引 + 严格内容去重”的组合方案。重复文件以内容哈希判定，命中后拒绝新增记录；删除同时清理对象存储和向量数据；重建索引复用原始对象而不是要求重新上传。  
**Consequences**: 运维语义变得清晰，重复索引不再继续污染 Milvus；代价是对历史遗留、未带哈希的旧记录不做自动迁移清洗，只从本次实现开始严格约束。

## Technical Approach

* `common/knowledge_registry.py` 增加 `content_hash` 和删除/按哈希查询能力。
* `tools/rag/service.py` 增加严格去重、Milvus 按 `file_id` 删 chunk、MinIO 删对象、重建索引入口。
* `main.py` 增加 `DELETE /api/knowledge/files/{file_id}` 和 `POST /api/knowledge/files/{file_id}/reindex`。
* `web/hooks/useKnowledgeFiles.ts`、`web/components/views/Library.tsx`、`web/components/library/KnowledgeFileItem.tsx` 接入删除和重建索引交互。
* 更新 OpenAPI 生成类型和回归测试，覆盖 upload/list/download/delete/reindex/duplicate。
