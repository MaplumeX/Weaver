# Directory Structure

> How backend code is organized in this project.

---

## Overview

The backend is centered around a single FastAPI application entrypoint and a
set of capability-focused packages.

- `main.py` is the backend composition root. It contains app startup,
  middleware, exception handlers, request/response models, and most routes.
- `agent/` contains agent runtime orchestration, contracts, prompts, and
  reusable agent APIs.
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
│   ├── api.py
│   ├── application/
│   ├── contracts/
│   ├── core/
│   ├── infrastructure/
│   ├── prompts/
│   ├── research/
│   └── runtime/
├── common/
│   ├── config.py
│   ├── logger.py
│   ├── persistence_schema.py
│   ├── session_service.py
│   └── session_store.py
├── tools/
│   ├── browser/
│   ├── code/
│   ├── crawl/
│   ├── export/
│   ├── io/
│   ├── rag/
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
- Put reusable runtime logic under `agent/`, especially when it is part of the
  graph, prompt/runtime contracts, or agent composition.
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
  `agent/api.py` and `agent/contracts/research.py` are preferred over broad
  wildcard imports.

---

## Naming Conventions

- Use `snake_case.py` for Python modules and functions.
- Prefer capability-oriented names over vague utility buckets. Examples:
  `session_store.py`, `sandbox_browser_session.py`, `quality_assessor.py`.
- Keep package names singular and responsibility-focused (`agent/runtime`,
  `tools/search`, `common`).
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
- `agent/runtime/graph.py`: runtime orchestration code placed under `agent/`
  instead of the HTTP layer.
- `triggers/manager.py`: subsystem-specific management logic kept inside
  `triggers/`.
- `tools/rag/vector_store.py`: external capability adapter grouped under
  `tools/`.
