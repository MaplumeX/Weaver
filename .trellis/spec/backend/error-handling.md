# Error Handling

> How errors are handled in this project.

---

## Overview

Error handling is layered:

- API boundaries return consistent JSON responses from global FastAPI exception
  handlers in `main.py`.
- Expected client problems should raise `HTTPException`.
- Missing configuration or invalid internal arguments usually raise
  `ValueError`.
- Infrastructure failures are wrapped as `RuntimeError(... ) from e` when the
  caller needs context.
- Best-effort helper paths may log and return a safe fallback instead of
  crashing the whole request.

---

## Error Types

Common patterns used in the codebase:

- `HTTPException` for request-level client errors.
- `RequestValidationError` handled globally and converted into a human-readable
  422 payload.
- `ValueError` for missing required configuration or invalid internal inputs.
- `RuntimeError` for wrapped infrastructure failures such as database
  connection/setup errors.
- Plain `Exception` is only handled at the global boundary, where it is logged
  and translated into a 500 response.

---

## Error Handling Patterns

- Validate early and fail fast on required inputs.
- Raise boundary-friendly exceptions at the edge, but wrap lower-level
  integration failures with context.
- Use `raise ... from e` when rethrowing infrastructure errors so the original
  exception is preserved in logs.
- For optional or best-effort work, log the failure and degrade gracefully
  instead of taking down the process.
- For utility methods that can safely fail locally, return `None`, `0`, or
  `False` after logging the error.

Examples:

- `agent/execution/graph.py`: `create_checkpointer()` raises `ValueError` for
  missing config and wraps connection failures as `RuntimeError`.
- `main.py`: startup/shutdown paths log warnings for optional subsystem failures
  such as MCP or trigger initialization while keeping the app running.
- `tools/io/screenshot_service.py`: local helper methods log and return safe
  fallback payloads when screenshot persistence fails.

---

## API Error Responses

All top-level API errors should converge on a consistent JSON shape:

- Validation errors return status `422` with:
  `error`, `detail`, `request_id`, `timestamp`.
- `HTTPException` responses return:
  `error`, `status_code`, `request_id`, `timestamp`.
- Unhandled exceptions return status `500` with:
  `error`, `detail`, `request_id`, `timestamp`.

Rules:

- Always attach or derive a request ID at the API boundary.
- Do not leak raw stack traces in production responses.
- In debug mode only, it is acceptable for 500 `detail` to include the
  exception string.

---

## Common Mistakes

- Do not return ad-hoc error payloads from one endpoint when a global handler
  already defines the response shape.
- Do not expose provider exceptions or stack traces to clients in production.
- Do not swallow infrastructure exceptions silently; at minimum log them.
- Do not use broad `except Exception` blocks without either re-raising or
  returning a deliberate fallback.

## Examples

- `main.py`: global handlers for `RequestValidationError`, `HTTPException`, and
  fallback `Exception`.
- `main.py`: chat endpoint raises `HTTPException(status_code=400, ...)` for
  missing user input.
- `agent/execution/graph.py`: explicit wrapping of Postgres connection failures.
- `tools/io/screenshot_service.py`: helper-level error logging with safe
  fallback return values.
