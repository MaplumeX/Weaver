# brainstorm: upgrade rag system

## Goal

升级当前 Weaver 的 RAG 系统，提升知识库检索质量、索引治理能力，以及与 deep research 证据链路的协同效果；在不过度重构现有 FastAPI + MinIO + Milvus 架构的前提下，给出一条可分阶段落地的演进路径。

## What I already know

* 当前知识文件元数据通过 `common/knowledge_registry.py` 写入本地 `data/knowledge_files.json`
* 原始文件存储在 MinIO，对象 key 形如 `knowledge/{file_id}/{filename}`
* 向量检索通过 `tools/rag/service.py` 中的 `KnowledgeMilvusStore` 对接 Milvus
* Embedding 由独立的 `RagEmbeddingClient` 提供，使用单独的 `rag_embedding_*` 配置
* 当前 chunk 由 `agent.foundation.passages.split_into_passages()` 基于段落和标题按字符窗口切分
* 当前 `knowledge_search` 对外只暴露 `query + max_results`，不支持 metadata filter、rerank、query rewrite 或混合检索
* Deep Research 的 `ResearchAgent` 会同时调用 web search 和 `knowledge_service.search()`，并把 RAG 结果视作 `milvus_rag` 证据源
* Deep Research branch pipeline 已有 coverage / quality / contradiction / grounding 评估，但 RAG 检索本身仍偏“单轮向量召回”

## Assumptions (temporary)

* 当前主要目标不是替换 Milvus/MinIO，而是在现有架构上提升效果和可运营性
* 用户关心的是可落地方案，而不是一次性引入大型新基础设施
* 升级应优先兼容现有 `/api/knowledge/files`、`knowledge_search` 和 deep research runtime contracts

## Open Questions

* 是否按推荐的 MVP 直接进入实现：以 `KnowledgeService.search()` 为统一增强入口，普通 `knowledge_search` 与 deep research 共同复用

## Requirements (evolving)

* 方案必须基于当前代码结构，而不是泛化的 RAG 最佳实践
* 方案需要区分短期可落地项与中长期演进项
* 方案需要说明对现有 API、数据模型、runtime artifacts 的影响范围
* 已确定优先采用方案 A：检索质量增强，不动大架构
* 已确定当前范围为 A1 + A2，不包含 A3 的 public API 扩展
* 已确定 deep research 也要同步吃到新的 query expansion / rerank 能力

## Acceptance Criteria (evolving)

* [ ] 能清楚说明当前实现的瓶颈和约束
* [ ] 至少给出 2 到 3 条可选升级路径，并说明 trade-off
* [ ] 给出推荐路径和建议的实施阶段

## Definition of Done (team quality bar)

* 方案与现有代码结构一致
* 明确 cross-layer 影响点
* 后续若进入实现，能直接拆成任务并补齐测试与文档

## Out of Scope (explicit)

* 本轮不直接改动线上基础设施
* 本轮不默认引入新的大型存储系统或搜索后端
* 本轮不一次性重写 deep research pipeline

## Technical Notes

* 核心文件：
  * `tools/rag/service.py`
  * `tools/rag/knowledge_search_tool.py`
  * `common/knowledge_registry.py`
  * `agent/deep_research/agents/researcher.py`
  * `agent/deep_research/branch_research/research_pipeline.py`
* 当前主要配置：
  * `knowledge_chunk_max_chars`
  * `knowledge_search_top_k`
  * `knowledge_milvus_collection`
  * `rag_embedding_model`
  * `rag_embedding_dimensions`
* 已知约束：
  * tool runtime contract 要求 `knowledge_search` 保持独立 public tool
  * cross-layer 变更需要显式定义 API / service / runtime artifact 边界

## Research Notes

### Current bottlenecks from code inspection

* 检索仍是单路 dense retrieval：
  * `KnowledgeService.search()` 只有 embedding -> Milvus search -> 返回命中，没有 keyword/BM25、query rewrite 或 rerank
* chunk 策略偏静态：
  * `split_into_passages()` 和 `_build_chunks_payload()` 主要按段落和固定字符窗口切块，没有 overlap、文档类型专属 chunk 规则或语义切分
* ingest 在请求路径内同步完成：
  * `/api/knowledge/files` 直接调用 `service.ingest_file()`，其中包含解析、embedding、Milvus 写入
* registry 目前是本地 JSON 文件：
  * 适合轻量元数据，但不利于高并发治理、索引版本管理和批量作业追踪
* deep research 会消费 RAG 结果，但当前 URL canonicalization 会去掉 fragment；而知识 chunk 恰好通过 `#chunk=...` 区分，这会导致同文件多 chunk 命中在排序阶段被折叠
* `knowledge_search` tool 的公开输入只有 `query` 和 `max_results`，产品面无法表达 filters、document scope、retrieval mode 或 debug signal

