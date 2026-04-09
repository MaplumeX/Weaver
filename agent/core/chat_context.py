from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from agent.core.message_utils import summarize_history_slice
from common.config import settings

_PINNED_HINTS = (
    "请用",
    "请不要",
    "不要",
    "必须",
    "请始终",
    "输出格式",
    "以后",
    "always",
    "must",
    "format",
    "respond in",
)


def _normalized_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    data = snapshot if isinstance(snapshot, dict) else {}
    return {
        "version": int(data.get("version") or 1),
        "summarized_through_seq": max(int(data.get("summarized_through_seq") or 0), 0),
        "rolling_summary": str(data.get("rolling_summary") or "").strip(),
        "pinned_items": [
            str(item).strip()
            for item in (data.get("pinned_items") or [])
            if str(item).strip()
        ],
        "open_questions": [
            str(item).strip() for item in (data.get("open_questions") or []) if str(item).strip()
        ],
        "recent_tools": [
            str(item).strip()
            for item in (data.get("recent_tools") or [])
            if str(item).strip()
        ],
        "recent_sources": [
            str(item).strip() for item in (data.get("recent_sources") or []) if str(item).strip()
        ],
        "updated_at": str(data.get("updated_at") or "").strip(),
    }


def normalize_short_term_context(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return _normalized_snapshot(snapshot)


def _message_seq(message: dict[str, Any]) -> int:
    try:
        return int(message.get("seq") or 0)
    except (TypeError, ValueError):
        return 0


def _normalized_messages(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    items = [message for message in (messages or []) if isinstance(message, dict)]
    return sorted(items, key=_message_seq)


def _session_message_to_langchain_message(message: dict[str, Any]) -> BaseMessage | None:
    role = str(message.get("role") or "").strip().lower()
    content = str(message.get("content") or "").strip()
    if not content:
        return None
    if role in {"human", "user"}:
        return HumanMessage(content=content)
    if role in {"ai", "assistant"}:
        return AIMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    return None


def build_recent_runtime_messages(
    messages: list[dict[str, Any]] | None,
    *,
    limit: int | None = None,
) -> list[BaseMessage]:
    window = max(int(limit or getattr(settings, "chat_recent_turns", 6) or 6), 1)
    normalized = _normalized_messages(messages)
    recent = normalized[-window:]
    runtime_messages: list[BaseMessage] = []
    for message in recent:
        converted = _session_message_to_langchain_message(message)
        if converted is not None:
            runtime_messages.append(converted)
    return runtime_messages


def short_term_context_fetch_limit() -> int:
    recent_limit = max(int(getattr(settings, "chat_recent_turns", 6) or 6), 1)
    summary_trigger = max(
        int(
            getattr(settings, "chat_short_term_summary_trigger_turns", recent_limit + 2)
            or (recent_limit + 2)
        ),
        recent_limit,
    )
    derived = max(recent_limit + 4, summary_trigger + 1, 12)
    return min(derived, 50)


def _dedupe_keep_recent(items: list[str], *, limit: int) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in reversed(items):
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
        if len(ordered) >= limit:
            break
    return list(reversed(ordered))


def _extract_pinned_items(messages: list[dict[str, Any]], *, limit: int) -> list[str]:
    candidates: list[str] = []
    for message in messages:
        if str(message.get("role") or "").strip().lower() not in {"human", "user"}:
            continue
        content = str(message.get("content") or "").strip()
        if not content or len(content) > 240:
            continue
        lowered = content.lower()
        if any(hint in content or hint in lowered for hint in _PINNED_HINTS):
            candidates.append(content)
    return _dedupe_keep_recent(candidates, limit=limit)


def _extract_open_questions(messages: list[dict[str, Any]], *, limit: int) -> list[str]:
    if not messages:
        return []
    latest = messages[-1]
    role = str(latest.get("role") or "").strip().lower()
    if role not in {"ai", "assistant"}:
        return []
    content = str(latest.get("content") or "").strip()
    if not content:
        return []
    parts = [
        segment.strip()
        for segment in content.replace("?", "?\n").replace("？", "？\n").splitlines()
        if segment.strip()
    ]
    questions = [part for part in parts if part.endswith("?") or part.endswith("？")]
    return questions[:limit]


def _format_tool_summary(invocation: dict[str, Any]) -> str:
    tool_name = str(
        invocation.get("toolName") or invocation.get("toolId") or invocation.get("name") or ""
    ).strip()
    state = str(invocation.get("state") or invocation.get("status") or "").strip()
    args = invocation.get("args") if isinstance(invocation.get("args"), dict) else {}
    query = str(args.get("query") or args.get("q") or "").strip()
    details = [tool_name]
    if query:
        details.append(f"query={query}")
    if state:
        details.append(state)
    return " | ".join(part for part in details if part)


def _extract_recent_tools(messages: list[dict[str, Any]], *, limit: int) -> list[str]:
    items: list[str] = []
    for message in reversed(messages):
        raw_tool_invocations = message.get("tool_invocations")
        tool_invocations = raw_tool_invocations if isinstance(raw_tool_invocations, list) else []
        for invocation in tool_invocations:
            if not isinstance(invocation, dict):
                continue
            summary = _format_tool_summary(invocation)
            if summary:
                items.append(summary)
        raw_process_events = message.get("process_events")
        process_events = raw_process_events if isinstance(raw_process_events, list) else []
        for event in process_events:
            if not isinstance(event, dict) or str(event.get("type") or "") != "tool":
                continue
            payload = event.get("data") if isinstance(event.get("data"), dict) else event
            summary = _format_tool_summary(payload if isinstance(payload, dict) else {})
            if summary:
                items.append(summary)
        if len(items) >= limit * 2:
            break
    return _dedupe_keep_recent(items, limit=limit)


def _format_source_summary(source: dict[str, Any]) -> str:
    title = str(source.get("title") or "").strip()
    url = str(source.get("url") or source.get("rawUrl") or "").strip()
    if title and url:
        return f"{title} ({url})"
    return title or url


def _extract_recent_sources(messages: list[dict[str, Any]], *, limit: int) -> list[str]:
    items: list[str] = []
    for message in reversed(messages):
        sources = message.get("sources") if isinstance(message.get("sources"), list) else []
        for source in sources:
            if not isinstance(source, dict):
                continue
            summary = _format_source_summary(source)
            if summary:
                items.append(summary)
        if len(items) >= limit * 2:
            break
    return _dedupe_keep_recent(items, limit=limit)


def build_short_term_snapshot(
    messages: list[dict[str, Any]] | None,
    *,
    previous_snapshot: dict[str, Any] | None = None,
    now_iso: str | None = None,
) -> dict[str, Any]:
    normalized = _normalized_messages(messages)
    previous = _normalized_snapshot(previous_snapshot)
    recent_limit = max(int(getattr(settings, "chat_recent_turns", 6) or 6), 1)
    summary_trigger = max(
        int(
            getattr(settings, "chat_short_term_summary_trigger_turns", recent_limit + 2)
            or (recent_limit + 2)
        ),
        recent_limit,
    )
    pinned_limit = max(int(getattr(settings, "chat_short_term_pinned_max_items", 8) or 8), 1)
    open_question_limit = max(
        int(getattr(settings, "chat_short_term_open_questions_max_items", 5) or 5),
        1,
    )
    recent_tools_limit = max(
        int(getattr(settings, "chat_short_term_recent_tools_max_items", 5) or 5),
        1,
    )
    recent_sources_limit = max(
        int(getattr(settings, "chat_short_term_recent_sources_max_items", 5) or 5),
        1,
    )

    recent_window = normalized[-recent_limit:]
    summary_cutoff_seq = (
        _message_seq(recent_window[0])
        - 1
        if recent_window and len(normalized) > recent_limit
        else 0
    )
    previous_summary_seq = max(int(previous.get("summarized_through_seq") or 0), 0)
    rolling_summary = str(previous.get("rolling_summary") or "").strip()

    if len(normalized) > summary_trigger and summary_cutoff_seq > previous_summary_seq:
        slice_messages = [
            item
            for item in normalized
            if previous_summary_seq < _message_seq(item) <= summary_cutoff_seq
        ]
        langchain_messages = [
            converted
            for converted in (
                _session_message_to_langchain_message(item) for item in slice_messages
            )
            if converted is not None
        ]
        if langchain_messages:
            rolling_summary = summarize_history_slice(
                langchain_messages,
                previous_summary=rolling_summary,
            )
            previous_summary_seq = summary_cutoff_seq

    return {
        "version": 1,
        "summarized_through_seq": previous_summary_seq,
        "rolling_summary": rolling_summary,
        "pinned_items": _extract_pinned_items(normalized, limit=pinned_limit),
        "open_questions": _extract_open_questions(normalized, limit=open_question_limit),
        "recent_tools": _extract_recent_tools(normalized, limit=recent_tools_limit),
        "recent_sources": _extract_recent_sources(normalized, limit=recent_sources_limit),
        "updated_at": now_iso or datetime.now(UTC).isoformat(),
    }


__all__ = [
    "build_recent_runtime_messages",
    "build_short_term_snapshot",
    "normalize_short_term_context",
    "short_term_context_fetch_limit",
]
