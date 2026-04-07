# Backend Development Guidelines

> Project-specific backend conventions for Weaver.

---

## Overview

Weaver is a FastAPI backend with a monolithic application entrypoint and a
modular runtime/tooling layer.

- `main.py` owns app bootstrap, Pydantic API models, middleware, exception
  handlers, and most HTTP/WebSocket endpoints.
- `agent/` contains runtime orchestration, domain contracts, prompt assembly,
  and reusable agent-facing APIs.
- `common/` contains shared infrastructure such as config, logging,
  persistence, metrics, session services, and long-term memory services.
- `tools/` contains tool integrations grouped by capability.
- `triggers/` contains the scheduled/webhook/event trigger subsystem.

Match these documents to the current codebase instead of introducing generic
"controller/service/repository" patterns that do not exist here.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module ownership, entrypoints, and placement rules | Filled |
| [Database Guidelines](./database-guidelines.md) | Runtime-managed persistence and storage backends | Filled |
| [Error Handling](./error-handling.md) | Boundary errors, safe fallbacks, and API response shape | Filled |
| [Quality Guidelines](./quality-guidelines.md) | Lint, testing, review expectations, and forbidden patterns | Filled |
| [Logging Guidelines](./logging-guidelines.md) | Standard logging bootstrap, levels, and redaction rules | Filled |

---

## Pre-Development Checklist

Read the relevant files before changing backend code:

1. Start with [Directory Structure](./directory-structure.md) to choose the
   right module.
2. Read [Database Guidelines](./database-guidelines.md) for persistence,
   storage, or schema work.
3. Read [Error Handling](./error-handling.md) and
   [Logging Guidelines](./logging-guidelines.md) for any request-path or
   integration changes.
4. Read [Quality Guidelines](./quality-guidelines.md) before finishing work.

---

## Core Rules

- Prefer matching existing module ownership over inventing new layers.
- Use typed boundaries: Pydantic models for API/tool inputs, dataclasses or
  typed state objects for internal flows.
- Keep persistence adapters close to the backend that owns them.
- Add regression tests with each behavior change.
- Treat these documents as reality, not aspirational architecture.

---

**Language**: Keep backend spec documents in **English**.
