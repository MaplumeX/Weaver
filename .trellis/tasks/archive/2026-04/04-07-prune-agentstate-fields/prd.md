# Prune Unused AgentState Fields

## Goal
Remove `AgentState` fields that are not consumed by the current root graph runtime or related runtime flows, while preserving existing chat/deep-research behavior.

## Requirements
- Remove fields from `AgentState` and initial state construction only when they have no runtime consumers.
- Keep fields that are still required by deep-research runtime, checkpoint restore, or public artifact building.
- Update tests and projections that currently assume removed fields exist.
- Do not introduce unrelated state-model refactors.

## Acceptance Criteria
- [ ] Unused `AgentState` fields are removed from the schema and initial state builder.
- [ ] Remaining runtime paths still build and use state correctly for chat and deep modes.
- [ ] Tests covering state initialization/projection are updated to the new contract.
- [ ] Targeted backend tests pass.

## Technical Notes
- The change spans `agent/core/state.py`, `agent/application/state.py`, `agent/domain/state.py`, and tests around state slices.
- Treat checkpoint/runtime compatibility as a contract boundary: only remove fields with no active runtime consumers.
