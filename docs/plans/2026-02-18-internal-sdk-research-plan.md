# Weaver Internal SDK (TS + Python) — Research Core Implementation Plan (Top 20)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Weaver 增加可复用的内部 SDK（TypeScript + Python），覆盖 Research 核心能力（chat SSE / research / sessions / evidence / export），并把 SDK 的类型与后端 OpenAPI 严格对齐（漂移门禁扩展到 SDK）。

**Architecture:** Contract-first（FastAPI OpenAPI → `openapi-typescript`）+ Thin SDK（fetch/httpx wrapper + SSE 解析）+ Milestone commits（≤5）+ Tests（SSE parser + client error handling）。

**Tech Stack:** Python 3.11, FastAPI OpenAPI, httpx, pytest, TypeScript, openapi-typescript (via `web`), Node 20, pnpm.

---

## Baseline Setup (worktree)

- Worktree (this plan assumes you are in it):
  - `~/.config/superpowers/worktrees/Weaver/codex/internal-sdk-research-20260218`
- Reuse repo venv (local-only, do not commit):
  - `ln -s /Users/luke/code/Weaver/.venv .venv`
- Baseline verify:
  - `make test` (should be green before changes)

---

## Milestone Commit Policy (≤ 5)

- **Milestone 1 (docs):** design + plan + docs updates
- **Milestone 2 (sdk-core):** TS+Python SDK skeleton + SSE parser + core client wrapper
- **Milestone 3 (sdk-research):** Research-core endpoints + examples
- **Milestone 4 (contract):** OpenAPI drift guard extended to SDK + CI adjustments (if needed)
- **Milestone 5 (polish):** final docs + troubleshooting (optional)

---

## Phase 1 — Docs (Tasks 1–3)

### Task 1: Add SDK Design Doc

**Files:**
- Create: `docs/plans/2026-02-18-internal-sdk-research-design.md`

**Steps:**
1. Ensure design doc exists and matches current decision:
   - TS+Python, internal-only, Research core only, thin SDK, SSE-first, OpenAPI drift guard.
2. Verify: `git diff --check`

---

### Task 2: Add This Implementation Plan

**Files:**
- Create: `docs/plans/2026-02-18-internal-sdk-research-plan.md`

**Steps:**
1. Ensure plan contains 20 tasks, milestone commit strategy, and exact file paths.
2. Verify: `git diff --check`

---

### Task 3: Commit Milestone 1 (Docs)

**Files:**
- Stage: `docs/plans/2026-02-18-internal-sdk-research-design.md`
- Stage: `docs/plans/2026-02-18-internal-sdk-research-plan.md`

**Steps:**
1. Stage docs:
   - `git add docs/plans/2026-02-18-internal-sdk-research-design.md docs/plans/2026-02-18-internal-sdk-research-plan.md`
2. Commit:
   - `git commit -m "docs(sdk): add internal sdk design and plan"`

---

## Phase 2 — TypeScript SDK Core (Tasks 4–10)

### Task 4: Create TypeScript SDK Package Skeleton

**Files:**
- Create: `sdk/typescript/package.json`
- Create: `sdk/typescript/tsconfig.json`
- Create: `sdk/typescript/src/index.ts`
- Create: `sdk/typescript/src/client.ts`
- Create: `sdk/typescript/src/sse.ts`
- Create: `sdk/typescript/src/types.ts`

**Steps:**
1. Add minimal package metadata (private, internal):
   - exports `dist/index.js` + `dist/index.d.ts`
2. Add TS config for `dist/` output + declarations.
3. Add placeholder exports in `src/index.ts`.
4. Add `WeaverClient` skeleton in `src/client.ts` (baseUrl, headers, `requestJson`).
5. Add SSE parser skeleton in `src/sse.ts` (pure parser first).

---

### Task 5: Add TS Unit Test for SSE Frame Parsing (RED)

**Files:**
- Create: `sdk/typescript/test/sse.test.mjs`

