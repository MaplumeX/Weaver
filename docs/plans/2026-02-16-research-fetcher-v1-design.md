# Research Fetcher v1 (Direct + Reader Fallback) — Evidence Passages Design

**Date:** 2026-02-16  
**Owner:** Codex + Luke  

## Goal
在不推翻现有 FastAPI + LangGraph + DeepSearch 架构的前提下，新增一个统一的“网页内容抓取/阅读层”（direct 优先、Reader 兜底、可配置），并产出可用于 claim/evidence 的 passages（证据片段），同时与现有 OpenAPI/前端对齐方式兼容。

优先级来自业务目标：
1) Web research 深度（抓取/阅读/证据片段）
2) 可靠性与性能（并发、缓存、断点、事件）
3) 搜索与排行增强（provider unify、freshness/多样性）
4) 接口对齐前端（OpenAPI single source of truth + typed client 渐进迁移）

## Non-goals
- 不做大规模重构（不替换 LangGraph、不中断现有 deepsearch 路径）。
- 不强制引入 Redis/Celery（先做 in-process 并发 + 可插拔）。
- 不把抓取正文塞进 SSE 事件（事件仅发送摘要/诊断，正文落 session artifacts）。

## Design Overview

### Fetching strategy (C)
- **Direct first**: 简单 HTTP 抓取（requests/httpx）优先。
- **Render/crawl optional**: 在判断需要 JS/渲染时才走 Playwright/crawler（复用 `tools/crawl/crawler.py` 能力）。
- **Reader fallback**: direct/render 失败时走 Reader。
  - 支持 public 与 self-hosted 两种 reader base，`.env` 控制。

### Reader selection
- `READER_FALLBACK_MODE=off|public|self_hosted|both`（默认 `both`）
- `READER_PUBLIC_BASE`（默认 public base，可配置）
- `READER_SELF_HOSTED_BASE`（你自建 reader 的 base URL）

Reader 请求只发送 URL，不发送任何用户提示词/密钥。

### Evidence primitives
- `FetchedPage`: canonical url + method + metadata + (截断后的) text/markdown + error。
- `EvidencePassage`: 对 text 分段，带 source/url/offset/heading，便于 verifier 引用。

### Reliability & performance
- 两级并发限制：全局并发 + per-domain 并发。
- 超时/最大响应体限制。
- 失败分类与仅对 transient 错误 retry。
- fetch cache：canonical url → FetchedPage（TTL 可配置，先 in-memory）。

### Observability
- 复用现有 event system（`agent/core/events.py`）新增/复用事件：
  - `source_fetch_start|done|failed`
  - `fetch_batch_summary`
- 事件 payload 只放摘要：method/latency/cache_hit/error_type。

### Frontend alignment
- 不新增大量端点；优先把 fetch/passages/诊断汇入 session evidence artifacts（`GET /api/sessions/{thread_id}/evidence`）的可选字段。
- 前端渐进式用 typed client 读取 evidence（后续任务）。

## Success criteria
- 单测覆盖：fallback 顺序、env 切换、canonicalize、并发限制、缓存命中。
- 不依赖外网：测试使用 monkeypatch/mock。
- `make test` 通过；`bash scripts/check_openapi_ts_types.sh` 通过；前端 lint/build 不回归。