### Feasible approaches here

**Approach A: 检索质量增强，不动大架构** (Recommended)

* How it works:
  * 保留 MinIO + Milvus + JSON registry
  * 增加 query rewrite、hybrid recall、lightweight rerank、chunk overlap/metadata、deep research 的 chunk 级去重修正
* Pros:
  * 改动集中在 `tools/rag/` 和 deep research 排序管线
  * 对现有 API 和存储侵入较小
  * 最快看到效果提升
* Cons:
  * 运营治理能力提升有限
  * registry 和同步 ingest 的基础问题仍然在

### Selected direction

* 用户已选择方案 A 作为当前升级方向
* 用户已进一步选择当前范围为 A1 + A2

### Proposed phased plan for Approach A

**Phase A1: 低风险质量修正**

* 修复 deep research 中 knowledge chunk 的 URL 去重折叠问题
* 优化 chunk 策略：加入 overlap、标题优先切分、最小 chunk 质量门槛
* 为检索结果补充更多 ranking metadata，便于调试和后续 rerank

**Phase A2: 检索增强**

* 增加 query rewrite / query expansion
* 提升召回窗口，再做 lightweight rerank
* 评估是否在现有 Milvus 能力内加入 hybrid recall

**Phase A3: 产品面暴露可控能力**

* 视范围决定是否扩展 `knowledge_search` 输入
* 可选能力包括：`file_ids`、`include_shared`、`retrieval_mode`、`debug`

### Current implementation target

**In scope**

* 修复 deep research 对 knowledge chunk 的错误去重
* 升级 chunk 策略，至少包含 overlap 和更稳定的标题/段落边界
* 为 retrieval 增加 query rewrite / expansion
* 增加两阶段排序：先扩大召回，再做 lightweight rerank
* 尽量保持现有 `/api/knowledge/files` 与 `knowledge_search` public contract 不变
* deep research 与普通 `knowledge_search` 共用增强后的知识检索路径

**Out of scope for this iteration**

* 后台索引任务
* registry 存储层替换
* 新 public API 字段或新的 public tool

### MVP breakdown for A1 + A2

**MVP-1**

* 修复 chunk 级 URL 折叠问题
* 给 `KnowledgeService.search()` 增加内部召回窗口与 rerank 钩子
* 保持外部返回结构兼容

**MVP-2**

* 升级 `split_into_passages()` / chunk payload 生成逻辑
* 引入 query rewrite / expansion，产出多个内部查询
* 合并、去重、重排多查询结果

**MVP-3**

* 将增强后的检索能力接入 deep research 主研究链路
* 为测试补齐 knowledge service 与 deep research 回归用例

### Recommended implementation shape

* 统一入口放在 `KnowledgeService.search()`：
  * 内部生成扩展查询
  * 批量 embedding
  * 每个查询扩大召回窗口
  * 合并命中并按 `chunk_id` 去重
  * 用 lightweight rerank 输出最终 top-k
* `knowledge_search` tool 不改 public args / payload，只复用增强后的 service
* deep research 不新增独立 RAG planner：
  * 继续使用已有 `BranchQueryPlanner`
  * 每轮 query 进入 `KnowledgeService.search()` 后再进行知识检索内部扩展
* deep research 侧单独修复 knowledge chunk 去重键：
  * RAG 结果不能再按去掉 fragment 的 canonical URL 合并
  * 至少要保留 `chunk_id` 作为唯一性来源

### Expected file touch points

* `tools/rag/service.py`
* `agent/foundation/passages.py`
* `agent/deep_research/branch_research/shared.py`
* `agent/deep_research/branch_research/research_pipeline.py`
* `tests/test_knowledge_service.py`
* `tests/test_deepsearch_researcher.py`
* 视实现情况可能补 `tests/test_knowledge_tool.py`

**Approach B: 面向生产的知识库治理升级**

* How it works:
  * 在 A 的基础上，为知识文件引入索引任务、版本状态、可观测性、失败重试和更强元数据模型
  * 将 ingest/reindex 改为后台作业
* Pros:
  * 更适合文档量上涨、多人协作、频繁 reindex
  * 有利于后续做灰度索引、双写和回滚
* Cons:
  * cross-layer 影响更大
  * 需要补充任务状态 API、测试和文档

**Approach C: Deep Research 优先的一体化升级**

* How it works:
  * 把 RAG 从“一个工具”升级为 deep research 的一级证据通道
  * 增加 coverage-aware retrieval、query family expansion、evidence fusion 和 source confidence 归一化
* Pros:
  * 对 deep research 质量提升最大
  * 能让私有知识和公网证据形成统一推理链
* Cons:
  * 改动跨 `tools/rag/`、`agent/deep_research/`、runtime artifacts，复杂度最高
  * 没有先打好 A/B 基础时，实施风险偏高
