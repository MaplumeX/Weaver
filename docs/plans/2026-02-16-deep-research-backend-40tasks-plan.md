# Deep Research Backend (Evidence-First) — 40 Tasks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不推翻现有 FastAPI + LangGraph 架构的前提下，把 Weaver 的深度研究能力升级为 evidence-first（可引用、可追溯、可复核、可回归），并把后端接口与前端严格对齐（OpenAPI 为单一真相），同时新增标准 SSE Chat 流式端点（旧协议保留兼容）。

**Architecture:** Contract-first（OpenAPI → TS types 生成）+ 增量式质量门禁（citation gate / claim verifier / freshness gate）+ 可复现 benchmark/golden runner。Chat 侧新增 `/api/chat/sse`，以“翻译器”方式复用现有 `0:` 行协议逻辑，降低重写风险。

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, LangGraph, pytest/httpx, Next.js 16 + TypeScript, pnpm, openapi-typescript.

---

## Baseline Setup (pre-task)

- Worktree:
  - Create a dedicated worktree (global): `~/.config/superpowers/worktrees/Weaver/codex/deep-research-backend-40tasks-20260216`
- Backend deps:
  - `make setup`
- Baseline verify:
  - `make test` (must be green before changing behavior)

> Note: 当前仓库 `ruff check .` 存在大量历史 lint 错误，本计划以“新代码 lint 友好 + 关键改动文件尽量不新增 lint 债 + tests/contract tests 为门禁”为主，不把全仓库 lint 清零作为本轮目标。

---

## Phase 1 — OpenAPI as Source of Truth (Contract + TS Types)

### Task 1: Add OpenAPI Schema Regression Test (names + key paths)

**Files:**
- Test: `tests/test_openapi_contract.py`

**Step 1: Write the failing test**

```python
from main import app

def test_openapi_has_key_paths_and_distinct_resume_schemas():
    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/api/interrupt/resume" in paths
    assert "/api/sessions/{thread_id}/resume" in paths

    schemas = (spec.get("components", {}) or {}).get("schemas", {}) or {}
    assert "InterruptResumeRequest" in schemas
    assert "SessionResumeRequest" in schemas
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: FAIL (当前存在同名 `ResumeRequest`，OpenAPI 组件无法同时出现两个 distinct schema 名称)

**Step 3: Minimal implementation**

Leave implementation for Task 2.

**Step 4: Verify still failing**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: still FAIL

---

### Task 2: Fix Duplicate `ResumeRequest` Model Names (OpenAPI stable)

**Files:**
- Modify: `main.py`
- Test: `tests/test_openapi_contract.py`

**Step 1: Ensure the failing test exists (Task 1)**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: FAIL

**Step 2: Implement minimal schema rename**

- Rename `/api/interrupt/resume` request model:
  - `ResumeRequest` → `InterruptResumeRequest`
- Rename `/api/sessions/{thread_id}/resume` request model:
  - `ResumeRequest` → `SessionResumeRequest`

Minimal code sketch (don’t copy/paste blindly; keep fields unchanged):

```python
class InterruptResumeRequest(BaseModel):
    thread_id: str
    payload: Any
    model: Optional[str] = None
    search_mode: Optional[SearchMode | Dict[str, Any] | str] = None
    agent_id: Optional[str] = None

class SessionResumeRequest(BaseModel):
    additional_input: Optional[str] = None
    update_state: Optional[Dict[str, Any]] = None
```

Update the two endpoints to reference the new classes.

**Step 3: Run test to verify it passes**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: PASS

**Step 4: Commit**

```bash
git add main.py tests/test_openapi_contract.py
git commit -m "fix(api): stabilize OpenAPI schema names for resume requests"
```

---

### Task 3: Add Offline OpenAPI Export Script (JSON)

**Files:**
- Create: `scripts/export_openapi.py`
- Test: `tests/test_export_openapi.py`

**Step 1: Write failing test**

```python
import json

from scripts.export_openapi import build_openapi_spec

