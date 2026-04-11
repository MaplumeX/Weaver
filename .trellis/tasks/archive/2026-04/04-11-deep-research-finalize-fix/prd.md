# Fix Deep Research Finalize State Handling

## Goal
Fix Deep Research finalize behavior so the returned runtime snapshot reflects completion correctly and finalize never returns an empty successful result when reporting has no admitted sections.

## Requirements
- Ensure `final_result.deep_runtime.runtime_state` is projected from the finalized runtime state, not the pre-finalize snapshot.
- Ensure the empty-report finalize path records a terminal failure reason and produces a non-empty user-facing final report.
- Keep the fix scoped to the Deep Research runtime and its existing public contracts.
- Add regression tests for both behaviors.

## Acceptance Criteria
- [ ] Deep Research finalize returns `deep_runtime.runtime_state.next_step == "completed"`.
- [ ] Deep Research finalize keeps `runtime_state.phase == "finalize"` after completion.
- [ ] When `report` has no reportable sections, finalize returns a non-empty failure report and marks completion deterministically.
- [ ] Targeted pytest coverage passes for the modified behavior.

## Technical Notes
- Backend-only implementation in `agent/deep_research/engine/`.
- This change affects a cross-layer runtime payload consumed by checkpoint resume logic and frontend/public artifacts, so preserve field names and shapes.
