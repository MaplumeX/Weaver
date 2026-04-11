# Deep Research Supervisor Tool-Calling Manager V1

## Goal
Upgrade the Deep Research supervisor control plane so the entire supervisor surface is manager-driven with tool calls, while preserving the existing researcher, reviewer, reporter, artifact, and task-queue runtime flow.

## Requirements
- Remove deterministic supervisor entry points and keep only the tool-calling manager path.
- Introduce supervisor control-plane tools for outline submission, research dispatch, revision dispatch, report completion, and stop decisions.
- Keep the existing public supervisor methods stable: `create_outline_plan()` and `decide_section_action()`.
- Convert both `outline_plan` and `supervisor_decide` to tool-calling manager flows.
- Preserve the existing reviewer-driven quality gate and researcher execution flow.
- Compile supervisor tool calls into the current runtime pipeline:
  - `submit_outline_plan` -> `outline -> plan -> task_queue`
  - `conduct_research` / `revise_section` -> `task_specs -> task_queue`
- Keep deep runtime artifacts and checkpoint behavior backward compatible at the artifact shape level.
- Fix runtime observability so researcher/revisor nodes do not mark `active_agent` as `supervisor`.

## Acceptance Criteria
- [x] `ResearchSupervisor.create_outline_plan()` uses only the tool-calling outline manager path.
- [x] `ResearchSupervisor.decide_section_action()` uses only the tool-calling manager path.
- [x] Deterministic supervisor config and runtime fallbacks are removed from the active execution path.
- [x] Supervisor tool-call outputs are compiled into valid runtime outlines and replan task specs.
- [x] Existing reviewer and researcher paths continue to work without architectural rewrite.
- [x] Targeted backend tests cover outline manager behavior, replan behavior, and runtime failure handling.

## Technical Notes
- Reuse existing Deep Research tool-agent infrastructure where practical, but keep supervisor v1 on control-plane tools only.
- Keep module ownership inside `agent/deep_research/agents/` and `agent/deep_research/engine/`.
- Keep the tool schema narrow:
  - outline: `submit_outline_plan`, `stop_planning`
  - decision: `conduct_research`, `revise_section`, `complete_report`, `stop_research`
- When the manager fails or emits no usable tool call:
  - `outline_plan` blocks and finalizes the runtime
  - `supervisor_decide` returns `STOP`
