# brainstorm: researcher RAG search channel

## Goal

在现有 Weaver Deep Research / researcher 流程里增加一条 RAG 检索通道，让 researcher 除了 Web Search 之外，还能从项目自有知识库中检索证据并参与后续 passages / synthesis 流程。

## What I already know

* 仓库已经有完整的 Deep Research 流程，核心位于 `agent/deep_research/`。
* `ResearchAgent` 当前通过 `search_func` 走统一检索入口，再由 `research_pipeline` 完成结果归一化、抓取、切分 passages、综合总结。
* 当前 `tools/search/` 已实现统一 Web Search provider 编排，但仓库内没有现成的向量库 / RAG / semantic retrieval 实现。
* `ResearchTask` 已有 `source_preferences`、`authority_preferences` 等检索偏好字段，但没有专门表达 RAG 检索来源、索引或召回策略的字段。
* 仓库存在 `common/memory_store.py`，但它是长期记忆存储，不是面向 researcher 的知识库检索层。
* `requirements.txt` 已包含 `openai`、`chromadb`、`pgvector` 等 RAG 相关依赖，但当前代码未接入 embedding / ingestion 流程。
* 仓库已有成熟的网页内容抓取与正文提取能力，核心在 `tools/research/content_fetcher.py`，更适合复用到 URL 型知识入库。
* 当前 Web 聊天附件链路只把文件转成图片附件发送，不适合作为通用文档知识入库入口。
* 当前后端没有现成的知识库文件上传 API，但已有 `python-multipart`，可自然扩展 `UploadFile` 路径。
* 现有依赖足以支撑首期文件解析，至少可覆盖 `PDF / DOCX / MD / TXT`。
* 仓库里当前没有现成 `MinIO / S3` 对象存储接入，也没有现成 Milvus 适配层，需要新增清晰的基础设施模块。

## Assumptions (temporary)

* 这次目标是“给现有 researcher 增加 RAG 检索能力”，不是新建一套独立研究系统。
* RAG 数据源首期来自外部向量库服务，而不是本地文档目录或用户聊天记忆。
* 首个 MVP 可以先支持单一知识库来源和后端能力接入，UI 可以只做最小暴露或暂不暴露复杂配置。
* 首个向量库服务固定为 Milvus。
* 首期由 Weaver 负责 query embedding 与文档入库，而不是依赖外部预处理链路。
* Web 上传界面首期放在 `Library` 视图，而不是聊天输入区。
* researcher 默认采用 `Web + RAG` 混合召回，RAG 不可用时降级为现有 Web Search。
* Milvus collection 与基础 schema 由后端自动初始化。

## Open Questions

* 首期 MinIO 中除了原始文件，是否还需要保存解析后的规范化文本副本；当前默认只要求保存原始文件。

## Requirements (evolving)

* 为 researcher 提供至少一种可运行的 RAG 检索通道。
* 首期知识源为外部向量库服务。
* 首个外部向量库服务为 Milvus。
* Weaver 负责 query embedding 与文档入库。
* 原始 `PDF / DOCX / MD / TXT` 文件需要存储到 `MinIO`。
* embedding 服务必须使用独立供应商配置，不能与主 LLM 复用同一供应商配置。
* 首期同时提供后端 ingestion API 与 Web 上传界面。
* 首期文档入库来源为本地文件上传。
* Web 上传界面放在 `Library` 视图。
* researcher 默认采用 `Web + RAG` 混合召回，并支持 RAG 故障时安全降级。
* Milvus collection/schema 由后端自动初始化。
* 检索结果要能进入现有 Deep Research 的 documents / passages / synthesis 流程，而不是旁路拼接文本。
* 方案需要尽量贴合当前 `agent/deep_research` 与 `tools/search` 的模块边界。

## Acceptance Criteria (evolving)

* [ ] researcher 能从 RAG 通道拿到标准化检索结果。
* [ ] RAG 检索结果能进入 branch research 的后续证据处理流程。
* [ ] 至少有回归测试覆盖新增检索路径和主要契约。
* [ ] 上传的原始文件可在 MinIO 中持久化并保留可追溯对象键。
* [ ] embedding 请求使用独立配置，不依赖当前 chat / deep research LLM 供应商设置。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 先不做完整知识运营后台。
* 先不做多租户权限系统，除非现有 researcher 接口已经要求。
* 先不预设多种向量数据库同时支持，除非最终方案确认必须。
* 在未明确要求前，首期不覆盖通用索引构建平台。
* 首期不做复杂知识库权限与共享策略。
* 首期不做原始文件之外的对象版本管理。

## Technical Notes