def test_build_openapi_spec_contains_openapi_version_and_chat_path():
    spec = build_openapi_spec()
    assert isinstance(spec, dict)
    assert "openapi" in spec
    assert "/api/chat" in (spec.get("paths") or {})
    json.dumps(spec)  # must be JSON-serializable
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_export_openapi.py`  
Expected: FAIL (module not found)

**Step 3: Implement minimal script**

Implement `scripts/export_openapi.py`:
- `build_openapi_spec() -> dict` returning `main.app.openapi()`
- CLI:
  - `--output <path>` (optional; default stdout)

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_export_openapi.py`  
Expected: PASS

---

### Task 4: Add OpenAPI Export CLI Smoke Test

**Files:**
- Modify: `scripts/export_openapi.py`
- Test: `tests/test_export_openapi_cli.py`

**Step 1: Write failing test**

```python
import json
import subprocess
import sys

def test_export_openapi_cli_writes_json_to_stdout():
    proc = subprocess.run(
        [sys.executable, "scripts/export_openapi.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    spec = json.loads(proc.stdout)
    assert "openapi" in spec
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_export_openapi_cli.py`  
Expected: FAIL until CLI prints spec to stdout

**Step 3: Implement minimal CLI behavior**

Ensure `python scripts/export_openapi.py` prints JSON to stdout (UTF-8, ensure_ascii=False OK).

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_export_openapi_cli.py`  
Expected: PASS

**Step 5: Commit (Task 3+4)**

```bash
git add scripts/export_openapi.py tests/test_export_openapi.py tests/test_export_openapi_cli.py
git commit -m "feat(api): add offline OpenAPI exporter"
```

---

### Task 5: Add `openapi-typescript` to Web + Generation Script

**Files:**
- Modify: `web/package.json`
- Create: `web/scripts/generate-api-types.sh`

**Step 1: Create generator script**

Create `web/scripts/generate-api-types.sh`:
- Exports OpenAPI JSON to a temp file:
  - `python scripts/export_openapi.py --output /tmp/weaver-openapi.json`
- Generates TS types:
  - `pnpm -C web exec openapi-typescript /tmp/weaver-openapi.json -o web/lib/api-types.ts`

**Step 2: Add dependency + pnpm script**

In `web/package.json`:
- Add devDependency: `openapi-typescript`
- Add script: `"api:types": "bash scripts/generate-api-types.sh"`

**Step 3: Verify**

Run:
- `pnpm -C web install --frozen-lockfile`
- `pnpm -C web api:types`

Expected:
- `web/lib/api-types.ts` created/updated

---

### Task 6: Commit Generated `web/lib/api-types.ts` + Web Lint Gate

**Files:**
- Create/Modify: `web/lib/api-types.ts`
- Verify: `web` lint/build

**Step 1: Generate types**

Run: `pnpm -C web api:types`

**Step 2: Verify web still clean**

Run:
- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`

Expected: exit code 0

**Step 3: Commit (Task 5+6)**

```bash
git add web/package.json web/pnpm-lock.yaml web/scripts/generate-api-types.sh web/lib/api-types.ts
git commit -m "feat(web): generate TS types from backend OpenAPI"
```

---

### Task 7: Add Typed Web API Client Wrapper (non-stream)

**Files:**
- Create: `web/lib/api-client.ts`
- Modify: `web/lib/api.ts`

**Step 1: Write minimal client**

Implement helpers:
- `apiFetch<T>(path, init) -> Promise<T>`
- typed endpoints:
  - `getMcpConfig()`
  - `resumeInterrupt(...)`

Use `getApiBaseUrl()`; ensure trailing slash safe.

**Step 2: Verify**

