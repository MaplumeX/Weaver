# Refine Deep Research Runtime State Contracts

## Goal
Stabilize the Deep Research multi-agent runtime state machine without changing external API behavior or replacing the current LangGraph topology.

## Requirements
- Introduce explicit runtime step and agent constants/types for the Deep Research engine.
- Centralize step normalization and resume-step resolution so graph routing and checkpoint recovery share the same contract.
- Align `outline_gate` graph routing with the actual decision outputs so the topology matches runtime semantics.
- Replace ad-hoc pending replan and worker assignment payload handling with typed runtime contracts where practical.
- Remove or fix misleading worker assignment metadata so revision tasks do not carry inconsistent agent identity semantics.

## Acceptance Criteria
- [ ] Deep Research runtime uses shared step/agent contract helpers instead of scattered string literals for core routing paths.
- [ ] Resume logic and in-graph routing resolve the same normalized runtime steps.
- [ ] `outline_gate` can route directly to `report` or `finalize` according to its decision result.
- [ ] Pending replan and dispatch payloads have explicit typed contracts or normalization helpers.
- [ ] Regression tests cover outline-gate routing, resume-step normalization, legacy payload compatibility, and worker assignment semantics.

## Technical Notes
- Scope is backend-only and limited to `agent/deep_research/engine/*`, `agent/deep_research/schema.py`, and targeted tests.
- Keep checkpoint names and public Deep Research artifact payloads stable.
- Prefer additive compatibility layers for legacy checkpoint/runtime payloads.
