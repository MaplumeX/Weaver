# Remove Final Claim Gate From Deep Research

## Goal
Remove the `final_claim_gate` stage from the deep research multi-agent pipeline and delete the deep-research-only `ClaimVerifier` contract if it is no longer used.

## Requirements
- Remove `final_claim_gate` from the backend runtime graph and resume logic.
- Remove final-claim-gate-derived runtime fields, API summary fields, and UI timeline/status handling.
- Delete `ClaimVerifier` and related exports/tests if it is no longer used anywhere after the pipeline change.
- Keep the existing reviewer/section gating and report generation behavior unchanged.
- Preserve unrelated in-progress deep research changes already present in the worktree.

## Acceptance Criteria
- [ ] Deep research flows from `report` directly to `finalize`.
- [ ] No deep research runtime output includes `final_claim_gate_summary` or claim-verifier counters.
- [ ] Frontend deep research timeline/progress no longer references `Final Claim Gate`.
- [ ] `ClaimVerifier` code and tests are removed if no runtime path imports it anymore.
- [ ] Targeted backend and frontend regression tests pass.

## Technical Notes
- This is a cross-layer cleanup touching runtime graph, public runtime artifacts, API metrics projection, frontend progress UI, and tests/docs.
- The current worktree already contains unrelated deep research changes in supervisor/review logic; integrate with them without reverting.