Run:
- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`

---

### Task 8: Migrate One Callsite to Typed Client (MCP Config)

**Files:**
- Modify: `web/components/settings/SettingsDialog.tsx`
- Modify: `web/components/settings/McpConfigDialog.tsx`

**Step 1: Replace raw fetch**

Replace:
- `fetch(`${getApiBaseUrl()}/api/mcp/config`)`

With:
- `getMcpConfig()` from `web/lib/api-client.ts`

**Step 2: Verify**

Run: `pnpm -C web lint`

**Step 3: Commit (Task 7+8)**

```bash
git add web/lib/api-client.ts web/lib/api.ts web/components/settings/SettingsDialog.tsx web/components/settings/McpConfigDialog.tsx
git commit -m "refactor(web): use typed api client for mcp config"
```

---

### Task 9: Add Response Models for Agents API (OpenAPI becomes useful)

**Files:**
- Modify: `main.py`
- Test: `tests/test_openapi_contract.py`

**Step 1: Extend OpenAPI contract test**

Add assertions that:
- `/api/agents` `GET` has JSON response schema with `{ agents: [...] }`

**Step 2: Implement response_model**

Add Pydantic model:
- `AgentsListResponse { agents: list[AgentProfile] }`
and set:
- `@app.get("/api/agents", response_model=AgentsListResponse)`

**Step 3: Verify**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: PASS

---

### Task 10: Add Response Models for Sessions/Comments/Versions APIs

**Files:**
- Modify: `main.py`
- Test: `tests/test_openapi_contract.py`

**Step 1: Extend OpenAPI contract test**

Add assertions that:
- `/api/sessions` returns a typed object (not bare dict with unknown shape)
- `/api/sessions/{thread_id}/comments` typed
- `/api/sessions/{thread_id}/versions` typed

**Step 2: Implement minimal response models**

Keep models small and aligned with current frontend needs:
- `SessionSummary` (id/title/updatedAt/createdAt/isPinned/summary/tags)
- `SessionsListResponse { sessions: list[SessionSummary] }`
- `Comment`, `CommentsResponse`
- `VersionEntry`, `VersionsResponse`

**Step 3: Verify**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: PASS

**Step 4: Commit (Task 9+10)**

```bash
git add main.py tests/test_openapi_contract.py
git commit -m "feat(api): add response models for agents and sessions endpoints"
```

---

## Phase 2 — Standard SSE Chat Stream (new endpoint + frontend migration)

### Task 11: Add SSE Frame Formatter Utility + Unit Tests

**Files:**
- Create: `common/sse.py`
- Test: `tests/test_sse_format.py`

**Step 1: Write failing test**

```python
from common.sse import format_sse_event

def test_format_sse_event_includes_event_and_data_and_double_newline():
    text = format_sse_event(event="status", data={"type": "status", "data": {"text": "hi"}}, event_id=3)
    assert "id: 3\n" in text
    assert "event: status\n" in text
    assert "data: " in text
    assert text.endswith("\n\n")
```

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_sse_format.py`  
Expected: FAIL (module missing)

**Step 3: Implement**

Implement `format_sse_event(event: str, data: object, event_id: int | None = None) -> str`:
- JSON dump with `ensure_ascii=False`
- One `data:` line (no multi-line JSON)
- End with `\n\n`

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_sse_format.py`  
Expected: PASS

---

### Task 12: Implement Legacy `0:` → SSE Translator + Unit Tests

**Files:**
- Create: `common/chat_stream_translate.py`
- Test: `tests/test_chat_stream_translate.py`

**Step 1: Write failing test**

```python
from common.chat_stream_translate import translate_legacy_line_to_sse

def test_translate_legacy_line_to_sse_maps_type_to_event():
    line = '0:{"type":"text","data":{"content":"hello"}}\\n'
    out = translate_legacy_line_to_sse(line, seq=1)
    assert "event: text" in out
    assert "id: 1" in out
```

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_chat_stream_translate.py`  
Expected: FAIL

**Step 3: Implement minimal translator**

