# Logging Guidelines

> How logging is done in this project.

---

## Overview

The project uses the standard `logging` package with a shared bootstrap in
`common/logger.py`.

Current behavior:

- `main.py` calls `setup_logging()` once during process startup.
- Logging can be plain text or JSON, depending on settings.
- File logging is optional and uses a rotating file handler.
- The root logger is marked as configured to avoid duplicate handlers under
  reload.
- Third-party logger noise is reduced centrally instead of per-call-site.

---

## Log Levels

- `DEBUG`: verbose diagnostics that are useful during investigation but too
  noisy for normal operation. Examples include message previews, node-level
  transitions, and cache/debug details.
- `INFO`: normal lifecycle milestones and high-signal operational events such as
  startup, shutdown, request start, route selection, and subsystem readiness.
- `WARNING`: recoverable misconfiguration or degraded behavior. Use when the
  request/process can continue but the operator should notice.
- `ERROR`: request failures, infrastructure errors, or unexpected exceptions.
  Include `exc_info=True` when traceback context matters.

Examples:

- `main.py` logs request start and selected chat mode at `INFO`.
- `main.py` logs validation errors and optional subsystem failures at
  `WARNING`.
- `main.py` and `tools/*` log unexpected failures at `ERROR`, often with
  `exc_info=True`.

---

## Structured Logging

- Module code should use `logging.getLogger(__name__)` or
  `common.logger.get_logger(__name__)`.
- JSON mode emits:
  `timestamp`, `level`, `logger`, `message`, `module`, `function`, `line`.
- Optional context fields currently supported by the formatter are:
  `user_id`, `request_id`, and `thread_id`.
- When a subsystem has a recognizable prefix, keep it stable in the message
  (`[trigger_manager]`, `[sandbox_browser]`, `[MultiSearch]`).
- Reuse the shared bootstrap instead of hand-configuring handlers inside
  feature modules.

Examples:

- `common/logger.py`: `JSONFormatter`, rotating file handler, and handler
  deduplication.
- `triggers/manager.py`: consistent subsystem prefixing with
  `[trigger_manager]`.
- `tools/search/multi_search.py`: capability-specific prefixes like
  `[MultiSearch]`.

---

## What to Log

- Process startup/shutdown and backend mode selection.
- Incoming requests and major request-shaping decisions.
- Storage backend initialization and failures.
- Trigger lifecycle changes.
- Optional dependency fallbacks and degraded runtime behavior.
- High-signal tool/provider outcomes, especially when switching strategy or
  returning partial results.

---

## What NOT to Log

- Never log secrets, API keys, auth headers, cookies, or raw credentials.
- Do not log full user content at `INFO`; keep verbose previews short and
  `DEBUG`-only.
- Do not emit duplicate handlers or feature-local logging setup.
- Do not rely on noisy third-party defaults when the shared bootstrap already
  suppresses them.

## Examples

- `common/logger.py`: redaction-safe shared formatter and handler setup.
- `main.py`: logs message length at `INFO` and message preview at `DEBUG`.
- `main.py`: request middleware creates request-scoped operational logs.
- `triggers/manager.py`: subsystem lifecycle logging without leaking payload
  secrets.