**Steps:**
1. Write failing test for parsing a single frame:
   - input: `id: 3\nevent: text\ndata: {"type":"text","data":{"content":"hi"}}\n\n`
   - expect: `{ id: 3, event: "text", data: { type: "text", ... } }`
2. Run (expect FAIL, module missing / function not implemented):
   - `node sdk/typescript/test/sse.test.mjs`

---

### Task 6: Implement TS SSE Frame Parser (GREEN)

**Files:**
- Modify: `sdk/typescript/src/sse.ts`
- Test: `sdk/typescript/test/sse.test.mjs`

**Steps:**
1. Implement pure function:
   - `parseSseFrame(frame: string): { id?: number; event?: string; data?: unknown } | null`
2. Rules:
   - ignore empty lines and comment lines starting with `:`
   - accept multiple `data:` lines (join with `\n`)
   - JSON parse `data`
3. Re-run:
   - `node sdk/typescript/test/sse.test.mjs` (expect PASS)

---

### Task 7: Implement TS Fetch Wrapper + Errors

**Files:**
- Modify: `sdk/typescript/src/client.ts`
- Modify: `sdk/typescript/src/types.ts`

**Steps:**
1. Add `WeaverApiError` with:
   - `status`, `bodyText`, `path`
2. Implement:
   - `requestJson<T>(path, init) -> Promise<T>`
   - default headers: `Accept: application/json`
3. Add basic `AbortSignal`/timeout support (optional, but keep minimal).

---

### Task 8: Add TS Stream Reader (SSE over fetch)

**Files:**
- Modify: `sdk/typescript/src/sse.ts`

**Steps:**
1. Implement:
   - `async function* readSseEvents(response: Response): AsyncGenerator<SseEvent>`
2. Buffer rules:
   - normalize `\r\n` → `\n`
   - split frames by `\n\n`
3. Yield parsed events in order.

---

### Task 9: Add TS Research-Core Client Methods (Signatures First)

**Files:**
- Modify: `sdk/typescript/src/client.ts`
- Modify: `sdk/typescript/src/types.ts`

**Steps:**
1. Add methods (initially typed loosely, tighten once OpenAPI types land):
   - `chatSse(payload) -> AsyncGenerator<StreamEvent>`
   - `research(payload) -> Promise<unknown>`
   - `listSessions()`, `getSession(threadId)`
   - `getEvidence(threadId)`
   - `export(threadId, params?)`, `listExportTemplates()`
2. Keep payload/response types in `types.ts`.

---

### Task 10: Build TS SDK to `dist/` (No Publishing)

**Files:**
- Create: `sdk/typescript/scripts/build.sh`
- Modify: `sdk/typescript/package.json`

**Steps:**
1. Build script uses repo toolchain:
   - `pnpm -C web exec tsc -p sdk/typescript/tsconfig.json`
2. Run build:
   - `bash sdk/typescript/scripts/build.sh`
3. Ensure outputs:
   - `sdk/typescript/dist/index.js`
   - `sdk/typescript/dist/index.d.ts`

---

## Phase 3 — Python SDK Core (Tasks 11–16)

### Task 11: Create Python SDK Package Skeleton

**Files:**
- Create: `sdk/python/pyproject.toml`
- Create: `sdk/python/README.md`
- Create: `sdk/python/weaver_sdk/__init__.py`
- Create: `sdk/python/weaver_sdk/client.py`
- Create: `sdk/python/weaver_sdk/sse.py`
- Create: `sdk/python/weaver_sdk/types.py`

**Steps:**
1. Minimal packaging for internal editable install:
   - `pip install -e ./sdk/python`
2. Keep dependencies minimal:
   - `httpx` only (already in repo)

---

### Task 12: Add Python SSE Parser Unit Test (RED)

**Files:**
- Create: `tests/test_sdk_sse_parser.py`

**Steps:**
1. Add test for parsing frames including comments (keepalive):
   - input contains `: keepalive` frames and normal `event/data`.
