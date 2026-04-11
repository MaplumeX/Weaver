# Document Deep Research Pipeline

## Goal
Create a repository-backed Markdown document that explains the Deep Research end-to-end workflow, including runtime entrypoints, agent roles, collaboration flow, intermediate artifacts, and how those artifacts move across backend runtime, persistence, and frontend event consumers.

## Requirements
- Trace how requests enter Deep Research mode from the main execution graph.
- Identify each Deep Research agent role and summarize its responsibility.
- Explain how agents collaborate across intake, planning, worker execution, merge, review, and report completion.
- Enumerate the main intermediate artifacts, where they are stored, and how they are transformed into public artifacts.
- Document how events and artifact snapshots are exposed to the frontend or resume flows.
- Write the analysis into a Markdown document under `docs/`.

## Acceptance Criteria
- [ ] The document references the concrete backend modules that implement each stage.
- [ ] The document distinguishes explicit code facts from inferred behavior where needed.
- [ ] The document explains artifact flow from runtime state to public `deep_research_artifacts`.
- [ ] The document covers frontend-facing event or resume integration points that consume Deep Research outputs.

## Technical Notes
- This is a documentation-only task backed by repository inspection.
- The main code surface is `agent/deep_research/`, plus runtime routing, persistence, and frontend stream consumers.