Rules:
- Ignore non-`0:` lines
- Parse JSON payload: `{type, data}`
- Emit SSE frame via `format_sse_event(event=payload["type"], data=payload, event_id=seq)`

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_chat_stream_translate.py`  
Expected: PASS

**Step 5: Commit (Task 11+12)**

```bash
git add common/sse.py common/chat_stream_translate.py tests/test_sse_format.py tests/test_chat_stream_translate.py
git commit -m "feat(stream): add SSE formatter and legacy stream translator"
```

---

### Task 13: Add `/api/chat/sse` Endpoint (graceful error without API key)

**Files:**
- Modify: `main.py`
- Test: `tests/test_chat_sse_no_key.py`

**Step 1: Write failing test**

```python
import os

import pytest
from httpx import ASGITransport, AsyncClient

from main import app

@pytest.mark.asyncio
async def test_chat_sse_without_openai_key_streams_error_and_done():
    os.environ["OPENAI_API_KEY"] = ""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat/sse",
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert resp.status_code == 200
        text = resp.text
        assert "event: error" in text
        assert "event: done" in text or "event: completion" in text
```

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_chat_sse_no_key.py`  
Expected: FAIL (endpoint not found)

**Step 3: Implement endpoint**

Add:
- `@app.post("/api/chat/sse")`
- Generate `thread_id` and return `StreamingResponse(media_type="text/event-stream")`
- If `settings.openai_api_key` is empty:
  - yield SSE `error` then `done`
  - return without running graph
- Else:
  - call existing `stream_agent_events(...)`
  - for each yielded legacy line, translate to SSE via `translate_legacy_line_to_sse(...)`

Also:
- Set `X-Thread-ID` header like `/api/chat` does.

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_chat_sse_no_key.py`  
Expected: PASS

---

### Task 14: Ensure `/api/chat/sse` Emits Thread Header + Cancel Compatibility

**Files:**
- Modify: `main.py`
- Test: `tests/test_chat_sse_headers.py`

**Step 1: Write failing test**

```python
import os
import pytest
from httpx import ASGITransport, AsyncClient

from main import app

@pytest.mark.asyncio
async def test_chat_sse_sets_thread_header_even_on_error():
    os.environ["OPENAI_API_KEY"] = ""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/chat/sse", json={"messages": [{"role": "user", "content": "hi"}]})
        assert resp.headers.get("X-Thread-ID")
```

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_chat_sse_headers.py`  
Expected: FAIL until header exists

**Step 3: Implement**

Ensure `StreamingResponse(..., headers={"X-Thread-ID": thread_id, ...})`.

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_chat_sse_headers.py`  
Expected: PASS

**Step 5: Commit (Task 13+14)**

```bash
git add main.py tests/test_chat_sse_no_key.py tests/test_chat_sse_headers.py
git commit -m "feat(api): add standard SSE chat stream endpoint"
```

---

### Task 15: Add Frontend Flag to Prefer SSE Chat Stream

**Files:**
- Modify: `web/lib/api.ts`
- Modify: `web/hooks/useChatStream.ts`

**Step 1: Implement flag + endpoint selection**

- Add helper: `getChatStreamUrl()` choosing:
  - SSE: `${base}/api/chat/sse`
  - legacy: `${base}/api/chat`
based on:
- `process.env.NEXT_PUBLIC_CHAT_STREAM_PROTOCOL` = `sse | legacy` (default `sse`)

**Step 2: Verify**

Run:
- `pnpm -C web exec tsc --noEmit`

---

### Task 16: Implement SSE Parser in `useChatStream` (fetch reader)

**Files:**
- Modify: `web/hooks/useChatStream.ts`
- Modify: `web/types/chat.ts`

**Step 1: Add `StreamEvent` support**

Keep existing handlers; implement an SSE parsing path:
- Split incoming buffer by `\n\n` frames
- Extract `event:` and `data:` lines
- Parse JSON from `data: ...`
- Route by `event`/`payload.type`

**Step 2: Verify**

Run:
- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`

**Step 3: Commit (Task 15+16)**

```bash
git add web/lib/api.ts web/hooks/useChatStream.ts web/types/chat.ts
git commit -m "feat(web): consume standard SSE chat stream via fetch"
```

---

