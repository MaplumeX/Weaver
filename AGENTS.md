# Repository Guidelines

## Project Structure & Module Organization
`main.py` boots the FastAPI backend. Core backend code lives in `agent/`, `tools/`, `common/`, and `triggers/`. Prompts are in `prompts/`, tests in `tests/`, scripts in `scripts/`, docs in `docs/`, and SDKs in `sdk/python/` and `sdk/typescript/`. The Next.js frontend lives in `web/`, with routes in `web/app/`, shared UI in `web/components/`, helpers in `web/lib/`, and tests in `web/tests/`.

## Build, Test, and Development Commands
Use `make setup` to create `.venv` and install backend dependencies. Use `pnpm -C web install --frozen-lockfile` for frontend dependencies. Recommended startup is `./scripts/dev.sh`; manual startup is `make dev` plus `pnpm -C web dev`. Key checks:

- `make test`: run backend `pytest`.
- `make lint`: run Ruff on changed Python files.
- `make format`: apply Ruff formatting.
- `make openapi-types`: verify OpenAPI to TypeScript type sync.
- `make verify`: run backend checks, API smoke, and frontend E2E flow.
- `pnpm -C web test | lint | build`: run frontend tests, lint, or production build.

## Coding Style & Naming Conventions
Follow `.editorconfig`: 4 spaces for Python, 2 spaces for web files, tabs only in `Makefile`, and LF line endings. Python targets 3.11 and uses Ruff (`line-length = 100`). Use `snake_case` for Python modules/functions, `PascalCase` for React components, and `camelCase` for hooks and browser utilities. Regenerate `sdk/typescript/src/openapi-types.ts` instead of editing it manually.

## Testing Guidelines
Backend tests use `pytest` in `tests/test_*.py`. Frontend tests use the Node test runner in `web/tests/*.test.ts`. Add regression tests with every behavior change, especially around streaming, OpenAPI contracts, and deep-research flows. No global coverage threshold is configured, so extend tests for touched paths and keep CI green.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects and frequent Conventional Commit prefixes such as `feat:`, `fix:`, and `refactor(scope):`; prefer `type(scope): summary`. PRs should complete `.github/pull_request_template.md`, include a concrete test plan, and update docs when behavior or setup changes. Run `make lint && make test`, run `pnpm -C web lint && pnpm -C web build` if `web/` changed, and run `docker build -f docker/Dockerfile .` if Docker files changed. Include screenshots for visible UI changes.

## Security & Agent Workflow
Copy `.env.example` and `web/.env.local.example` for local setup; never commit real secrets; run `make secret-scan` before opening a PR. This repository also tracks work with `bd` (`bd ready`, `bd show <id>`, `bd update <id> --status in_progress`), so keep issue status aligned with code changes.