* 相关代码：
  * `agent/deep_research/agents/researcher.py`
  * `agent/deep_research/branch_research/research_pipeline.py`
  * `agent/deep_research/branch_research/runner.py`
  * `agent/deep_research/branch_research/search_runtime.py`
  * `agent/deep_research/schema.py`
  * `agent/tooling/capabilities.py`
  * `tools/search/contracts.py`
  * `tools/search/orchestrator.py`
  * `common/config.py`
  * `requirements.txt`
  * `web/components/chat/Chat.tsx`
  * `web/components/views/Library.tsx`
  * `web/components/chat/ChatInput.tsx`
* 相关规范：
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/backend/tool-runtime-contracts.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`

## Research Notes

### What similar tools do

* 仓库内的 `docs/IMPROVEMENT_PLAN_V2.md` 记录了同类项目的做法：
  * GPT-Researcher 倾向于支持本地文档分析。
  * DeerFlow 通过 RAGFlow 集成 RAG。
  * 行业内普遍是“Web Search + 私有知识源”并存，而不是单一路径替换。

### Constraints from our repo/project

* researcher 当前主链路是：
  * query planning
  * search results
  * fetch documents
  * build passages
  * synthesize
* `tools/search` 当前语义明显偏 Web Search；如果强塞 RAG，URL、provider、fetcher 语义会被拉扯。
* `research_pipeline` 后半段已经有统一的 documents / passages / source 结构，适合作为 RAG 与 Web Search 汇合点。
* 如果修改 `ResearchTask`、branch runtime 结果结构或公共 artifacts，需要遵守 `.trellis/spec/backend/tool-runtime-contracts.md` 的契约。

### Feasible approaches here

**Approach A: 在 branch runtime 新增专用 RAG retrieval 通道并与 Web Search 合流** (Recommended)

* How it works:
  * 新增 RAG 检索服务/适配器，输出标准化 `documents/sources/passages` 所需字段。
  * `ResearchAgent` / `BranchResearchRunner` 在检索阶段同时拿 Web Search 与 RAG 结果，再进入统一 ranking / synthesis。
* Pros:
  * 最贴合当前 researcher 的真实责任边界。
  * 不会把 `tools/search` 从“网页搜索”硬扩成“任意检索”大杂烩。
  * 后续可继续扩到 hybrid retrieval、RAG-only、按任务偏好切换。
* Cons:
  * 需要改动 `agent/deep_research` 的 runtime 契约，测试面更大。

**Approach B: 把 RAG 伪装成 `tools/search` 下的新 search provider**

* How it works:
  * 把知识库检索包装成类似 search provider 的结果，复用 `run_web_search` / orchestrator / ranking 入口。
* Pros:
  * 接入点浅，前半段改动少。
  * 可以快速得到“researcher 能搜到知识库内容”的 MVP。
* Cons:
  * `SearchResult` 当前是 Web Search 语义，RAG 文档的 chunk / doc id / score / fetch 行为会很别扭。
  * 后续一旦需要索引元数据、chunk provenance、过滤条件，会很快顶到抽象上限。

**Approach C: 先把 RAG 暴露成 agent tool，暂不进入 researcher branch runtime**

* How it works:
  * 新增一个工具让普通 agent 或 deep 模式显式调用 RAG 查询。
* Pros:
  * 实现最快，风险最小。
* Cons:
  * 不满足“为 researcher 提供 RAG 搜索渠道”的核心目标，因为 branch research 主链路并不会天然使用它。

## Decision (ADR-lite)

**Context**: researcher 已有稳定的 Deep Research 主链路，但当前只有 Web Search，没有知识库检索通道。  
**Decision**: 首期知识源使用外部向量库服务，首个向量库为 Milvus，且由 Weaver 负责 query embedding 与文档入库。原始文件存 MinIO，embedding 服务使用独立供应商配置。当前采用 Approach A，并默认 `Web + RAG` 混合召回。  
**Consequences**: 会引入一层新的 retrieval 契约与测试面，但能保持模块边界清晰，后续也更容易演进。

## Technical Approach

* 后端新增 Milvus 适配层，负责 collection 初始化、文档 chunk 入库、向量检索。
* 后端新增 MinIO 存储适配层，负责原始文件上传、对象键生成与元数据追踪。
* embedding 采用独立供应商配置，新增单独的 RAG embedding 配置项，不与主 LLM 配置耦合。
* researcher 在 branch runtime 中接入 RAG 检索结果，并与现有证据结构合流。
* 新增文件 ingestion API，支持上传并解析 `PDF / DOCX / MD / TXT`。
* 前端在 `Library` 视图增加知识库上传入口与基础文件列表/状态展示。