### Task 17: Update Docs for SSE Chat Stream + Env Flag

**Files:**
- Modify: `README.md`
- Create: `docs/chat-streaming.md`

**Step 1: Document**

- Explain legacy `0:` protocol vs standard SSE
- Document env:
  - `NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=sse|legacy`

**Step 2: Commit**

```bash
git add README.md docs/chat-streaming.md
git commit -m "docs: add chat streaming protocol guide"
```

---

### Task 18: Add OpenAPI Note for SSE Endpoint (best-effort)

**Files:**
- Modify: `main.py`
- Test: `tests/test_openapi_contract.py`

**Step 1: Extend contract test**

Assert `/api/chat/sse` exists in OpenAPI paths.

**Step 2: Implement**

Ensure the decorator exists and uses `responses` / docstring to clarify content type:
- `text/event-stream`

**Step 3: Verify**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: PASS

---

### Task 19: Add Chat SSE Keepalive (optional, proxy-friendly)

**Files:**
- Modify: `main.py`
- Test: `tests/test_chat_sse_keepalive.py`

**Step 1: Test**

Write unit test for helper that emits `: keepalive\n\n` every N seconds when idle (do not integration-test timing).

**Step 2: Implement**

Add small keepalive yield in SSE generator when legacy stream is quiet.

---

### Task 20: Verify Web Build After SSE Migration

**Files:**
- Verify only

**Step 1: Verify**

Run:
- `pnpm -C web build`

Expected: success

**Step 2: Commit (Task 18+19+20)**

```bash
git add main.py tests/test_openapi_contract.py tests/test_chat_sse_keepalive.py README.md docs/chat-streaming.md
git commit -m "feat(api+docs): document and harden SSE chat stream"
```

---

## Phase 3 — Evidence Outputs (Sources, Claims, Quality) + Frontend Alignment

### Task 21: Add Evidence Extractor for Message Sources

**Files:**
- Create: `agent/workflows/evidence_extractor.py`
- Test: `tests/test_evidence_extractor.py`

**Step 1: Write failing test**

```python
from agent.workflows.evidence_extractor import extract_message_sources

def test_extract_message_sources_returns_canonicalized_urls_and_titles():
    scraped = [
        {"results": [{"title": "A", "url": "https://example.com/?utm_source=x"}]}
    ]
    sources = extract_message_sources(scraped)
    assert sources[0]["url"] == "https://example.com/"
    assert sources[0]["title"] == "A"
```

**Step 2: Run (expect fail)**

Run: `pytest -q tests/test_evidence_extractor.py`  
Expected: FAIL

**Step 3: Implement**

Use `agent/workflows/source_registry.SourceRegistry` to canonicalize and dedupe; output list of dicts:
- `title`, `url`, `rawUrl?`, `domain?`, `provider?`, `publishedDate?`

**Step 4: Run (expect pass)**

Run: `pytest -q tests/test_evidence_extractor.py`  
Expected: PASS

---

### Task 22: Emit `sources` Event in Chat Streams (legacy + SSE)

**Files:**
- Modify: `main.py`
- Test: `tests/test_chat_sources_event.py`

**Step 1: Write failing unit test**

Test the helper that converts a `sources` list into a stream event payload without needing real LLM:

```python
from main import format_stream_event

import asyncio

def test_format_stream_event_sources_is_json_serializable():
    payload = asyncio.get_event_loop().run_until_complete(
        format_stream_event("sources", {"items": [{"title": "A", "url": "https://a.com"}]})
    )
    assert payload.startswith("0:")
```

**Step 2: Implement**

During `stream_agent_events(...)` finalization:
- compute sources from `result.get("scraped_content")` (or deepsearch artifacts)
- yield `format_stream_event("sources", {"items": sources})` before `completion`

**Step 3: Verify**

Run: `pytest -q tests/test_chat_sources_event.py`  
Expected: PASS

---

### Task 23: Attach `sources` to Assistant Message in Frontend