2. Run (expect FAIL, module missing):
   - `pytest -q tests/test_sdk_sse_parser.py`

---

### Task 13: Implement Python SSE Parser (GREEN)

**Files:**
- Modify: `sdk/python/weaver_sdk/sse.py`
- Test: `tests/test_sdk_sse_parser.py`

**Steps:**
1. Implement:
   - `parse_sse_frame(frame: str) -> dict | None`
   - `iter_sse_frames(text: str) -> list[str]` (helper)
2. Rules align with TS parser.
3. Run:
   - `pytest -q tests/test_sdk_sse_parser.py` (expect PASS)

---

### Task 14: Implement Python Client Wrapper + Errors

**Files:**
- Modify: `sdk/python/weaver_sdk/client.py`
- Modify: `sdk/python/weaver_sdk/types.py`
- Create: `tests/test_sdk_client_errors.py`

**Steps:**
1. RED: test non-2xx raises `WeaverApiError` with status/body.
2. GREEN: implement `WeaverClient.request_json()` using httpx:
   - default `Accept: application/json`
   - `base_url` normalization

---

### Task 15: Implement Python Chat SSE Streaming

**Files:**
- Modify: `sdk/python/weaver_sdk/client.py`
- Create: `tests/test_sdk_chat_sse_smoke.py`

**Steps:**
1. Implement `WeaverClient.chat_sse(...)` returning generator over SSE events.
2. Unit test uses MockTransport returning a small SSE stream body.

---

### Task 16: Add Python Methods for Research / Sessions / Evidence / Export

**Files:**
- Modify: `sdk/python/weaver_sdk/client.py`

**Steps:**
1. Add methods mirroring TS names.
2. Keep payload/response types minimal (dict in v1).

---

## Phase 4 — Contract Drift Guard + Examples (Tasks 17–20)

### Task 17: Generate SDK OpenAPI Types (TypeScript) + Drift Guard

**Files:**
- Modify: `scripts/check_openapi_ts_types.sh`
- Create: `sdk/typescript/src/openapi-types.ts` (generated)
- Update: `docs/openapi-contract.md`

**Steps:**
1. Extend `scripts/check_openapi_ts_types.sh` to also generate:
   - `sdk/typescript/src/openapi-types.ts`
2. Update git diff guard to include both generated outputs.
3. Verify:
   - `bash scripts/check_openapi_ts_types.sh` (expect exit code 0)

---

### Task 18: Tighten TS Client Types to OpenAPI Types

**Files:**
- Modify: `sdk/typescript/src/client.ts`
- Modify: `sdk/typescript/src/types.ts`

**Steps:**
1. Replace loose payload/response types with:
   - `import type { components } from "./openapi-types"`
2. Prefer OpenAPI schemas for:
   - chat payloads, evidence response, sessions response, export response.

---

### Task 19: Add SDK Examples (TS + Python)

**Files:**
- Create: `sdk/typescript/examples/research.mjs`
- Create: `sdk/python/examples/research.py`

**Steps:**
1. Provide minimal usage:
   - start chat SSE, print `text` / `sources` / `done`
2. Keep examples safe (no API keys in repo).

---

### Task 20: Milestone Commits + Final Verification

**Files:**
- Stage: `sdk/**`, `scripts/check_openapi_ts_types.sh`, `docs/openapi-contract.md`, tests

**Steps:**
1. Run backend tests:
   - `make test`
2. Run OpenAPI drift guard:
   - `bash scripts/check_openapi_ts_types.sh`
3. Run frontend checks (optional):
   - `pnpm -C web lint`
4. Run TS SDK build:
   - `bash sdk/typescript/scripts/build.sh`
5. Commit milestones (≤5 total). Suggested:
   - `git commit -m "feat(sdk): add internal ts+python sdk core"`
   - `git commit -m "feat(sdk): cover research core endpoints and examples"`
   - `git commit -m "chore(contract): extend openapi drift guard to sdk types"`
   - `git commit -m "docs(sdk): add internal sdk usage notes"`

