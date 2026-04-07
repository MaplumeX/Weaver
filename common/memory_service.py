from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from common.config import settings

logger = logging.getLogger(__name__)

_EPHEMERAL_HINTS = (
    "当前任务",
    "这次任务",
    "本次任务",
    "这个任务",
    "当前会话",
    "这次会话",
    "这个线程",
    "这个仓库",
    "this task",
    "current task",
    "this session",
    "this thread",
    "this repo",
    "today",
    "今天",
    "暂时",
    "temporary",
)
_PREFERENCE_HINTS = (
    "偏好",
    "喜欢",
    "prefer",
    "preference",
    "以后请",
    "always",
    "一直",
    "请用",
    "回答风格",
)
_MEMORY_PATTERNS: tuple[tuple[re.Pattern[str], str | None], ...] = (
    (re.compile(r"^\s*(?:请\s*)?(?:帮我\s*)?记住(?:一下)?[\uFF1A:,\s\uFF0C]*(?P<fact>.+?)\s*$", re.IGNORECASE), None),
    (re.compile(r"^\s*我的(?:长期)?偏好是[\uFF1A:,\s\uFF0C]*(?P<fact>.+?)\s*$", re.IGNORECASE), "preference"),
    (re.compile(r"^\s*以后请(?:一直)?[\uFF1A:,\s\uFF0C]*(?P<fact>.+?)\s*$", re.IGNORECASE), "preference"),
    (re.compile(r"^\s*(?:please\s+)?remember(?:\s+that)?[ :,\s]*(?P<fact>.+?)\s*$", re.IGNORECASE), None),
    (re.compile(r"^\s*my\s+(?:long[- ]term\s+)?preference\s+is[ :,\s]*(?P<fact>.+?)\s*$", re.IGNORECASE), "preference"),
    (re.compile(r"^\s*from\s+now\s+on[ :,\s]*(?P<fact>.+?)\s*$", re.IGNORECASE), "preference"),
)


@dataclass(frozen=True)
class MemoryCandidate:
    memory_type: str
    content: str
    normalized_key: str
    importance: int
    source_message: str


