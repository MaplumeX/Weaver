from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from common.config import settings


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class KnowledgeFileRecord(BaseModel):
    id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    content_type: str = ""
    extension: str = ""
    size_bytes: int = 0
    content_hash: str = ""
    bucket: str = ""
    object_key: str = ""
    download_path: str = ""
    collection_name: str = ""
    status: str = "uploaded"
    parser_name: str = ""
    chunk_count: int = 0
    indexed_at: str | None = None
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)


@dataclass(frozen=True)
class KnowledgeRegistryPaths:
    root: Path
    file: Path


_LOCK = threading.Lock()


def default_registry_paths(project_root: Path | None = None) -> KnowledgeRegistryPaths:
    override = (os.getenv("WEAVER_DATA_DIR") or "").strip()
    if override:
        data_dir = Path(override).expanduser()
        if not data_dir.is_absolute():
            data_dir = (Path.cwd() / data_dir).resolve()
        return KnowledgeRegistryPaths(root=data_dir, file=data_dir / settings.knowledge_registry_file)

    root = project_root or Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    return KnowledgeRegistryPaths(root=data_dir, file=data_dir / settings.knowledge_registry_file)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class KnowledgeRegistry:
    def __init__(self, paths: KnowledgeRegistryPaths | None = None) -> None:
        self.paths = paths or default_registry_paths()

    def list_records(self) -> list[KnowledgeFileRecord]:
        with _LOCK:
            if not self.paths.file.exists():
                return []
            raw = json.loads(self.paths.file.read_text(encoding="utf-8") or "[]")
            if not isinstance(raw, list):
                return []
            records: list[KnowledgeFileRecord] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                try:
                    records.append(KnowledgeFileRecord.model_validate(item))
                except Exception:
                    continue
            records.sort(key=lambda item: item.updated_at, reverse=True)
            return records

    def get_record(self, record_id: str) -> KnowledgeFileRecord | None:
        for item in self.list_records():
            if item.id == record_id:
                return item
        return None

    def find_record_by_content_hash(
        self,
        content_hash: str,
        *,
        exclude_id: str | None = None,
    ) -> KnowledgeFileRecord | None:
        target = str(content_hash or "").strip()
        if not target:
            return None
        for item in self.list_records():
            if exclude_id and item.id == exclude_id:
                continue
            if str(item.content_hash or "").strip() == target:
                return item
        return None

    def upsert_record(self, record: KnowledgeFileRecord) -> KnowledgeFileRecord:
        now = _utc_now_iso()
        updated = record.model_copy(update={"updated_at": now})
        existing = self.list_records()
        merged: list[KnowledgeFileRecord] = []
        replaced = False
        for item in existing:
            if item.id != updated.id:
                merged.append(item)
                continue
            merged.append(updated)
            replaced = True
        if not replaced:
            merged.append(updated.model_copy(update={"created_at": now, "updated_at": now}))
        payload = [item.model_dump(mode="json") for item in merged]
        with _LOCK:
            _atomic_write_json(self.paths.file, payload)
        return self.get_record(updated.id) or updated

    def delete_record(self, record_id: str) -> KnowledgeFileRecord | None:
        existing = self.list_records()
        kept: list[KnowledgeFileRecord] = []
        removed: KnowledgeFileRecord | None = None

        for item in existing:
            if item.id == record_id and removed is None:
                removed = item
                continue
            kept.append(item)

        if removed is None:
            return None

        payload = [item.model_dump(mode="json") for item in kept]
        with _LOCK:
            _atomic_write_json(self.paths.file, payload)
        return removed


__all__ = [
    "KnowledgeFileRecord",
    "KnowledgeRegistry",
    "KnowledgeRegistryPaths",
    "default_registry_paths",
]
