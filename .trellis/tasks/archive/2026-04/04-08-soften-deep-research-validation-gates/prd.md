# Soften deep research validation gates

## Goal
Make Deep Research validation advisory-first so review and claim checks improve output quality without hard-blocking final report generation when some information is unavailable.

## Requirements
- Explain and preserve current review/claim quality signals in runtime artifacts.
- Remove the requirement that all required sections must be certified before report generation.
- Allow partial or limitation-bearing section drafts to flow into the final report when they are the best available result.
- Keep reviewer and claim verification outputs visible in artifacts and events.
- Avoid terminal blocked status when the runtime can still produce a useful report.

## Acceptance Criteria
- [ ] Deep Research can generate a final report even when some sections remain uncertified but have usable drafts.
- [ ] Final claim verification records contradictions/unsupported claims as quality warnings instead of a hard stop.
- [ ] Quality summary and public artifacts still expose validation issues and completion state.
- [ ] Regression tests cover partial-report and non-blocking claim verification behavior.

## Technical Notes
- Primary implementation target is `agent/runtime/deep/orchestration/graph.py`.
- Frontend status text may need a small update if decision semantics change.
- Keep changes minimal and aligned with existing artifact/event contracts where possible.
