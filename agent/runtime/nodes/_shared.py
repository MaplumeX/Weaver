import asyncio
import logging
import re
from typing import Any, Union

from agent.core.llm_factory import create_chat_model
from agent.core.multi_model import resolve_model_name
from agent.core.state import AgentState, project_state_updates
from agent.research.source_url_utils import compact_unique_sources
from agent.runtime.config_utils import configurable_dict
from common.cancellation import check_cancellation as _check_cancellation
from common.config import settings

logger = logging.getLogger(__name__)

_EXACT_REPLY_QUOTED_RE = re.compile(
    r"""(?is)\b(?:reply|respond|answer|return)\s+with\s+exactly\s+["“'`](.+?)["”'`]"""
)
_EXACT_REPLY_PLAIN_RE = re.compile(
    r"""(?is)\b(?:reply|respond|answer|return)\s+with\s+exactly\s+(.+?)(?:\s+and\s+nothing\s+else\b|$)"""
)


def check_cancellation(state: Union[AgentState, dict[str, Any]]) -> None:
    """
    检查取消状态，如果已取消则抛出 CancelledError

    在长时间操作的关键点调用此函数
    """
    if state.get("is_cancelled"):
        raise asyncio.CancelledError("Task was cancelled (state flag)")

    token_id = state.get("cancel_token_id")
    if token_id:
        _check_cancellation(token_id)


def handle_cancellation(state: AgentState, error: Exception) -> dict[str, Any]:
    """
    处理取消异常，返回取消状态
    """
    logger.info(f"Task cancelled: {error}")
    result = {
        "is_cancelled": True,
        "is_complete": True,
        "errors": [f"Cancelled: {error!s}"],
        "final_report": "任务已被用户取消。",
    }
    if isinstance(state, dict) and ("input" in state or "route" in state):
        return project_state_updates(state, result)
    return result


def _event_results_limit() -> int:
    return max(1, min(20, int(getattr(settings, "deep_research_event_results_limit", 5) or 5)))


def _build_compact_unique_source_preview(
    scraped_content: Any,
    limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for run in scraped_content or []:
        if not isinstance(run, dict):
            continue

        if run.get("url"):
            candidates.append(run)
            continue

        results = run.get("results", [])
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    candidates.append(item)

    return compact_unique_sources(candidates, limit=limit)


def _extract_exact_reply_target(user_input: str) -> str | None:
    text = (user_input or "").strip()
    if not text:
        return None

    quoted = _EXACT_REPLY_QUOTED_RE.search(text)
    if quoted:
        target = quoted.group(1).strip()
        return target or None

    match = _EXACT_REPLY_PLAIN_RE.search(text)
    if not match:
        return None

    target = match.group(1).strip()
    target = re.split(r"[\r\n]", target, maxsplit=1)[0].strip()
    target = target.rstrip(" \t\r\n.,!?;:。！？；：")
    return target or None


def _apply_output_contract(user_input: str, report: str) -> str:
    target = _extract_exact_reply_target(user_input)
    if not target:
        return report

    text = (report or "").strip()
    if not text:
        return report

    normalized_text = text.strip("`*_# \t\r\n")
    normalized_text = normalized_text.rstrip(" \t\r\n.,!?;:。！？；：")
    normalized_target = target.rstrip(" \t\r\n.,!?;:。！？；：")

    if normalized_text == normalized_target:
        return target

    if re.search(rf"(?i)(?<!\w){re.escape(normalized_target)}(?!\w)", normalized_text):
        return target

    return report


_configurable = configurable_dict


_chat_model = create_chat_model


_model_for_task = resolve_model_name


__all__ = [
    "_apply_output_contract",
    "_build_compact_unique_source_preview",
    "_chat_model",
    "_configurable",
    "_event_results_limit",
    "_extract_exact_reply_target",
    "_model_for_task",
    "check_cancellation",
    "handle_cancellation",
    "logger",
    "settings",
]
