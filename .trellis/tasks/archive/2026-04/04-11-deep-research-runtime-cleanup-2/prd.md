# Clean Up Deep Research Runtime Knobs And Projection Model

## Goal
Reduce misleading Deep Research runtime abstractions and dead configuration, and converge readiness/validation public projection so runtime state has a clearer single source of truth.

## Requirements
- Remove or neutralize misleading Deep Research tool-agent configuration paths that are not part of the current runtime execution model.
- Remove dead Deep Research config/runtime knobs that are parsed but not consumed by the actual runtime flow.
- Keep current Deep Research runtime behavior, checkpoint resume behavior, and public artifact consumers working after cleanup.
- Converge readiness/validation public projection so export/resume/public artifacts derive from one shared projection path instead of repeated ad-hoc fallback logic.
- Update regression tests to cover the cleaned contracts.

## Acceptance Criteria
- [ ] Current Deep Research runtime no longer exposes misleading unused tool-agent feature switches in active code paths.
- [ ] Unused Deep Research runtime knobs are removed from config/runtime code and related tests/docs are updated.
- [ ] Public readiness/validation payloads are derived through a shared projection contract with reduced duplication.
- [ ] Existing Deep Research runtime regression coverage remains green and targeted new/updated tests cover the cleanup.

## Technical Notes
- Scope is intentionally limited to cleanup/refactor of current `multi_agent` runtime, not a broader architecture rewrite.
- Preserve current checkpoint names, resume semantics, public `deep_research_artifacts` shape, and SSE/frontend compatibility unless a field is provably dead and internal-only.
- Prefer single-source derivation helpers over duplicating fallback logic in `main.py`, runtime finalize, and resume helpers.
