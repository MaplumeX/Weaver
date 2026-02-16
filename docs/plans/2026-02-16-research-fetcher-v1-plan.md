# Research Fetcher v1 (Direct + Reader Fallback) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a unified content fetching layer (direct HTTP + optional Playwright + Reader fallback) that produces evidence passages and integrates with deepsearch + session evidence artifacts, while keeping OpenAPI as the source of truth.

**Architecture:** Introduce a `ContentFetcher` + `ReaderClient` with env-driven policy; normalize outputs into `FetchedPage` + `EvidencePassage`; emit lightweight fetch events via the existing event emitter; store results in session deepsearch artifacts so `/api/sessions/{thread_id}/evidence` becomes the primary frontend contract.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, httpx/requests, existing Playwright crawler (`tools/crawl/crawler.py`), pytest/monkeypatch, existing SourceRegistry.

---

## Phase 0 — Settings + Utilities

### Task 1: Add Research Fetcher Settings to `common/config.py`

**Files:**
- Modify: `common/config.py`
- Test: `tests/test_research_fetcher_settings.py`

**Step 1: Write the failing test**

```python
from common.config import Settings


def test_settings_exposes_reader_and_fetcher_fields():
    s = Settings()
    assert hasattr(s, "reader_fallback_mode")
    assert hasattr(s, "reader_public_base")
    assert hasattr(s, "reader_self_hosted_base")
    assert hasattr(s, "research_fetch_timeout_s")
    assert hasattr(s, "research_fetch_max_bytes")
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_research_fetcher_settings.py`
Expected: FAIL (missing attributes)

**Step 3: Minimal implementation**

Add settings fields with sane defaults:
- `reader_fallback_mode: str = "both"`
- `reader_public_base: str = "https://r.jina.ai"`
- `reader_self_hosted_base: str = ""`
- `research_fetch_timeout_s: float = 25.0`
- `research_fetch_max_bytes: int = 2_000_000`
- `research_fetch_concurrency: int = 6`
- `research_fetch_concurrency_per_domain: int = 2`

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_research_fetcher_settings.py`
Expected: PASS

**Step 5: Commit**

```bash
git add common/config.py tests/test_research_fetcher_settings.py
git commit -m "feat(config): add research fetcher settings"
```

---

## Phase 1 — Reader Client (public + self-hosted)

### Task 2: Implement Reader URL builder + unit tests

**Files:**
- Create: `tools/research/reader_client.py`
- Create: `tools/research/__init__.py`
- Test: `tests/test_reader_client.py`

**Step 1: Write the failing test**

```python
from tools.research.reader_client import ReaderClient


def test_reader_client_builds_public_url():
    c = ReaderClient(mode="public", public_base="https://r.jina.ai", self_hosted_base="")
    out = c.build_reader_url("https://example.com/a?utm_source=x")
    assert out.startswith("https://r.jina.ai/")


def test_reader_client_prefers_self_hosted_when_configured():
    c = ReaderClient(mode="self_hosted", public_base="https://r.jina.ai", self_hosted_base="http://reader.local")
    out = c.build_reader_url("https://example.com/")
    assert out.startswith("http://reader.local")
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_reader_client.py`
Expected: FAIL (module not found)

**Step 3: Minimal implementation**

Implement `ReaderClient`:
- Constructor takes `mode`, `public_base`, `self_hosted_base`
- `build_reader_url(url: str) -> str`
- Strip trailing slash on base; ensure single `/` join
- No network calls in this task

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_reader_client.py`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/research/reader_client.py tools/research/__init__.py tests/test_reader_client.py
git commit -m "feat(research): add reader client url builder"
```

---

## Phase 2 — FetchedPage model + direct HTTP fetch

### Task 3: Add `FetchedPage` dataclass/model + truncation helper

**Files:**
- Create: `tools/research/models.py`
- Test: `tests/test_fetched_page.py`

**Step 1: Write failing test**

```python
from tools.research.models import FetchedPage


