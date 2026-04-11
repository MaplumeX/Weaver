# Memory Runtime Contracts

> Executable contracts for explicit long-term memory ingestion, extractor
> gating, runtime wiring, and debug metadata/event behavior.

---

## Overview

These contracts apply when backend work changes any of:

- `common/memory_service.py`
- `common/session_service.py`
- `main.py` memory extractor/runtime wiring
- `/api/memory/*` payload visibility for metadata or events

This document is mandatory for memory work because the same write path is
consumed by:

- session-backed chat startup and resume flows
- support chat ingestion
- long-term memory persistence (`memory_entries`, `memory_entry_events`)
- runtime memory context assembly
- debug/admin memory APIs

---

## Scenario: Explicit Memory Extraction Contract

### 1. Scope / Trigger

- Trigger: changing explicit memory ingestion, long-term memory extraction
  rules, extractor wiring, or memory metadata/event payloads.
- This is a cross-layer contract:
  FastAPI request path or session flow -> `SessionService` / `main.py` ->
  `MemoryService` -> `MemoryStore` -> memory debug APIs.
- Treat explicit memory extraction as a stable backend capability, not as
  prompt-only behavior.

### 2. Signatures

- File: `common/memory_service.py`
  - `class MemoryExtractionResult(BaseModel)`
  - `class ModelBackedMemoryExtractor`
  - `ModelBackedMemoryExtractor.extract(*, source_message, intent_fact, forced_type=None) -> MemoryExtractionResult | None`
  - `MemoryService.ingest_user_message(*, user_id, text, source_kind, thread_id="") -> list[dict[str, Any]]`
- File: `common/session_service.py`
  - `SessionService.start_session_run(*, thread_id, user_id, route, initial_user_message) -> None`
  - `SessionService.append_user_message(*, thread_id, content) -> None`
- File: `main.py`
  - `_build_memory_extractor() -> ModelBackedMemoryExtractor | None`
  - `_ingest_explicit_memory_if_needed(*, user_id, text, source_kind, thread_id="") -> None`

### 3. Contracts

Explicit-ingestion gating:

- Only explicit memory instructions may enter the extractor path.
- Examples of allowed triggers:
  - `请记住...`
  - `记一下...`
  - `以后请...`
  - `remember ...`
  - `my long-term preference is ...`
- General user self-description without explicit memory intent must not trigger
  extraction in this phase.

Pre-extraction rejection:

- Task-local, session-local, repo-local, thread-local, or temporary facts must
  be rejected before model extraction.
- If the explicit instruction resolves to ephemeral content, do not call the
  extractor and do not write a memory entry.

Extractor acceptance rules:

- The extractor runs only after explicit-intent gating succeeds.
- A memory entry may be persisted only when all of the following hold:
  - `should_store == true`
  - `stability == "high"`
  - `memory_type in {"preference", "user_fact"}`
  - extracted fact is non-empty, non-ephemeral, and within length limit
- Medium/low stability is a hard reject in this phase.
- On extractor failure, timeout, empty result, or invalid structured output,
  skip the write. Do not fall back to rule-only persistence.

Persistence metadata contract:

- This phase does not add new DB columns.
- Entry-level write metadata must remain in `memory_entries.metadata`.
- Required metadata keys for extractor-backed writes:
  - `ingestion`
  - `ingestion_method`
  - `extractor_model`
  - `extractor_version`
  - `ingestion_reason`
  - `dedupe_basis`
  - `stability`

Event contract:

- Memory ingestion outcomes must be observable through
  `memory_entry_events`.
- Expected event types for this flow:
  - `ingested`
  - `ingest_skipped`
  - `extract_failed`
  - `extract_rejected`

Async runtime contract:

- Request-path memory ingestion must not block the event loop with direct model
  calls.
- Async callers must offload `MemoryService.ingest_user_message(...)` via
  `asyncio.to_thread(...)`.
- This applies to:
  - `SessionService.start_session_run(...)`
  - `SessionService.append_user_message(...)`
  - `main.py` support/resume direct-ingestion helpers

### 4. Validation & Error Matrix

| Input / State | Required Behavior | If Broken | Typical Symptom |
|---------------|-------------------|-----------|-----------------|
| Explicit durable preference with high-stability extractor result | Persist one memory entry with extractor metadata and `ingested` event | Preference is lost or stored without traceability | User explicitly says "remember" but nothing is retrievable later |
| Explicit but ephemeral instruction | Reject before extractor call | Temporary task state pollutes long-term memory | Memory context starts surfacing current-task directions |
| Extractor unavailable | Skip write and emit `ingest_skipped` event | Silent loss with no audit trail | Operator cannot tell why explicit memory was ignored |
| Extractor raises / times out | Skip write and emit `extract_failed` event | Request path may fail or fallback may write unstable data | User request slows down or wrong memory is stored after model outage |
| Extractor returns `stability=medium|low` | Reject and emit `extract_rejected` | Unstable or speculative facts get stored | Memory contains weakly inferred phrasing |
| Async request path calls ingestion directly | Must be offloaded with `asyncio.to_thread(...)` | Event loop blocking | Chat/support requests stall during memory extraction |

### 5. Good / Base / Bad Cases

Good:

- User message: `请记住以后请先讲风险，再讲实现`
- Gating passes, extractor returns:
  - `should_store=true`
  - `memory_type=preference`
  - `fact=讨论实现时先讲风险，再讲实现`
  - `stability=high`
- Result: one active memory entry is stored with extractor metadata and an
  `ingested` event.

Base:

- User message: `请记住我主要用 FastAPI`
- Extractor is unavailable or fails
- Result: no memory entry is written; an audit event records the skip/failure.

Bad:

- User message: `记住这次任务先改 main.py`
- If this is stored as long-term memory, ephemeral task state leaks into future
  conversations.

### 6. Tests Required

- `tests/test_memory_service.py`
  - assert explicit-intent success writes one entry
  - assert ephemeral instruction is rejected before extractor use
  - assert extractor-not-configured path emits `ingest_skipped`
  - assert extractor failure emits `extract_failed`
  - assert low/medium stability emits `extract_rejected`
  - assert structured-output fallback retries the next method
- `tests/test_session_service_memory_ingest.py`
  - assert session-backed startup and resume still forward the same logical
    memory-ingestion payload through the async wrapper
- Assertion points:
  - entry `metadata["ingestion_method"]`
  - entry `metadata["extractor_model"]`
  - event `event_type`
  - extractor call payload (`source_message`, `intent_fact`, `forced_type`)

### 7. Wrong vs Correct

#### Wrong

```python
extraction = extractor.extract(...)
if extraction is None:
    candidate = _rule_based_candidate(intent)
    return store.upsert_entry(...)
if extraction.stability != "high":
    return store.upsert_entry(...)
```

#### Correct

```python
extraction = extractor.extract(...)
candidate, rejection_reason = self._candidate_from_extraction(extraction, intent=intent)
if candidate is None:
    self._record_event(
        event_type="extract_rejected",
        reason=rejection_reason,
        payload={"ingestion_method": "explicit_rule_llm"},
    )
    return []
```

#### Wrong

```python
self.memory_service.ingest_user_message(
    user_id=user_id,
    text=initial_user_message,
    source_kind="chat",
    thread_id=thread_id,
)
```

#### Correct

```python
await asyncio.to_thread(
    self.memory_service.ingest_user_message,
    user_id=user_id,
    text=initial_user_message,
    source_kind="chat",
    thread_id=thread_id,
)
```
