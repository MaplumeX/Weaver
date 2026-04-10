"""ID helpers owned by the Deep Research capability."""

from __future__ import annotations

import uuid


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


__all__ = ["_new_id"]