def test_fetched_page_serializes():
    page = FetchedPage(url="https://example.com/", raw_url="https://example.com/?utm=1", method="direct_http", text="hi")
    d = page.to_dict()
    assert d["url"] == "https://example.com/"
    assert d["method"] == "direct_http"
```

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_fetched_page.py`
Expected: FAIL

**Step 3: Implement**

Implement:
- fields: `url, raw_url, title, published_date, retrieved_at, method, text, markdown, http_status, error, attempts`
- `to_dict()` JSON-safe

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_fetched_page.py`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/research/models.py tests/test_fetched_page.py
git commit -m "feat(research): add fetched page model"
```

---

### Task 4: Implement direct HTTP fetcher (no external network in tests)

**Files:**
- Create: `tools/research/content_fetcher.py`
- Test: `tests/test_content_fetcher_direct.py`

**Step 1: Write failing test**

```python
import types

from tools.research.content_fetcher import ContentFetcher


def test_content_fetcher_direct_uses_requests(monkeypatch):
    calls = {"get": 0}

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<html><body>Hello</body></html>"
        text = "<html><body>Hello</body></html>"

    def fake_get(url, timeout=None, headers=None):
        calls["get"] += 1
        return FakeResp()

    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    f = ContentFetcher()
    page = f.fetch("https://example.com/")
    assert page.method == "direct_http"
    assert "Hello" in (page.text or page.markdown or "")
    assert calls["get"] == 1
```

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_content_fetcher_direct.py`
Expected: FAIL

**Step 3: Implement minimal fetch**

- Use `SourceRegistry.canonicalize_url`
- `requests.get(..., timeout=settings.research_fetch_timeout_s, headers={User-Agent})`
- Respect `settings.research_fetch_max_bytes` (truncate `resp.content`)
- Extract a naive text fallback: strip tags minimally (keep simple; better extraction later)

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_content_fetcher_direct.py`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/research/content_fetcher.py tests/test_content_fetcher_direct.py
git commit -m "feat(research): add direct http content fetcher"
```

---

## Phase 3 — Reader fallback + policy

### Task 5: Add Reader fallback selection logic + unit tests

**Files:**
- Modify: `tools/research/content_fetcher.py`
- Test: `tests/test_content_fetcher_reader_fallback.py`

**Step 1: Write failing test**

```python
import types

from tools.research.content_fetcher import ContentFetcher


def test_content_fetcher_falls_back_to_reader(monkeypatch):
    class FakeRespFail:
        status_code = 403
        headers = {"content-type": "text/html"}
        content = b""
        text = ""

    class FakeRespReader:
        status_code = 200
        headers = {"content-type": "text/plain"}
        content = b"Reader text"
        text = "Reader text"

    def fake_get(url, timeout=None, headers=None):
        if "r.jina.ai" in url:
            return FakeRespReader()
        return FakeRespFail()

    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    f = ContentFetcher(reader_mode="public", reader_public_base="https://r.jina.ai")
    page = f.fetch("https://example.com/")
    assert page.method == "reader_public"
    assert "Reader text" in (page.text or "")
```

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_content_fetcher_reader_fallback.py`
Expected: FAIL

**Step 3: Implement minimal fallback**

- On direct fetch non-200 or empty content, call `ReaderClient.build_reader_url(url)`
- Fetch that URL via requests
- Set method based on mode: `reader_public` / `reader_self_hosted`

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_content_fetcher_reader_fallback.py`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/research/content_fetcher.py tests/test_content_fetcher_reader_fallback.py
git commit -m "feat(research): add reader fallback to content fetcher"
```

---

## Phase 4 — Evidence passages

### Task 6: Implement passage splitter + tests

**Files:**
- Create: `agent/workflows/evidence_passages.py`
- Test: `tests/test_evidence_passages.py`

**Step 1: Write failing test**

