# Strong Citations for Deep Research (Plan)

Date: 2026-02-21

## Goal

Improve Deep Research output quality to an “A” level by making citations:

- **Reliable**: report citations use a stable `[1] [2] ...` format.
- **Aligned**: citation numbers map 1:1 to the **same** `sources[]` payload sent to the frontend.
- **Usable in UI**: clicking `[n]` highlights the matching source and tooltips show real metadata (not placeholders).
- **Open-source friendly**: no new mandatory paid APIs; no default-on network fetching that could add flakiness.

Non-goals:

- Re-architect the entire research graph or add a full “enterprise” workflow.
- Enable content fetcher/crawler by default (kept opt-in via `.env`).

## Current State (Before)

- DeepSearch final report is generated from `summary_notes` only, which often loses URLs/snippets.
- Frontend parses `[n]` in paragraphs, but `CitationBadge` tooltips are placeholder text.
- List items (`<li>`) don’t reliably convert `[n]` into clickable citation badges.

## Approach Options Considered

1. **Prompt-driven citations + system-appended reference list** (recommended)
   - Provide the writer a numbered sources block.
   - Require citations in the body using `[n]` that match those numbers.
   - Append a deterministic “参考来源（自动生成）” section from the same sources list.

2. Automatic citation injection (post-processing)
   - Insert citations into sentences after claim-to-evidence matching.
   - Rejected: higher risk of breaking Markdown and adds complexity.

3. Structured report schema (JSON sections + citations)
   - Rejected: too large a change for current scope.

## Selected Design

### Backend (DeepSearch)

Files:
- `agent/workflows/deepsearch_optimized.py`
- `prompts/templates/deepsearch/final_summary.py`

Plan:

1. Extract a stable, canonical `sources[]` list from `search_runs` using
   `agent/workflows/evidence_extractor.extract_message_sources`.
2. Build a compact “sources for writer” block with:
   - numbering `[1..N]`
   - `title`, `domain/provider/publishedDate` when available
   - URL (canonical + raw if needed)
   - a short snippet/summary (best-effort, from search results)
3. Pass that block into the writer prompt as `{sources}`.
4. After LLM report generation, **append** a deterministic references section:
   `## 参考来源（自动生成）` with a numbered list matching the same ordering.
5. Optionally include `sources` at the top-level output state so the streaming layer can reuse it.

Safety:
- Do not change the default `DEEPSEARCH_ENABLE_RESEARCH_FETCHER` / crawler defaults.
- Avoid adding network calls in tests.

### Prompt Changes (Writer)

Update `final_summary_prompt_zh` to:

- Require citations for factual claims, numbers, dates, comparisons, and recommendations.
- Restrict citations to only the provided sources numbering (`[n]` must exist).
- Forbid inventing sources or writing a separate references list (system appends it).

### Frontend (Citation UX)

Files:
- `web/components/chat/MessageItem.tsx`
- `web/components/chat/message/CitationBadge.tsx`

Plan:

1. Pass the matching `MessageSource` into `CitationBadge` based on citation number.
2. Tooltip displays real data:
   - title
   - domain/provider
   - published date / freshness when available
   - clickable URL
3. Extend citation parsing to list items (`<li>`) to improve readability for reports that use many bullet points.

### Docs

Files:
- `README.md`

Add a short section under “深度研究示例/使用指南” describing:
- `[n]` citation semantics
- clicking citations to inspect sources
- optional stronger evidence via `DEEPSEARCH_ENABLE_RESEARCH_FETCHER=true`

## Verification

Run:
- `make check`
- `make web-lint`
- `make web-build`
- `make openapi-types` (only if API schemas change)

## Rollout / Compatibility

- Report remains Markdown.
- Citations continue using the already-supported `[n]` format.
- `message.sources` remains backward compatible; UI enhancements are additive.

