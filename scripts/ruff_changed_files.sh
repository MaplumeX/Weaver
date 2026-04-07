#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_REF="${BASE_REF:-}"
HEAD_REF="${HEAD_REF:-HEAD}"

if [[ -z "$BASE_REF" ]]; then
  if [[ -n "${GITHUB_BASE_REF:-}" ]]; then
    BASE_REF="origin/${GITHUB_BASE_REF}"
  else
    # Default branch heuristic.
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
      BASE_REF="origin/main"
    elif git rev-parse --verify origin/master >/dev/null 2>&1; then
      BASE_REF="origin/master"
    else
      BASE_REF="HEAD~1"
    fi
  fi
fi

# Ensure the base ref exists in shallow checkouts.
if [[ "$BASE_REF" == origin/* ]]; then
  remote_branch="${BASE_REF#origin/}"
  git fetch origin "$remote_branch" --depth=1 >/dev/null 2>&1 || true
fi

CHANGED_PY_FILES="$(
  git diff --name-only "${BASE_REF}...${HEAD_REF}" -- '*.py' \
    | awk '!/^\.trellis\//' \
    | tr '\n' ' '
)"

if [[ -z "${CHANGED_PY_FILES// }" ]]; then
  echo "ruff: no changed Python files detected (${BASE_REF}...${HEAD_REF})"
  exit 0
fi

echo "ruff: checking changed files (${BASE_REF}...${HEAD_REF})"
echo "$CHANGED_PY_FILES" | tr ' ' '\n'

# Prefer repo-local virtualenv when available.
RUFF_BIN=""
if [[ -x "$ROOT_DIR/.venv/bin/ruff" ]]; then
  RUFF_BIN="$ROOT_DIR/.venv/bin/ruff"
elif command -v ruff >/dev/null 2>&1; then
  RUFF_BIN="$(command -v ruff)"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  RUFF_BIN="$ROOT_DIR/.venv/bin/python -m ruff"
elif command -v python3 >/dev/null 2>&1; then
  RUFF_BIN="$(command -v python3) -m ruff"
elif command -v python >/dev/null 2>&1; then
  RUFF_BIN="$(command -v python) -m ruff"
else
  echo "ruff: no ruff executable found" >&2
  exit 1
fi

# High-signal lint only; avoids blocking on historical style debt.
$RUFF_BIN check \
  --select E,W,F,I,B \
  --ignore E501,B008,B904 \
  $CHANGED_PY_FILES
