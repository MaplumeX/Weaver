from __future__ import annotations

import py_compile
from pathlib import Path


def _iter_python_files(root: Path) -> list[Path]:
    """
    Return a stable list of Python source files we expect to be importable/compilable.

    Why this exists:
    - Some optional modules are imported under broad try/except blocks, which can
      silently swallow SyntaxError/IndentationError. A compile gate catches that.
    - We intentionally avoid compiling `web/` (frontend) and any `node_modules/`.
    """

    candidates: list[Path] = []

    # Top-level entrypoints
    for filename in ("main.py", "support_agent.py"):
        path = root / filename
        if path.is_file():
            candidates.append(path)

    # Core backend packages
    for folder in ("agent", "common", "tools", "triggers", "eval", "scripts"):
        base = root / folder
        if not base.is_dir():
            continue
        candidates.extend(sorted(base.rglob("*.py")))

    filtered: list[Path] = []
    for path in candidates:
        # Skip caches and generated artifacts
        if "__pycache__" in path.parts:
            continue
        if "node_modules" in path.parts:
            continue
        filtered.append(path)

    # De-dupe while keeping order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in filtered:
        if p in seen:
            continue
        seen.add(p)
        unique.append(p)
    return unique


def test_python_sources_compile() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = _iter_python_files(root)
    assert paths, "expected to find python files to compile"

    for path in paths:
        py_compile.compile(str(path), doraise=True)

