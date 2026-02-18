# Weaver Internal SDK (TS + Python) — Research Core Design (2026-02-18)

**Goal:** 在不发布 npm/pypi 的前提下，为 Weaver 提供可复用的内部 SDK（TypeScript + Python），让“Research 核心能力”可以被外部脚本/服务稳定调用，并且与后端接口严格对齐（OpenAPI 为单一真相，自动漂移门禁）。

> Scope 说明：本设计聚焦 **Research Core**（chat stream / research / sessions / evidence / export）。Documents/RAG 与 Triggers/Webhook 放到后续版本（v2/v3）。

---

## Why / 背景

当前仓库已经采用了 **contract-first** 思路：

- 后端：FastAPI OpenAPI
- 前端：`openapi-typescript` 生成 `web/lib/api-types.ts`
- CI：`scripts/check_openapi_ts_types.sh` 防止前后端漂移

但“对外复用能力”仍主要停留在 Web UI 代码层（`web/lib/api-client.ts`），当你需要：

- 在另一个服务里触发 deep research
- 在脚本里批量跑 benchmark / 回归
- 在自动化系统里消费 SSE 事件（sources/passages/quality_update）

就缺少一个稳定的、可复用的 client 层。

---

## Principles / 设计原则

1. **OpenAPI as source of truth**：SDK 的类型来源必须可追溯到后端 OpenAPI。
2. **Thin SDK（薄封装）**：以“少逻辑、强约束”为目标；避免把业务逻辑复制进 SDK。
3. **SSE-first**：Chat 默认走标准 SSE；保持 legacy 协议可兼容/可回退。
4. **No publishing**：仓库内复用（`pip install -e` / `pnpm add file:`），不引入发布流水线复杂度。
5. **Milestone commits**：分阶段提交（≤ 5），避免每个小改动都 commit。

---

## Scope (v1)

### API coverage

- Chat / Streaming
  - `POST /api/chat/sse`（标准 SSE，主要入口）
  - `POST /api/chat`（legacy 兼容，可选）
  - `POST /api/chat/cancel/{thread_id}`
  - `POST /api/chat/cancel-all`
- Deep Research
  - `POST /api/research`
- Sessions / Evidence / Export
  - `GET /api/sessions`
  - `GET /api/sessions/{thread_id}`
  - `GET /api/sessions/{thread_id}/evidence`
  - `GET /api/export/{thread_id}`
  - `GET /api/export/templates`

### Non-goals (v1)

- Documents/RAG (`/api/documents/*`)
- Triggers/Webhook (`/api/triggers/*`, `/api/webhook/*`)
- Auth 体系（先保留 header 注入扩展点，不引入具体鉴权方案）

---

## Architecture

### TypeScript SDK

目录：`sdk/typescript/`

- `src/openapi-types.ts`：由后端 OpenAPI 自动生成（`openapi-typescript`）
- `src/client.ts`：`WeaverClient`（baseUrl、headers、timeout、错误处理）
- `src/sse.ts`：SSE 解析器（fetch/ReadableStream → event generator）
- `src/index.ts`：SDK 对外导出

消费方式（内部）：

- 其他 Node/TS 项目可用 `pnpm add file:/path/to/Weaver/sdk/typescript`
- 代码引用通过 `import { WeaverClient } from "weaver-internal-sdk"`

> 注意：SDK 会产出 `dist/`（JS + d.ts）以确保被 Node 环境直接使用；生成物会提交到 git（内部复用优先，避免消费者编译 TS）。

### Python SDK

目录：`sdk/python/`

- `weaver_sdk/client.py`：`WeaverClient`（httpx，同样支持 headers 注入）
- `weaver_sdk/sse.py`：SSE 解析器（iter_bytes/aiter_bytes → event generator）
- `weaver_sdk/types.py`：轻量类型（dataclasses / TypedDict）用于关键字段约束

消费方式（内部）：

- `pip install -e ./sdk/python`

---

## Contract drift guard（OpenAPI 漂移门禁）

扩展现有 `scripts/check_openapi_ts_types.sh`：

- 在生成 `web/lib/api-types.ts` 的同时，生成 `sdk/typescript/src/openapi-types.ts`
- 然后对两份生成物都做 `git diff --exit-code`

效果：

- 后端 API 变了 → Web UI 与 SDK types 必须同步更新并提交
- “接口对齐”不再只覆盖前端，也覆盖 SDK

---

## Testing strategy

### TypeScript

- 单测：SSE frame parser（纯函数、无网络依赖）
- 构建门禁：`tsc`（确保 dist 可产出）

### Python

- 单测：SSE parser（确保 keepalive/comment、event/data/id 解析稳定）
- 客户端测试：用 httpx MockTransport 验证：
  - 非 2xx 抛出可读错误
  - JSON response 正常解析

---

## Rollout / Migration

1. 先引入 SDK（不改 Web UI）
2. 后续可选择把 Web UI 内部的 `web/lib/api-client.ts` 收敛为 SDK 的 wrapper（可选，避免破坏现有前端）

