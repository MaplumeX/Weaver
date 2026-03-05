# DeepSearch Live Browser Activity (v0.6.x)

## Problem

The frontend includes a WebSocket live browser viewer (`/api/browser/{thread_id}/stream`) that can render a remote Chromium session.

In DeepSearch / Tree research modes, we often rely on **API-based search providers** (Tavily/Serper/DDG, etc.) and optional lightweight crawling. Those steps may never open a page in the sandbox browser, so the live viewer can remain stuck on `about:blank` (visually “white/empty”) even while research is actively running.

This is confusing: users expect DeepSearch to “browse the web” and see the agent open pages, scroll, and capture screenshots.

## Goal

When DeepSearch is running, keep the sandbox browser session active so the Live viewer:

- navigates to real source pages
- scrolls (human-like skim)
- emits screenshots (for the timeline + Thinking accordion)

This is primarily a **UX visualization layer**: it should be best-effort and must never break research correctness.

## Options considered

1. **Do nothing / keep API-only search**
   - Fast, but Live viewer remains blank for many runs.

2. **Browser-only search (open a search engine UI)**
   - Strong “agent browsing” feel, but brittle (bot detection/CAPTCHAs) and slower.

3. **Hybrid preview (chosen)**
   - Keep API search for reliability.
   - After each query (and after URL selection), preview 1–3 top URLs in the sandbox browser:
     - navigate
     - scroll a bit
     - capture screenshots via existing `sb_browser_*` tool event emission
   - Pros: reliable, shows real pages, minimal coupling to research logic.
   - Cons: extra sandbox/browser work (configurable).

## Design

- Add `deepsearch_visualize_browser: bool` setting (default `True`).
- Introduce `agent/workflows/browser_visualizer.py`:
  - resolves `thread_id` from LangGraph config
  - de-dupes visited URLs per thread
  - uses `SbBrowserNavigateTool` + `SbBrowserScrollTool` to drive the sandbox browser
  - best-effort: failures do not raise
- Integrate into:
  - Linear DeepSearch (`agent/workflows/deepsearch_optimized.py`)
    - preview top search result per query
    - preview up to 3 “chosen” URLs per epoch
  - Tree research (`agent/workflows/research_tree.py`)
    - preview top search result per query in both sync + async branch exploration

## Success criteria

- During DeepSearch, the live browser viewer should show real page navigation (not a persistent blank `about:blank`).
- “Thinking…” accordion and screenshots timeline should include `sb_browser_*` tool events (navigate/scroll screenshots).
- Research output quality should be unchanged (visualization is best-effort and non-blocking for correctness).

