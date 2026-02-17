# Evidence Passages (Standard Metadata) + Render Auto Heuristics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add heading/page metadata to evidence passages (for better frontend evidence UX) and improve render `auto` heuristics to detect interstitial pages and trigger Playwright crawling.

**Architecture:** Keep `/api/sessions/{thread_id}/evidence` as the single frontend contract. DeepSearch writes enriched passages into `deepsearch_artifacts.passages`; FastAPI response model exposes optional passage metadata fields; TS types are generated from OpenAPI.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, pytest/monkeypatch, existing Playwright crawler (`tools/crawl/crawler.py`), openapi-typescript for `web/lib/api-types.ts`.

---

## Phase 1 — Passage headings (markdown-only) with stable offsets

### Task 1: Add markdown heading extraction in `split_into_passages()`

**Files:**
- Modify: `agent/workflows/evidence_passages.py`
- Test: `tests/test_evidence_passages_headings.py`

**Step 1: Write the failing test**

Create `tests/test_evidence_passages_headings.py`:

```python
from agent.workflows.evidence_passages import split_into_passages


def test_split_into_passages_includes_heading_for_markdown():
    md = "# Intro\n\nAlpha.\n\n## Details\n\nBeta.\n\nGamma.\n"
    passages = split_into_passages(md, max_chars=40)
    assert passages

    # Find the first passage that contains "Alpha"
    alpha = next(p for p in passages if "Alpha" in p["text"])
    assert alpha.get("heading") == "Intro"

    beta = next(p for p in passages if "Beta" in p["text"])
    assert beta.get("heading") == "Details"
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_evidence_passages_headings.py`  
Expected: FAIL (missing `heading` field / always None)

**Step 3: Implement minimal heading logic**

Update `split_into_passages()` to:
- Detect markdown headings via regex `(?m)^(#{1,6})\\s+(.+?)\\s*$`
- Track the “current heading” while iterating paragraph spans
- For each emitted passage dict, include `heading` (string) when available
- Keep `start_char/end_char` semantics unchanged

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_evidence_passages_headings.py`  
Expected: PASS

**Step 5: Commit**

```bash
git add agent/workflows/evidence_passages.py tests/test_evidence_passages_headings.py
git commit -m "feat(evidence): add markdown heading context to passages"
```

---

## Phase 2 — Enrich DeepSearch passages with page metadata

### Task 2: Add `page_title/retrieved_at/method` to passages in `_build_fetcher_evidence()`

**Files:**
- Modify: `agent/workflows/deepsearch_optimized.py`
- Test: `tests/test_deepsearch_fetcher_evidence.py`

**Step 1: Update the failing test**

Extend `tests/test_deepsearch_fetcher_evidence.py` to include page metadata and assert it appears on passages:

```python
assert passages[0].get("page_title") == "Example Title"
assert passages[0].get("retrieved_at") == "2026-02-17T00:00:00+00:00"
assert passages[0].get("method") == "direct_http"
```

Also update the `FakePage` to expose `title` and `retrieved_at` fields in `to_dict()`.

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_deepsearch_fetcher_evidence.py`  
Expected: FAIL (fields missing)

**Step 3: Implement minimal enrichment**

In `_build_fetcher_evidence()`:
- When building `enriched` passage dict, add:
  - `page_title`: from `page.title` (or dict field)
  - `retrieved_at`: from `page.retrieved_at` (or dict field)
  - `method`: from `page.method`
- Preserve existing keys and behavior (dedupe + offsets)

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_deepsearch_fetcher_evidence.py`  
Expected: PASS

**Step 5: Commit**

```bash
git add agent/workflows/deepsearch_optimized.py tests/test_deepsearch_fetcher_evidence.py
git commit -m "feat(deepsearch): enrich passages with page metadata"
```

---

## Phase 3 — OpenAPI contract (EvidencePassageItem optional fields)

### Task 3: Extend `EvidencePassageItem` model and assert it survives the API

**Files:**
- Modify: `main.py`
- Modify: `tests/test_session_evidence_api.py`
- Modify: `tests/test_openapi_contract.py`

**Step 1: Update `tests/test_session_evidence_api.py` to include new fields**

Add `heading/page_title/retrieved_at/method` into the `artifacts["passages"][0]` dict and assert they are present in the HTTP response JSON.

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_session_evidence_api.py::test_session_evidence_includes_fetched_pages_and_passages`  
Expected: FAIL (Pydantic drops unknown passage fields)

**Step 3: Implement model changes**

Update `EvidencePassageItem` in `main.py`:

```python
class EvidencePassageItem(BaseModel):
    url: str
    text: str
    start_char: int
    end_char: int
    heading: Optional[str] = None
    page_title: Optional[str] = None
    retrieved_at: Optional[str] = None
    method: Optional[str] = None
```

**Step 4: Extend OpenAPI contract test**

In `tests/test_openapi_contract.py`, resolve `EvidencePassageItem` schema and assert it has the new optional properties.

**Step 5: Run tests to verify they pass**

Run:
- `pytest -q tests/test_session_evidence_api.py`
- `pytest -q tests/test_openapi_contract.py`

Expected: PASS

**Step 6: Commit**

```bash
git add main.py tests/test_session_evidence_api.py tests/test_openapi_contract.py
git commit -m "feat(api): add standard metadata fields to evidence passages"
```

---

## Phase 4 — Render `auto` heuristics for interstitial pages

### Task 4: Trigger render on Cloudflare / access-denied interstitial templates

**Files:**
- Modify: `tools/research/content_fetcher.py`
- Test: `tests/test_content_fetcher_render_heuristics.py`

**Step 1: Add failing tests**

Add a test case that returns a long HTML page containing typical Cloudflare interstitial copy (so it exceeds `render_min_chars`), and assert `render_crawler` is used.

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_content_fetcher_render_heuristics.py`  
Expected: FAIL (still returns `direct_http`)

**Step 3: Implement minimal heuristic expansion**

Extend `_looks_like_javascript_interstitial()` to match high-confidence phrases like:
- "just a moment"
- "checking your browser"
- "verify you are human"
- "access denied"
- "captcha"

**Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_content_fetcher_render_heuristics.py`  
Expected: PASS

**Step 5: Commit**

```bash
git add tools/research/content_fetcher.py tests/test_content_fetcher_render_heuristics.py
git commit -m "feat(research): auto-render common interstitial pages"
```

---

## Verification Gate (before claiming done)

Backend:
- `make test`

Contract drift:
- `bash scripts/check_openapi_ts_types.sh`

Frontend:
- `pnpm -C web install --frozen-lockfile`
- `pnpm -C web lint`
- `pnpm -C web build`

