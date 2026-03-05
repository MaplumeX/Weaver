# Weaver Tag Notes

This document is a lightweight “tag register” for the repo. It is meant for quick copy/paste when creating release notes.

- **Date** = the commit date of the commit the tag points to (not the tagger date).
- **Commit** = the commit SHA the tag points to.
- **Summary** = the tag subject (annotated tags) or the commit subject (lightweight tags).

## Index

| Tag | Date | Commit | Summary |
| --- | --- | --- | --- |
| `v0.6.6` | 2026-03-05 | `6280914` | v0.6.6: Live viewer shows correct URL/title on CDP frames |
| `v0.6.5` | 2026-03-05 | `7e82ec6` | v0.6.5: Live view frames don't stall during navigation |
| `v0.6.4` | 2026-03-05 | `d57cb16` | v0.6.4: live view default status page + stream mode default |
| `v0.6.3` | 2026-03-05 | `8cbdc44` | v0.6.3: deepsearch drives live browser (navigate/scroll/screenshot) |
| `v0.6.2` | 2026-03-05 | `e55a469` | v0.6.2: auto-start browser live view |
| `v0.6.1` | 2026-03-05 | `4988547` | v0.6.1: thinking accordion + actionable live browser viewer |
| `v0.6.0` | 2026-02-22 | `c5af854` | v0.6.0: chat UI stream alignment + codeblock UX |
| `v0.5.0` | 2026-01-02 | `89b4fa7` | 优化README |
| `v0.4.0` | 2026-01-01 | `45a1cc5` | 沙盒机制 |
| `v0.3.0` | 2025-12-23 | `6df4d17` | Update .env.example2 |
| `v0.2.0` | 2025-12-22 | `c47c29e` | 暂存 |
| `v0.1.0` | 2025-12-21 | `ac7f7d4` | 暂存 |

## Details

### v0.6.6 (2026-03-05)

- **Commit:** `6280914`
- **Tag subject:** v0.6.6: Live viewer shows correct URL/title on CDP frames
- **Commit subject:** fix(browser): preserve live frame URL/title metadata
- **Notes:**
  - Track last page URL/title on sandbox browser sessions
  - Attach URL/title to CDP screencast frames without Playwright cross-thread calls

### v0.6.5 (2026-03-05)

- **Commit:** `7e82ec6`
- **Tag subject:** v0.6.5: Live view frames don't stall during navigation
- **Commit subject:** fix(browser): stream CDP frames without blocking
- **Notes:**
  - Let WS stream peek latest CDP frames (no Playwright executor hop)
  - Throttle/async deepsearch browser previews to avoid slowing research
  - Skip heavy video sites for previews and reduce preview waits
  - Emit screenshot even when navigation fails

### v0.6.4 (2026-03-05)

- **Commit:** `d57cb16`
- **Tag subject:** v0.6.4: live view default status page + stream mode default
- **Commit subject:** fix(browser): avoid blank Live viewer on start
- **Notes:**
  - Render an animated status page when sandbox is still on about:blank
  - Default BrowserViewer to stream mode and add quick mode switch
  - Preview top search result pages during deepsearch API search
  - Ignore runtime screenshots in git

### v0.6.3 (2026-03-05)

- **Commit:** `8cbdc44`
- **Tag subject:** v0.6.3: deepsearch drives live browser (navigate/scroll/screenshot)
- **Commit subject:** feat(deepsearch): keep live browser active during search
- **Notes:**
  - Deepsearch keeps the sandbox browser “busy” (navigate / scroll / screenshot) so Live view is never just a blank page.

### v0.6.2 (2026-03-05)

- **Commit:** `e55a469`
- **Tag subject:** v0.6.2: auto-start browser live view
- **Commit subject:** fix(web): auto-start browser live view + better empty states
- **Notes:**
  - Browser Live view auto-starts (no manual click required).
  - Improved empty/initial states in the Web UI.

### v0.6.1 (2026-03-05)

- **Commit:** `4988547`
- **Tag subject:** v0.6.1: thinking accordion + actionable live browser viewer
- **Commit subject:** feat(web): interactive live browser viewer
- **Notes:**
  - OpenAI-style “Thinking…” accordion: keep main answer clean; expand to view process/events.
  - Actionable Live browser viewer for research-style workflows.

### v0.6.0 (2026-02-22)

- **Commit:** `c5af854`
- **Tag subject:** v0.6.0: chat UI stream alignment + codeblock UX
- **Commit subject:** docs(readme): add v0.5.0+ release notes for chat UI
- **Notes:**
  - Focused on chat UI streaming alignment + codeblock UX improvements.

### v0.5.0 (2026-01-02)

- **Commit:** `89b4fa7`
- **Commit subject:** 优化README
- **Notes:**
  - Documentation clean-up and `.env` completeness improvements.
  - Added multiple sandbox query mechanisms.

### v0.4.0 (2026-01-01)

- **Commit:** `45a1cc5`
- **Commit subject:** 沙盒机制
- **Notes:**
  - Introduced sandbox mechanism and related frontend display.
  - Fixed live-view visibility, frontend CORS issues, and sandbox screenshot bugs.
  - Memory mechanism and agent screenshot workflow refinements.

### v0.3.0 (2025-12-23)

- **Commit:** `6df4d17`
- **Commit subject:** Update .env.example2
- **Notes:**
  - Addressed sandbox invalidation issues and updated supported browsers.
  - Misc fixes (e.g. comment encoding/garbling).

### v0.2.0 (2025-12-22)

- **Commit:** `c47c29e`
- **Commit subject:** 暂存
- **Notes:**
  - Early agent iterations and dependency fixes (e.g. requirements and pydantic pinning).
  - Backend refactor and frontend deep-research display fixes.

### v0.1.0 (2025-12-21)

- **Commit:** `ac7f7d4`
- **Commit subject:** 暂存
- **Notes:**
  - Initial tagged snapshot.

