from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

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
    (
        re.compile(
            r"^\s*(?:请\s*)?(?:帮我\s*)?(?:长期)?记住(?:一下|这件事)?[\uFF1A:,\s\uFF0C]*(?P<fact>.+?)\s*$",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        re.compile(
            r"^\s*(?:请\s*)?记一下[\uFF1A:,\s\uFF0C]*(?P<fact>.+?)\s*$",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        re.compile(
            r"^\s*(?:请\s*)?(?:把|将)(?P<fact>.+?)记住(?:一下)?\s*$",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        re.compile(
            r"^\s*我想让你记住[\uFF1A:,\s\uFF0C]*(?P<fact>.+?)\s*$",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        re.compile(
            r"^\s*我的(?:长期)?偏好是[\uFF1A:,\s\uFF0C]*(?P<fact>.+?)\s*$",
            re.IGNORECASE,
        ),
        "preference",
    ),
    (
        re.compile(
            r"^\s*以后请(?:一直)?[\uFF1A:,\s\uFF0C]*(?P<fact>.+?)\s*$",
            re.IGNORECASE,
        ),
        "preference",
    ),
    (
        re.compile(
            r"^\s*(?:please\s+)?remember(?:\s+that)?[ :,\s]*(?P<fact>.+?)\s*$",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        re.compile(
            r"^\s*my\s+(?:long[- ]term\s+)?preference\s+is[ :,\s]*(?P<fact>.+?)\s*$",
            re.IGNORECASE,
        ),
        "preference",
    ),
    (
        re.compile(
            r"^\s*from\s+now\s+on[ :,\s]*(?P<fact>.+?)\s*$",
            re.IGNORECASE,
        ),
        "preference",
    ),
)
_MEMORY_EXTRACTOR_METHODS: tuple[str | None, ...] = (None, "json_schema", "function_calling", "json_mode")
_MEMORY_EXTRACTION_PROMPT = """You extract a single durable long-term memory card from an explicit user memory instruction.

Rules:
- The source message is already an explicit memory instruction, but you must still reject content that should not be stored.
- Only store stable user preferences or stable user facts.
- Never store task-local, repo-local, session-local, or temporary information.
- Never infer from behavior. Use only what the user explicitly stated.
- Prefer concise, reusable fact phrasing.
- Return should_store=false when uncertain.
- Set stability=high only when the extracted fact is clearly durable and reusable.
- Do not include prefixes like "用户偏好:" or "用户信息:" in fact. Return plain fact text only.
- normalized_key_hint should be a short canonicalized phrase if helpful; otherwise leave it empty.
"""


@dataclass(frozen=True)
class MemoryIntent:
    fact: str
    forced_type: str | None
    source_message: str


@dataclass(frozen=True)
class MemoryCandidate:
    memory_type: str
    content: str
    normalized_key: str
    importance: int
    source_message: str
    ingestion_reason: str
    stability: str
    dedupe_basis: str


class MemoryExtractionResult(BaseModel):
    should_store: bool = Field(
        default=False,
        description="Whether this explicit memory instruction should become a durable memory entry.",
    )
    memory_type: Literal["preference", "user_fact"] | None = Field(
        default=None,
        description="Memory type when should_store is true.",
    )
    fact: str = Field(
        default="",
        description="Concise durable fact or preference text without any system prefix.",
    )
    normalized_key_hint: str | None = Field(
        default=None,
        description="Optional short canonical phrase to help dedupe similar facts.",
    )
    importance: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional importance score.",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of why the fact should or should not be stored.",
    )
    stability: Literal["high", "medium", "low"] = Field(
        default="low",
        description="Confidence that the extracted fact is stable over time.",
    )


class MemoryExtractor(Protocol):
    model_name: str
    extractor_version: str

    def extract(
        self,
        *,
        source_message: str,
        intent_fact: str,
        forced_type: str | None = None,
    ) -> MemoryExtractionResult | None: ...


class ModelBackedMemoryExtractor:
    def __init__(
        self,
        *,
        model: Any,
        model_name: str,
        extractor_version: str = "memory-explicit-v1",
        methods: tuple[str | None, ...] = _MEMORY_EXTRACTOR_METHODS,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.model_name = str(model_name or "").strip()
        self.extractor_version = str(extractor_version or "memory-explicit-v1").strip()
        self.methods = tuple(methods or _MEMORY_EXTRACTOR_METHODS)
        self.config = config or {}

    def extract(
        self,
        *,
        source_message: str,
        intent_fact: str,
        forced_type: str | None = None,
    ) -> MemoryExtractionResult | None:
        payload = {
            "source_message": source_message,
            "intent_fact": intent_fact,
            "forced_type_hint": forced_type or "",
        }
        messages = [
            SystemMessage(content=_MEMORY_EXTRACTION_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
        ]
        last_error: Exception | None = None
        for method in self.methods:
            try:
                if method is None:
                    structured_model = self.model.with_structured_output(MemoryExtractionResult)
                else:
                    structured_model = self.model.with_structured_output(
                        MemoryExtractionResult,
                        method=method,
                    )
                response = structured_model.invoke(messages, config=self.config)
                return self._coerce_response(response)
            except Exception as exc:  # pragma: no cover - exercised via fallback behavior
                last_error = exc
                logger.debug(
                    "Memory extractor method failed | method=%s | error=%s",
                    method or "default",
                    exc,
                )
        if last_error is not None:
            raise RuntimeError("memory extractor failed across all structured-output methods") from last_error
        return None

    def _coerce_response(self, response: Any) -> MemoryExtractionResult:
        if isinstance(response, MemoryExtractionResult):
            return response
        if isinstance(response, BaseModel):
            return MemoryExtractionResult.model_validate(response.model_dump())
        if isinstance(response, dict):
            return MemoryExtractionResult.model_validate(response)
        raise TypeError(f"Unsupported memory extraction response: {type(response)!r}")


class MemoryService:
    def __init__(self, *, store: Any = None, extractor: MemoryExtractor | None = None):
        self.store = store
        self.extractor = extractor

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

        intent = self._extract_memory_intent(text)
        if intent is None:
            return []

        if self.extractor is None:
            self._record_event(
                entry_id=None,
                user_id=user_id,
                event_type="ingest_skipped",
                actor_type="system",
                actor_id=source_kind,
                reason="memory extractor is not configured",
                payload={
                    "source_kind": source_kind,
                    "thread_id": thread_id,
                    "ingestion_method": "explicit_rule_llm",
                },
            )
            return []

        try:
            extraction = self.extractor.extract(
                source_message=intent.source_message,
                intent_fact=intent.fact,
                forced_type=intent.forced_type,
            )
        except Exception as exc:
            logger.warning(
                "Memory extraction failed | source=%s | thread_id=%s | error=%s",
                source_kind,
                thread_id or "-",
                exc,
            )
            self._record_event(
                entry_id=None,
                user_id=user_id,
                event_type="extract_failed",
                actor_type="system",
                actor_id=source_kind,
                reason="memory extraction failed",
                payload={
                    "source_kind": source_kind,
                    "thread_id": thread_id,
                    "ingestion_method": "explicit_rule_llm",
                    "extractor_model": self._extractor_model_name(),
                },
            )
            return []

        candidate, rejection_reason = self._candidate_from_extraction(
            extraction,
            intent=intent,
        )
        if candidate is None:
            self._record_event(
                entry_id=None,
                user_id=user_id,
                event_type="extract_rejected",
                actor_type="system",
                actor_id=source_kind,
                reason=rejection_reason,
                payload={
                    "source_kind": source_kind,
                    "thread_id": thread_id,
                    "ingestion_method": "explicit_rule_llm",
                    "extractor_model": self._extractor_model_name(),
                    "stability": getattr(extraction, "stability", "low") if extraction is not None else "low",
                },
            )
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
            metadata={
                "ingestion": "explicit_user_memory",
                "ingestion_method": "explicit_rule_llm",
                "extractor_model": self._extractor_model_name(),
                "extractor_version": self._extractor_version(),
                "ingestion_reason": candidate.ingestion_reason,
                "dedupe_basis": candidate.dedupe_basis,
                "stability": candidate.stability,
            },
        )
        self._record_event(
            entry_id=entry.get("id"),
            user_id=user_id,
            event_type="ingested",
            actor_type="system",
            actor_id=source_kind,
            reason="explicit user memory intent accepted by extractor",
            payload={
                "memory_type": candidate.memory_type,
                "content": candidate.content,
                "thread_id": thread_id,
                "source_kind": source_kind,
                "ingestion_method": "explicit_rule_llm",
                "extractor_model": self._extractor_model_name(),
                "stability": candidate.stability,
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
            }

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
            self._record_event(
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
        self._record_event(
            entry_id=entry_id,
            user_id=user_id,
            event_type="deleted",
            actor_type="internal_api",
            actor_id=actor_id,
            reason=reason,
            payload={"entry_id": entry_id, "content": deleted.get("content", "")},
        )
        return True

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

    def _extract_memory_intent(self, text: str) -> MemoryIntent | None:
        normalized = self._clean_text(text)
        if not normalized:
            return None

        for pattern, forced_type in _MEMORY_PATTERNS:
            match = pattern.match(normalized)
            if not match:
                continue
            fact = self._clean_text(match.group("fact"))
            if not fact or len(fact) > 400 or self._is_ephemeral(fact):
                return None
            return MemoryIntent(
                fact=fact,
                forced_type=forced_type,
                source_message=normalized,
            )
        return None

    def _candidate_from_extraction(
        self,
        extraction: MemoryExtractionResult | None,
        *,
        intent: MemoryIntent,
    ) -> tuple[MemoryCandidate | None, str]:
        if extraction is None:
            return None, "memory extractor returned no structured result"
        if not extraction.should_store:
            return None, "memory extractor rejected candidate"
        if extraction.stability != "high":
            return None, f"memory extractor stability was {extraction.stability}"

        fact = self._clean_text(extraction.fact)
        if not fact:
            return None, "memory extractor returned empty fact"
        if len(fact) > 200:
            return None, "memory extractor returned oversized fact"
        if self._is_ephemeral(fact):
            return None, "memory extractor returned ephemeral fact"

        memory_type = str(extraction.memory_type or intent.forced_type or "").strip()
        if memory_type not in {"preference", "user_fact"}:
            return None, "memory extractor returned invalid memory type"

        normalized_source = self._clean_text(extraction.normalized_key_hint or fact)
        normalized_key = self._normalized_key(normalized_source)
        if not normalized_key:
            return None, "memory extractor returned empty normalized key"

        importance = self._resolve_importance(extraction.importance, memory_type)
        content = self._format_content(memory_type, fact)
        reason = self._clean_text(extraction.reasoning) or "explicit user memory intent accepted by extractor"
        return (
            MemoryCandidate(
                memory_type=memory_type,
                content=content,
                normalized_key=normalized_key,
                importance=importance,
                source_message=intent.source_message,
                ingestion_reason=reason,
                stability=extraction.stability,
                dedupe_basis=normalized_key,
            ),
            "",
        )

    def _resolve_importance(self, value: int | None, memory_type: str) -> int:
        default_value = 90 if memory_type == "preference" else 80
        if value is None:
            return default_value
        return max(1, min(100, int(value)))

    def _extractor_model_name(self) -> str:
        return str(getattr(self.extractor, "model_name", "") or "").strip()

    def _extractor_version(self) -> str:
        return str(getattr(self.extractor, "extractor_version", "") or "").strip()

    def _record_event(
        self,
        *,
        user_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str = "",
        reason: str = "",
        payload: dict[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> None:
        if not self.store or not hasattr(self.store, "record_event"):
            return
        self.store.record_event(
            entry_id=entry_id,
            user_id=user_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            payload=payload if isinstance(payload, dict) else {},
        )

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

