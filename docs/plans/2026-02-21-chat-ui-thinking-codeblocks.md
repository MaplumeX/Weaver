# Chat UI: Thinking + Code Output Polish

Date: 2026-02-21

## Scope / Symptoms

User-reported issues in the chat UI:

- Thinking UI (tool activity) sometimes **never completes** even when the model finished.
- Thinking steps **duplicate / keep growing** during a run.
- Thinking card is **too narrow / misaligned** with the message surface.
- Code blocks sometimes **overflow awkwardly** and **feel slow** on large outputs.
- Overall UI for these surfaces is “not pretty enough” (needs cleaner baseline styling).

## Root Cause (Thinking stuck / duplicated)

The streamed `tool` events currently behave like:

- `on_tool_start` emits `tool` events with a **generic name** (e.g. `"search"`, `"code_execution"`) and no stable id.
- `on_tool_end` emits `tool` events with the **real tool name** (e.g. `"tavily_search"`), still without a stable id.
- Frontend appends every `tool` event into `message.toolInvocations` (no upsert).

As a result:

- Start/end cannot be correlated → “running” entries never flip to “completed”.
- Every tool call becomes multiple UI entries → duplicates accumulate.

## Design (Chosen Approach)

### 1) Backend: stable tool correlation id

In `main.py` streaming:

- Include `toolCallId` in tool events (derived from LangGraph `run_id` when available).
- Emit **consistent tool name** on start/end (real tool name).
- Optionally include a small `args` preview payload for UI (query/code/url, truncated).

This is additive and should be backward compatible with existing clients.

### 2) Frontend: upsert tool invocations

In `web/hooks/useChatStream.ts`:

- Convert tool handling from “append” to “upsert”.
- Prefer `toolCallId` for matching; fallback to a stable key derived from `(toolName, query)` when no id exists.

Add a small pure helper (unit-tested) for deterministic behavior.

### 3) ThinkingProcess UI (baseline-ui)

- Remove the heuristic stepper (“Plan/Search/Analyze/Report”) which can be inaccurate.
- Replace with a compact “Tool activity” header:
  - running/completed counts
  - collapsible list of tool calls with state + minimal args preview
- Fix width to align with the message surface (remove `max-w-md`).
- Avoid adding new animations; keep existing micro feedback minimal.

### 4) CodeBlock UI: overflow + performance

Goals:

- Default to preserving code formatting with horizontal scrolling (no forced wrap).
- Provide a **wrap toggle** for readability when needed.
- Improve performance on large blocks:
  - avoid per-line syntax highlighting (heavy)
  - use plain rendering for very large blocks or allow collapsing by default

## Verification

- Add a vitest unit test for the tool upsert helper (ensures “running → completed” updates, no duplicates).
- Run `pnpm -C web test`, `make web-lint`, `make web-build`, `make check`.

## Rollout / Compatibility

- All changes are additive: existing stream consumers can ignore new fields.
- If `toolCallId` is missing (older streams), frontend fallback logic still behaves well.

