# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

Backend quality is enforced through typed boundaries, focused package ownership,
Ruff, and a large regression-heavy pytest suite.

Baseline expectations:

- Python target is 3.11.
- Formatting and linting follow `.editorconfig` and `pyproject.toml`.
- Behavior changes should come with regression tests.
- API contracts and persistence behavior are treated as stable surfaces.

---

## Forbidden Patterns

- Do not introduce SQLAlchemy/Alembic-style abstractions into a persistence path
  that currently uses direct `psycopg`, LangGraph stores, ChromaDB, or JSON
  files.
- Do not bypass typed API boundaries with unvalidated raw payload handling when
  the surrounding code already uses Pydantic models.
- Do not create broad wildcard public APIs; keep export surfaces explicit.
- Do not write to repo-local mutable data during tests when a temp dir or
  `WEAVER_DATA_DIR` override is available.
- Do not leak secrets, auth material, or production stack traces into logs or
  client responses.

---

## Required Patterns

- Add type hints to public/backend-facing functions and data structures.
- Use Pydantic models for HTTP and tool argument boundaries.
- Keep module ownership clear:
  reusable runtime logic belongs in `agent/`, shared infra in `common/`,
  concrete integrations in `tools/`.
- Add or update regression tests whenever behavior, contracts, or persistence
  change.
- Use existing build and verification entrypoints:
  `make lint`, `make test`, `make openapi-types`, and targeted pytest runs.
- Preserve stable public surfaces with explicit facade modules where they
  already exist.

Examples:

- `agent/api.py`: small explicit public API for the `agent` package.
- `agent/contracts/research.py`: narrow contract surface instead of broad
  package re-exports.
- `main.py`: request and response models use Pydantic rather than ad-hoc dicts.

---

## Testing Requirements

- Backend tests live in `tests/test_*.py`.
- Use `pytest` with `monkeypatch` for configuration and integration seams.
- For HTTP endpoints, prefer `httpx.AsyncClient` with `ASGITransport`; use
  `fastapi.testclient.TestClient` where WebSocket coverage is easier.
- Add focused regression tests for:
  API contracts,
  persistence behavior,
  SSE/WebSocket flows,
  optional dependency fallbacks,
  auth/rate-limit behavior,
  generated OpenAPI drift when relevant.
- Storage and runtime bootstrapping changes should assert concrete connection
  parameters, not just happy-path behavior.

---

## Code Review Checklist

- Is the code placed in the owning module/package instead of adding a new
  generic layer?
- Does the change match current persistence patterns and avoid hidden migration
  risk?
- Are errors and logs consistent with the shared API/logging conventions?
- Are request/response boundaries typed and validated?
- Are regression tests added or updated for the changed behavior?
- If an API contract changed, were OpenAPI-dependent artifacts checked?

## Examples

- `tests/test_checkpointer_config.py`: verifies exact Postgres connection
  settings instead of only asserting success.
- `tests/test_sandbox_diagnose.py`: validates actionable degraded-mode
  responses.
- `tests/test_browser_ws_actionable_errors.py`: uses WebSocket tests for
  protocol behavior that plain unit tests would miss.
- `scripts/ruff_changed_files.sh` and `pyproject.toml`: project lint
  expectations and enforced rule set.