```python
from agent.workflows.evidence_passages import split_into_passages


def test_split_into_passages_returns_offsets():
    text = "A" * 2000
    passages = split_into_passages(text, max_chars=500)
    assert passages
    assert passages[0]["start_char"] == 0
    assert passages[0]["end_char"] > passages[0]["start_char"]
```

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_evidence_passages.py`
Expected: FAIL

**Step 3: Implement**

- Chunk by paragraphs then size budget
- Output list of dicts: `text,start_char,end_char`

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_evidence_passages.py`
Expected: PASS

**Step 5: Commit**

```bash
git add agent/workflows/evidence_passages.py tests/test_evidence_passages.py
git commit -m "feat(evidence): add passage splitter"
```

---

## Phase 5 — Deepsearch integration + evidence endpoint expansion

### Task 7: Store fetched pages + passages into deepsearch artifacts

**Files:**
- Modify: `agent/workflows/deepsearch_optimized.py`
- Modify: `common/session_manager.py`
- Test: `tests/test_session_deepsearch_artifacts.py`

**Step 1: Add failing assertion to existing test**

Extend `tests/test_session_deepsearch_artifacts.py` to assert:
- `deepsearch_artifacts.fetched_pages` exists
- `deepsearch_artifacts.passages` exists

**Step 2: Run test (expect fail)**

Run: `pytest -q tests/test_session_deepsearch_artifacts.py`
Expected: FAIL

**Step 3: Implement minimal integration**

- After URLs are selected, fetch top N URLs via `ContentFetcher`
- Split into passages
- Store into deepsearch artifacts dict

**Step 4: Run test (expect pass)**

Run: `pytest -q tests/test_session_deepsearch_artifacts.py`
Expected: PASS

**Step 5: Commit**

```bash
git add agent/workflows/deepsearch_optimized.py common/session_manager.py tests/test_session_deepsearch_artifacts.py
git commit -m "feat(research): persist fetched pages and passages in session artifacts"
```

---

### Task 8: Expand `/api/sessions/{thread_id}/evidence` response model (optional fields)

**Files:**
- Modify: `main.py`
- Test: `tests/test_session_evidence_api.py`
- Test: `tests/test_openapi_contract.py`

**Step 1: Write failing contract assertions**

- Evidence response schema includes optional `fetched_pages` and `passages`.

**Step 2: Run tests (expect fail)**

Run:
- `pytest -q tests/test_session_evidence_api.py`
- `pytest -q tests/test_openapi_contract.py`

Expected: FAIL

**Step 3: Implement minimal response model changes**

- Add Pydantic models: `FetchedPageItem`, `EvidencePassageItem`
- Extend `EvidenceResponse` to include optional arrays
- Ensure endpoint reads artifacts and returns them when present

**Step 4: Run tests (expect pass)**

Run:
- `pytest -q tests/test_session_evidence_api.py`
- `pytest -q tests/test_openapi_contract.py`

Expected: PASS

**Step 5: Commit**

```bash
git add main.py tests/test_session_evidence_api.py tests/test_openapi_contract.py
git commit -m "feat(api): include fetched pages and passages in evidence endpoint"
```

---

## Phase 6 — Search provider unification (optional in v1, but aligned with approved design)

### Task 9: Add canonical URL normalization in multi_search results

**Files:**
- Modify: `tools/search/multi_search.py`
- Test: `tests/test_multi_search_ranking.py`

**Step 1: Add failing test**

Ensure that URLs differing only by UTM params dedupe as one.

**Step 2: Implement**

Use `SourceRegistry.canonicalize_url` when building `SearchResult`.

**Step 3: Verify**

Run: `pytest -q tests/test_multi_search_ranking.py`

**Step 4: Commit**

```bash
git add tools/search/multi_search.py tests/test_multi_search_ranking.py
git commit -m "feat(search): canonicalize urls in multi-search"
```

---

## Verification Gate (Before claiming done)

Backend:
- `make test`

Contract drift:
- `bash scripts/check_openapi_ts_types.sh`

Frontend:
- `pnpm -C web install --frozen-lockfile`
- `pnpm -C web lint`
- `pnpm -C web build`
