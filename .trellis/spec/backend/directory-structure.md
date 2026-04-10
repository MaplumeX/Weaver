# Directory Structure

> How backend code is organized in this project.

---

## Overview

The backend is centered around a single FastAPI application entrypoint and a
set of capability-focused packages.

- `main.py` is the backend composition root. It contains app startup,
  middleware, exception handlers, request/response models, and most routes.
- `agent/` is organized by capability: execution, chat, Deep Research,
  prompting, tooling, foundation, and contracts.
- `common/` contains shared infrastructure used across the backend.
- `tools/` contains concrete tool implementations grouped by capability.
- `triggers/` contains the trigger subsystem and should stay self-contained.

Do not force a generic `src/controllers/services/repositories` layout onto this
repo. Follow the current ownership boundaries instead.

---

## Directory Layout

```
.
├── main.py
├── agent/
│   ├── __init__.py
│   ├── api.py
│   ├── chat/
│   ├── contracts/
│   ├── deep_research/
│   │   ├── agents/
│   │   ├── artifacts/
│   │   ├── branch_research/
│   │   ├── engine/
│   │   └── intake/
│   ├── execution/
│   │   └── intake/
│   ├── foundation/
│   ├── prompting/
│   └── tooling/
│       └── agents/
├── common/
│   ├── config.py
│   ├── logger.py
│   ├── memory_service.py
│   ├── memory_store.py
│   ├── persistence_schema.py
│   ├── session_service.py
│   └── session_store.py
├── tools/
│   ├── browser/
│   ├── code/
│   ├── crawl/
│   ├── export/
│   ├── io/
│   ├── sandbox/
│   └── search/
├── triggers/
├── prompts/
├── scripts/
├── tests/
└── data/
```

---

## Module Organization

Use the owning package that already matches the behavior:

- Put FastAPI-only glue in `main.py` when it is tightly coupled to request
  parsing, response shaping, middleware, or route wiring.
- Put root graph wiring, execution request assembly, and route-mode selection
  in `agent/execution/`.
- Put chat-specific runtime nodes and prompt assembly in `agent/chat/`.
- Put Deep Research control-plane/runtime logic in `agent/deep_research/`.
- Put reusable runtime foundations in `agent/foundation/`, including shared
  state, event streaming, chat-context shaping, model resolution, and source
  helpers.
- Put prompt registry/manager logic in `agent/prompting/`. Prompt text assets
  still live under top-level `prompts/`.
- Put tool registry, capability expansion, runtime context, provider assembly,
  and agent-tool policy logic in `agent/tooling/`.
- Put stable public contracts in `agent/contracts/`.
- Put cross-cutting infrastructure under `common/`, such as config, logging,
  persistence, metrics, or session lifecycle helpers.
- Put external capability adapters under `tools/`, grouped by domain instead of
  by vendor.
- Put trigger-specific logic under `triggers/`; do not leak trigger internals
  into unrelated packages.

Placement rules:

- If code is only needed to serve an endpoint and would add indirection
  elsewhere, keeping it in `main.py` is acceptable.
- If code is reused across endpoints, runtime nodes, or tools, extract it to
  `common/`, `agent/`, or `tools/`.
- Keep public package surfaces explicit. Small facade modules such as
  `agent/api.py`, `agent/__init__.py`, and `agent/contracts/research.py` are
  preferred over broad wildcard imports.

---

## Naming Conventions

- Use `snake_case.py` for Python modules and functions.
- Prefer capability-oriented names over vague utility buckets. Examples:
  `session_store.py`, `runtime_context.py`, `branch_research`, `source_urls.py`.
- Keep package names responsibility-focused (`agent/execution`,
  `agent/tooling`, `agent/foundation`, `tools/search`, `common`).
- Stable public surfaces should declare explicit exports with `__all__`.
- New top-level directories are rare; prefer extending an existing package.

Anti-patterns:

- Do not create new architectural layers just because they are common in other
  projects.
- Do not add generic `utils.py` dumping grounds when a capability-specific
  module name is clearer.
- Do not expand the public API surface of `agent/` accidentally; expose new
  entrypoints deliberately.

---

## Examples

- `main.py`: the FastAPI composition root with middleware, models, exception
  handlers, and API routes.
- `common/logger.py`: shared infrastructure module with a single clear
  responsibility.
- `common/memory_store.py`: project-owned persistence adapter for long-term
  memory.
- `common/memory_service.py`: shared memory ingestion/retrieval service used by
  chat and support flows.
- `agent/execution/graph.py`: root runtime orchestration and Postgres
  checkpointer setup kept under `agent/` instead of the HTTP layer.
- `agent/deep_research/engine/graph.py`: Deep Research workflow engine kept
  inside the capability package, not mixed into `main.py`.
- `agent/tooling/runtime_context.py`: tool runtime context assembly owned by
  the tooling package, not by HTTP handlers or individual tool providers.
- `triggers/manager.py`: subsystem-specific management logic kept inside
  `triggers/`.
- `tools/search/orchestrator.py`: search-provider fan-out and reliability logic
  grouped under `tools/`.