**Files:**
- Modify: `web/types/chat.ts`
- Modify: `web/hooks/useChatStream.ts`

**Step 1: Extend StreamEvent union**

Add:
- `{ type: 'sources'; data: { items: MessageSource[] } }`

**Step 2: Update stream handler**

On `sources` event:
- attach `assistantMessage.sources = items`

**Step 3: Verify**

Run:
- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`

**Step 4: Commit (Task 21+22+23)**

```bash
git add agent/workflows/evidence_extractor.py main.py tests/test_evidence_extractor.py tests/test_chat_sources_event.py web/types/chat.ts web/hooks/useChatStream.ts
git commit -m "feat(evidence): surface sources in chat stream and frontend"
```

---

### Task 24: Upgrade Claim Verifier to Output Canonical URLs (via SourceRegistry)

**Files:**
- Modify: `agent/workflows/claim_verifier.py`
- Test: `tests/test_claim_verifier.py`

**Step 1: Add failing assertion**

Add a test case ensuring evidence urls are canonicalized (strip utm).

**Step 2: Implement**

In `ClaimVerifier._extract_evidence`:
- canonicalize urls using `SourceRegistry.canonicalize_url`

**Step 3: Verify**

Run: `pytest -q tests/test_claim_verifier.py`  
Expected: PASS

---

### Task 25: Persist Claims + Sources into Session Deepsearch Artifacts

**Files:**
- Modify: `common/session_manager.py`
- Modify: `agent/workflows/deepsearch_optimized.py`
- Test: `tests/test_session_deepsearch_artifacts.py`

**Step 1: Add failing test**

Extend snapshot test to assert:
- `deepsearch_artifacts.sources` exists
- `deepsearch_artifacts.claims` exists

**Step 2: Implement**

When building deepsearch artifacts:
- store `sources` from evidence extractor
- store `claims` from claim verifier output (list of dicts)

**Step 3: Verify**

Run: `pytest -q tests/test_session_deepsearch_artifacts.py`  
Expected: PASS

**Step 4: Commit (Task 24+25)**

```bash
git add agent/workflows/claim_verifier.py common/session_manager.py agent/workflows/deepsearch_optimized.py tests/test_claim_verifier.py tests/test_session_deepsearch_artifacts.py
git commit -m "feat(evidence): canonicalize claim evidence and persist sources/claims"
```

---

### Task 26: Add Evidence API Endpoint for a Session (`/api/sessions/{id}/evidence`)

**Files:**
- Modify: `main.py`
- Test: `tests/test_session_evidence_api.py`

**Step 1: Write failing test**

Use `ASGITransport` to call endpoint for unknown session and ensure 404 (stable contract).

**Step 2: Implement**

Add endpoint that returns:
- `sources`, `claims`, `quality_summary` (if present)

**Step 3: Verify**

Run: `pytest -q tests/test_session_evidence_api.py`  
Expected: PASS

---

### Task 27: Add OpenAPI Response Model for Evidence Endpoint

**Files:**
- Modify: `main.py`
- Test: `tests/test_openapi_contract.py`

**Step 1: Extend contract test**

Assert evidence endpoint exists and has JSON schema.

**Step 2: Implement response_model**

Add Pydantic models:
- `EvidenceSource`, `EvidenceClaim`, `EvidenceResponse`

**Step 3: Verify**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: PASS

**Step 4: Commit (Task 26+27)**

```bash
git add main.py tests/test_session_evidence_api.py tests/test_openapi_contract.py
git commit -m "feat(api): expose evidence artifacts via session endpoint"
```

---

### Task 28: Add JSON Export Format for `/api/export/{thread_id}`

**Files:**
- Modify: `main.py`
- Test: `tests/test_export_json.py`

**Step 1: Write failing test**

Ensure `format=json` returns `application/json` with evidence payload.

**Step 2: Implement**

In export handler:
- if `format == "json"` → return JSONResponse with `{ report, sources, claims, quality }`

**Step 3: Verify**

Run: `pytest -q tests/test_export_json.py`  
Expected: PASS

---

### Task 29: Add Frontend “Sources” UI (minimal, non-invasive)

**Files:**
- Create: `web/components/chat/message/SourcesList.tsx`
- Modify: `web/components/chat/MessageItem.tsx`

**Step 1: Render sources when present**

- Show a collapsible list under assistant message
- Each item: title + domain, link to url

**Step 2: Verify**

Run:
- `pnpm -C web lint`
- `pnpm -C web build`

---

### Task 30: Commit Evidence + UI Updates

**Files:**
- Commit-only aggregation

**Step 1: Commit (Task 28+29+30)**

```bash
git add main.py tests/test_export_json.py web/components/chat/message/SourcesList.tsx web/components/chat/MessageItem.tsx
git commit -m "feat(evidence+ui): add json export and message sources list"
```

---

## Phase 4 — Capability Depth: More Providers + Better Ranking + Bench Signals

### Task 31: Add DuckDuckGo Provider (no API key) + Unit Tests

**Files:**
- Modify: `tools/search/providers.py`
- Test: `tests/test_duckduckgo_provider.py`

**Step 1: Write failing test**

Patch provider call with monkeypatch to avoid network; assert function exists and returns list.

**Step 2: Implement**

Add:
- `duckduckgo_search(query, max_results)` using `duckduckgo_search` package when installed (try/except import)
- Return normalized fields: title/snippet/url/source/date?

**Step 3: Verify**

Run: `pytest -q tests/test_duckduckgo_provider.py`  
Expected: PASS

---

### Task 32: Wire DuckDuckGo into MultiSearch Strategy Profiles

**Files:**
- Modify: `tools/search/multi_search.py`
- Test: `tests/test_deepsearch_multi_search.py`

**Step 1: Add failing assertion**

Ensure multi_search can include `duckduckgo` provider in fallback/general profile when no API keys.

**Step 2: Implement**

Update provider registry to include ddg when available.

**Step 3: Verify**

Run: `pytest -q tests/test_deepsearch_multi_search.py`  
Expected: PASS

**Step 4: Commit (Task 31+32)**

```bash
git add tools/search/providers.py tools/search/multi_search.py tests/test_duckduckgo_provider.py tests/test_deepsearch_multi_search.py
git commit -m "feat(search): add DuckDuckGo provider and integrate into multi-search"
```

---

### Task 33: Add Freshness Scoring to Provider-Normalized Results (published_date)

**Files:**
- Modify: `tools/search/multi_search.py`
- Test: `tests/test_multi_search_ranking.py`

**Step 1: Add failing test**

Extend ranking test to ensure results with newer `published_date` rank higher for time-sensitive queries.

**Step 2: Implement**

Ensure normalized results include `published_date` consistently across providers and ranking uses it.

**Step 3: Verify**

Run: `pytest -q tests/test_multi_search_ranking.py`  
Expected: PASS

---

### Task 34: Emit “freshness diagnostics” to frontend via quality_update

**Files:**
- Modify: `agent/workflows/quality_assessor.py`
- Test: `tests/test_deepsearch_quality_diagnostics.py`

**Step 1: Add failing assertion**

Require `quality_update` includes `freshness_summary.fresh_30_ratio` and warning field when time-sensitive.

**Step 2: Implement**

Add fields to quality summary dict and make sure events include it.

**Step 3: Verify**

Run: `pytest -q tests/test_deepsearch_quality_diagnostics.py`  
Expected: PASS

**Step 4: Commit (Task 33+34)**

```bash
git add tools/search/multi_search.py agent/workflows/quality_assessor.py tests/test_multi_search_ranking.py tests/test_deepsearch_quality_diagnostics.py
git commit -m "feat(quality): improve freshness-aware ranking and diagnostics"
```

---

### Task 35: Add OpenAPI Drift Guard (generated TS types up-to-date)

**Files:**
- Create: `scripts/check_openapi_ts_types.sh`
- Modify: `.github/workflows/ci.yml`

**Step 1: Script**

Create script:
- export openapi
- run `pnpm -C web api:types`
- fail if `git diff --exit-code web/lib/api-types.ts` non-zero

**Step 2: CI integration**

Add a step to `frontend` job after install:
- run the drift guard script

**Step 3: Verify locally**

Run:
- `bash scripts/check_openapi_ts_types.sh`

---

### Task 36: Fix CI Ruff Gate (minimally unblock) — optional but recommended

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`