class MemoryService:
    def __init__(
        self,
        *,
        store: Any = None,
        legacy_message_fetcher: Callable[[str, int], list[str]] | None = None,
        legacy_store_loader: Callable[[str, int], list[str]] | None = None,
    ):
        self.store = store
        self.legacy_message_fetcher = legacy_message_fetcher
        self.legacy_store_loader = legacy_store_loader

    def is_configured(self) -> bool:
        return self.store is not None

    def ingest_user_message(
        self,
        *,
        user_id: str,
        text: str,
        source_kind: str,
        thread_id: str = "",
    ) -> list[dict[str, Any]]:
        if not self.store:
            return []

        candidate = self._extract_candidate_from_user_text(text)
        if candidate is None:
            return []

        entry = self.store.upsert_entry(
            user_id=user_id,
            memory_type=candidate.memory_type,
            content=candidate.content,
            normalized_key=candidate.normalized_key,
            source_kind=source_kind,
            source_thread_id=thread_id,
            source_message=candidate.source_message,
            importance=candidate.importance,
            metadata={"ingestion": "explicit_user_memory"},
        )
        self.store.record_event(
            entry_id=entry.get("id"),
            user_id=user_id,
            event_type="ingested",
            actor_type="system",
            actor_id=source_kind,
            reason="explicit user memory intent",
            payload={
                "memory_type": candidate.memory_type,
                "content": candidate.content,
                "thread_id": thread_id,
            },
        )
        return [entry]

    def build_runtime_context(
        self,
        *,
        user_id: str,
        query: str,
        limit: int | None = None,
    ) -> dict[str, list[str]]:
        context = self.debug_context(user_id=user_id, query=query, limit=limit)
        return {
            "stored": [str(item.get("content") or "") for item in context.get("stored_entries", [])],
            "relevant": [str(item.get("content") or "") for item in context.get("relevant_entries", [])],
        }

    def debug_context(
        self,
        *,
        user_id: str,
        query: str,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if not self.store:
            return {
                "stored_entries": [],
                "relevant_entries": [],
                "stored": [],
                "relevant": [],
                "migration_statuses": [],
            }

        self.ensure_user_migrated(user_id)
        size = max(1, int(limit or settings.memory_top_k or 5))
        entries = self.store.list_entries(
            user_id=user_id,
            limit=max(size * 5, 20),
            status="active",
        )
        stored_entries = [
            {
                **entry,
                "reason": "selected as top active memory by importance and recency",
            }
            for entry in entries[:size]
        ]

        relevant_entries = self._select_relevant_entries(entries, query=query, limit=size)
        touched_ids = list(
            {
                str(item.get("id") or "")
                for item in [*stored_entries, *relevant_entries]
                if str(item.get("id") or "").strip()
            }
        )
        self.store.touch_entries(entry_ids=touched_ids)

        return {
            "stored_entries": stored_entries,
            "relevant_entries": relevant_entries,
            "stored": [str(item.get("content") or "") for item in stored_entries],
            "relevant": [str(item.get("content") or "") for item in relevant_entries],
            "migration_statuses": self.store.list_migration_statuses(user_id=user_id),
        }

    def list_entries(
        self,
        *,
        user_id: str,
        limit: int = 50,
        status: str | None = None,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.store:
            return []
        self.ensure_user_migrated(user_id)
        return self.store.list_entries(
            user_id=user_id,
            limit=limit,
            status=status,
            memory_type=memory_type,
        )

    def list_events(
        self,
        *,
        user_id: str,
        entry_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not self.store:
            return []
        return self.store.list_events(user_id=user_id, entry_id=entry_id, limit=limit)

    def invalidate_entry(
        self,
        *,
        user_id: str,
        entry_id: str,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any] | None:
        if not self.store:
            return None
        entry = self.store.invalidate_entry(user_id=user_id, entry_id=entry_id, reason=reason)
        if entry:
            self.store.record_event(
                entry_id=entry_id,
                user_id=user_id,
                event_type="invalidated",
                actor_type="internal_api",
                actor_id=actor_id,
                reason=reason,
                payload={"entry_id": entry_id},
            )
        return entry

    def delete_entry(
        self,
        *,
        user_id: str,
        entry_id: str,
        actor_id: str,
        reason: str,
    ) -> bool:
        if not self.store:
            return False
        deleted = self.store.delete_entry(user_id=user_id, entry_id=entry_id)
        if not deleted:
            return False
        self.store.record_event(
            entry_id=entry_id,
            user_id=user_id,
            event_type="deleted",
            actor_type="internal_api",
            actor_id=actor_id,
            reason=reason,
            payload={"entry_id": entry_id, "content": deleted.get("content", "")},
        )
        return True

    def ensure_user_migrated(self, user_id: str) -> list[dict[str, Any]]:
        if not self.store:
            return []

        if self.legacy_message_fetcher is not None:
            self._ensure_source_migrated(
                user_id=user_id,
                source="legacy_memory_client",
                loader=self.legacy_message_fetcher,
            )
        if self.legacy_store_loader is not None:
            self._ensure_source_migrated(
                user_id=user_id,
                source="legacy_langgraph_store",
                loader=self.legacy_store_loader,
            )
        else:
            existing = self.store.get_migration_status(
                user_id=user_id,
                source="legacy_langgraph_store",
            )
            if not existing:
                self.store.upsert_migration_status(
                    user_id=user_id,
                    source="legacy_langgraph_store",
                    status="skipped",
                    details={
                        "note": "legacy langgraph store migration is unavailable in the redesigned memory service",
                    },
                )
        return self.store.list_migration_statuses(user_id=user_id)

    def _ensure_source_migrated(
        self,
        *,
        user_id: str,
        source: str,
        loader: Callable[[str, int], list[str]],
    ) -> None:
        existing = self.store.get_migration_status(user_id=user_id, source=source)
        if existing and str(existing.get("status") or "").strip() in {"completed", "skipped", "failed"}:
            return

        try:
            raw_items = list(loader(user_id, max(int(settings.memory_max_entries or 20) * 5, 20)) or [])
        except Exception as e:
            logger.warning("Legacy memory migration failed | source=%s | user_id=%s | error=%s", source, user_id, e)
            self.store.upsert_migration_status(
                user_id=user_id,
                source=source,
                status="failed",
                details={"error": str(e)},
            )
            return

        imported = 0
        skipped = 0
        for item in raw_items:
            candidate = self._extract_candidate_from_legacy_text(item)
            if candidate is None:
                skipped += 1
                continue
            entry = self.store.upsert_entry(
                user_id=user_id,
                memory_type=candidate.memory_type,
                content=candidate.content,
                normalized_key=candidate.normalized_key,
                source_kind=source,
                source_message=candidate.source_message,
                importance=candidate.importance,
                metadata={"migration_source": source},
            )
            self.store.record_event(
                entry_id=entry.get("id"),
                user_id=user_id,
                event_type="ingested",
                actor_type="migration",
                actor_id=source,
                reason="migrated legacy explicit user memory",
                payload={"content": candidate.content},
            )
            imported += 1

        status = "completed" if imported else "skipped"
        details: dict[str, Any] = {}
        if source == "legacy_langgraph_store" and not imported:
            details["note"] = "legacy store records are not structured enough to auto-convert into fact cards"
        self.store.upsert_migration_status(
            user_id=user_id,
            source=source,
            status=status,
            imported_count=imported,
            skipped_count=skipped,
            details=details,
        )
        self.store.record_event(
            user_id=user_id,
            event_type=f"migration_{status}",
            actor_type="migration",
            actor_id=source,
            reason=f"{source} migration {status}",
            payload={"imported_count": imported, "skipped_count": skipped, **details},
        )

    def _select_relevant_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        query_tokens = self._tokenize(query)
        scored: list[tuple[int, dict[str, Any], str]] = []
        for entry in entries:
            content = str(entry.get("content") or "")
            content_tokens = set(self._tokenize(content))
            overlap = sorted(token for token in query_tokens if token in content_tokens)
            base_score = int(entry.get("importance") or 0)
            if str(entry.get("memory_type") or "") == "preference":
                base_score += 1
            if overlap:
                score = base_score + len(overlap) * 10
                reason = f"matched query tokens: {', '.join(overlap)}"
                scored.append((score, entry, reason))
            elif not query_tokens:
                scored.append((base_score, entry, "selected without query tokens"))
        if not scored:
            fallback = entries[: min(limit, len(entries))]
            return [
                {
                    **entry,
                    "reason": "selected as fallback because no query-specific match was found",
                }
                for entry in fallback
            ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                **entry,
                "reason": reason,
            }
            for _, entry, reason in scored[:limit]
        ]

    def _extract_candidate_from_legacy_text(self, text: str) -> MemoryCandidate | None:
        normalized = self._clean_text(text)
        if not normalized:
            return None

        user_lines = [
            line.split(":", 1)[1].strip()
            for line in normalized.splitlines()
            if line.lower().startswith("user:")
        ]
        if user_lines:
            normalized = user_lines[0]

        return self._extract_candidate_from_user_text(normalized)

    def _extract_candidate_from_user_text(self, text: str) -> MemoryCandidate | None:
        normalized = self._clean_text(text)
        if not normalized:
            return None

        for pattern, forced_type in _MEMORY_PATTERNS:
            match = pattern.match(normalized)
            if not match:
                continue
            fact = self._clean_text(match.group("fact"))
            if not fact or len(fact) > 200 or self._is_ephemeral(fact):
                return None
            memory_type = forced_type or self._classify_memory_type(fact)
            content = self._format_content(memory_type, fact)
            normalized_key = self._normalized_key(fact)
            importance = 90 if memory_type == "preference" else 80
            return MemoryCandidate(
                memory_type=memory_type,
                content=content,
                normalized_key=normalized_key,
                importance=importance,
                source_message=normalized,
            )
        return None

    def _classify_memory_type(self, fact: str) -> str:
        lowered = fact.lower()
        if any(hint in fact for hint in _PREFERENCE_HINTS) or any(
            hint in lowered for hint in _PREFERENCE_HINTS
        ):
            return "preference"
        return "user_fact"

    def _format_content(self, memory_type: str, fact: str) -> str:
        clean_fact = fact.strip().rstrip("\u3002.!\uFF01")
        if memory_type == "preference":
            return f"用户偏好: {clean_fact}"
        return f"用户信息: {clean_fact}"

    def _is_ephemeral(self, fact: str) -> bool:
        lowered = fact.lower()
        return any(hint in fact or hint in lowered for hint in _EPHEMERAL_HINTS)

    def _tokenize(self, text: str) -> list[str]:
        normalized = self._clean_text(text).lower()
        if not normalized:
            return []
        return [
            token
            for token in re.split(r"[^\w\u4e00-\u9fff]+", normalized)
            if token and (len(token) >= 2 or any("\u4e00" <= ch <= "\u9fff" for ch in token))
        ]

    def _normalized_key(self, text: str) -> str:
        lowered = self._clean_text(text).lower()
        lowered = re.sub(r"\s+", "", lowered)
        lowered = lowered.strip("\uFF0C,\u3002.!\uFF01?\uFF1F:\uFF1A;\uFF1B")
        return lowered

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()