**Step 1: Decide policy**

Option A (recommended): Narrow CI lint scope to high-signal rules only (E/W/F/I/B/RUF) and disable noisy mass-UP rules until repo is migrated.

**Step 2: Implement**

- Remove `UP` from `[tool.ruff.lint].select` (or add targeted ignores for `UP006`, `UP045`, `UP035` and `RUF001/2/3`), so CI becomes green and meaningful.

**Step 3: Verify**

Run:
- `make lint` (or `ruff check .`) should be close to green; if still noisy, iterate once more (don’t start mass refactors).

---

### Task 37: Add Evidence Metrics to Benchmark Runner Output

**Files:**
- Modify: `scripts/benchmark_deep_research.py`
- Test: `tests/test_deepsearch_golden_smoke.py`

**Step 1: Add failing assertion**

Expect output JSON includes:
- `metrics.citation_coverage`
- `metrics.unsupported_claims`

**Step 2: Implement**

Compute metrics based on:
- sources list
- claim verifier output

**Step 3: Verify**

Run: `pytest -q tests/test_deepsearch_golden_smoke.py`  
Expected: PASS

---

### Task 38: Add `GET /api/runs/{thread_id}` to include evidence summary (OpenAPI)

**Files:**
- Modify: `main.py`
- Test: `tests/test_openapi_contract.py`

**Step 1: Extend contract test**

Ensure runs endpoint schema contains `evidence_summary` object.

**Step 2: Implement**

Add small evidence summary:
- sources_count
- unsupported_claims_count
- freshness_ratio_30d

**Step 3: Verify**

Run: `pytest -q tests/test_openapi_contract.py`  
Expected: PASS

**Step 4: Commit (Task 35-38)**

```bash
git add scripts/check_openapi_ts_types.sh .github/workflows/ci.yml pyproject.toml scripts/benchmark_deep_research.py tests/test_deepsearch_golden_smoke.py main.py tests/test_openapi_contract.py
git commit -m "feat(contract+bench): enforce api type drift guard and evidence metrics"
```

---

### Task 39: Add `/api/chat/sse` Event: `quality_update` Mirror (optional)

**Files:**
- Modify: `main.py`
- Test: `tests/test_chat_sse_quality_events.py`

**Step 1: Write failing test**

Call SSE endpoint with no key, but ensure it emits at least one structured `quality_update` diagnostic stub (or explicitly does not — pick one and lock contract).

**Step 2: Implement**

Prefer: keep no-key path minimal (error+done) and document that quality events require real run.

**Step 3: Verify**

Run: `pytest -q tests/test_chat_sse_quality_events.py`

---

### Task 40: Final Docs + Rollout / Troubleshooting

**Files:**
- Modify: `docs/deep-research-rollout.md`
- Create: `docs/openapi-contract.md`

**Step 1: Document**

- How to regenerate TS types
- How to switch chat protocol (SSE vs legacy)
- Common failure modes (missing API keys, proxies stripping SSE, etc.)

**Step 2: Full verification (before claiming done)**

Backend:
- `make test`

Frontend:
- `pnpm -C web lint`
- `pnpm -C web build`

**Step 3: Commit**

```bash
git add docs/deep-research-rollout.md docs/openapi-contract.md
git commit -m "docs: add OpenAPI contract + rollout guidance"
```

---

## Verification Gate (Before claiming done)

- Backend:
  - `make test`
- Frontend:
  - `pnpm -C web lint`
  - `pnpm -C web build`
- API types drift:
  - `bash scripts/check_openapi_ts_types.sh`

