import asyncio
import json
import logging
import mimetypes
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from agent.core.middleware import retry_call
from agent.core.state import AgentState, QueryState
from agent.runtime.deep.shared import _auto_mode_prefers_linear
from agent.workflows.source_url_utils import compact_unique_sources
from common.cancellation import check_cancellation as _check_cancellation
from common.config import settings
from tools import execute_python_code, tavily_search
from tools.core.registry import get_global_registry, get_registered_tools

ENHANCED_TOOLS_AVAILABLE = True

logger = logging.getLogger(__name__)

_EXACT_REPLY_QUOTED_RE = re.compile(
    r"""(?is)\b(?:reply|respond|answer|return)\s+with\s+exactly\s+["“'`](.+?)["”'`]"""
)
_EXACT_REPLY_PLAIN_RE = re.compile(
    r"""(?is)\b(?:reply|respond|answer|return)\s+with\s+exactly\s+(.+?)(?:\s+and\s+nothing\s+else\b|$)"""
)
_FAST_VERIFY_PREFIX_RE = re.compile(
    r"""(?is)^\s*(?:please\s+)?(?:use|using)\s+(?:current\s+)?web\s+search\s+to\s+verify\b[\s:：,-]*"""
)
_FAST_VERIFY_INLINE_RE = re.compile(
    r"""(?is)^\s*(?:please\s+)?verify(?:\s+this|\s+that)?\b[\s:：,-]*"""
)
_FAST_VERIFY_PREFIX_ZH_RE = re.compile(
    r"""(?is)^\s*(?:请)?(?:使用|用)(?:当前)?(?:网络|网页|web)?搜索(?:来)?验证[\s:：,-]*"""
)
_FAST_REPLY_SUFFIX_ZH_RE = re.compile(
    r"""(?is)[\s,，;；:：-]*(?:只回答|仅回答|只需回答|回答时只输出|只输出).*$"""
)
_FAST_COMPARE_PREFIX_RE = re.compile(
    r"""(?is)^\s*(?:please\s+)?(?:use|using)\s+(?:current\s+)?web\s+search\s+to\s+compare\b[\s:：,-]*"""
)
_FAST_COMPARE_INLINE_RE = re.compile(
    r"""(?is)^\s*(?:please\s+)?compare\b[\s:：,-]*"""
)
_FAST_COMPARE_PREFIX_ZH_RE = re.compile(
    r"""(?is)^\s*(?:请)?(?:使用|用)(?:当前)?(?:网络|网页|web)?搜索(?:来)?(?:比较|对比)[\s:：,-]*"""
)
_FAST_COMPARE_FORMAT_SUFFIX_RE = re.compile(
    r"""(?is)[\s,，;；:：-]*(?:in\s+one\s+sentence|in\s+a\s+sentence|briefly|succinctly|shortly|简短(?:地)?|简要(?:地)?|一句话|一段话).*$"""
)
_NARROW_COMPARE_SIGNALS = (
    "compare",
    "comparison",
    "versus",
    "vs",
    "比较",
    "对比",
)
_NARROW_COMPARE_ATTRIBUTE_CUES = (
    "capital",
    "capitals",
    "population",
    "populations",
    "gdp",
    "currency",
    "currencies",
    "area",
    "areas",
    "price",
    "prices",
    "leader",
    "leaders",
    "president",
    "presidents",
    "prime minister",
    "mayor",
    "founder",
    "founded",
    "headquarters",
    "market cap",
    "stock price",
    "exchange rate",
    "首都",
    "人口",
    "货币",
    "面积",
    "价格",
    "总统",
    "总理",
    "市长",
    "总部",
)
_NARROW_COMPARE_FORMAT_CUES = (
    "one sentence",
    "in a sentence",
    "briefly",
    "succinctly",
    "shortly",
    "一句话",
    "简短",
    "简要",
    "只回答",
)
_NARROW_COMPARE_BROAD_CUES = (
    "analysis",
    "analyze",
    "assess",
    "case study",
    "evaluate",
    "framework",
    "history",
    "histor",
    "impact",
    "investigate",
    "market",
    "overview",
    "policy",
    "regulation",
    "report",
    "research",
    "risk",
    "risks",
    "sourcing",
    "supply chain",
    "timeline",
    "trade-off",
    "tradeoffs",
    "trend",
    "trends",
    "分析",
    "影响",
    "政策",
    "法规",
    "研究",
    "风险",
    "供应链",
    "趋势",
    "历史",
)


def check_cancellation(state: Union[AgentState, QueryState, Dict[str, Any]]) -> None:
    """
    检查取消状态，如果已取消则抛出 CancelledError

    在长时间操作的关键点调用此函数
    """
    if state.get("is_cancelled"):
        raise asyncio.CancelledError("Task was cancelled (state flag)")

    token_id = state.get("cancel_token_id")
    if token_id:
        _check_cancellation(token_id)


def handle_cancellation(state: AgentState, error: Exception) -> Dict[str, Any]:
    """
    处理取消异常，返回取消状态
    """
    logger.info(f"Task cancelled: {error}")
    return {
        "is_cancelled": True,
        "is_complete": True,
        "errors": [f"Cancelled: {str(error)}"],
        "final_report": "任务已被用户取消。",
    }


def _event_results_limit() -> int:
    return max(1, min(20, int(getattr(settings, "deepsearch_event_results_limit", 5) or 5)))


def _build_compact_unique_source_preview(
    scraped_content: Any,
    limit: int,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

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


def _extract_exact_reply_target(user_input: str) -> Optional[str]:
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


def _is_tool_enabled(profile: Dict[str, Any], key: str, default: bool = False) -> bool:
    enabled_tools = profile.get("enabled_tools") or {}
    if isinstance(enabled_tools, dict) and key in enabled_tools:
        return bool(enabled_tools.get(key))
    return default


def _is_narrow_comparison_prompt(user_input: str) -> bool:
    text = re.sub(r"\s+", " ", str(user_input or "")).strip()
    if not text:
        return False

    lowered = text.lower()
    if not any(signal in lowered for signal in _NARROW_COMPARE_SIGNALS):
        return False
    if any(cue in lowered for cue in _NARROW_COMPARE_BROAD_CUES):
        return False

    token_count = len(re.findall(r"\w+", lowered))
    has_attribute_cue = any(cue in lowered for cue in _NARROW_COMPARE_ATTRIBUTE_CUES)
    has_format_cue = any(cue in lowered for cue in _NARROW_COMPARE_FORMAT_CUES)

    if has_attribute_cue and token_count <= 20:
        return True
    if has_attribute_cue and has_format_cue:
        return True
    return False


def _configurable(config: RunnableConfig) -> Dict[str, Any]:
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        if isinstance(cfg, dict):
            return cfg
    return {}


def _should_use_fast_agent_path(state: AgentState, config: RunnableConfig) -> bool:
    user_input = str(state.get("input", "") or "").strip()
    if not user_input or state.get("images"):
        return False
    if not (_auto_mode_prefers_linear(user_input) or _is_narrow_comparison_prompt(user_input)):
        return False

    profile = _configurable(config).get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    return _is_tool_enabled(profile, "web_search", default=True)


def _build_fast_agent_search_query(user_input: str) -> str:
    text = re.sub(r"\s+", " ", str(user_input or "")).strip()
    if not text:
        return ""

    text = _FAST_VERIFY_PREFIX_RE.sub("", text)
    text = _FAST_VERIFY_INLINE_RE.sub("", text)
    text = _FAST_VERIFY_PREFIX_ZH_RE.sub("", text)
    text = _FAST_COMPARE_PREFIX_RE.sub("", text)
    text = _FAST_COMPARE_INLINE_RE.sub("", text)
    text = _FAST_COMPARE_PREFIX_ZH_RE.sub("", text)
    text = _EXACT_REPLY_QUOTED_RE.sub("", text)
    text = _EXACT_REPLY_PLAIN_RE.sub("", text)
    text = _FAST_COMPARE_FORMAT_SUFFIX_RE.sub("", text)
    text = _FAST_REPLY_SUFFIX_ZH_RE.sub("", text)

    text = text.strip(" \t\r\n\"'`“”‘’")
    text = re.sub(r"^[,:：-]+\s*", "", text)
    return text or str(user_input or "").strip()


def _format_fast_search_results(results: List[Dict[str, Any]], limit: int = 3) -> str:
    blocks: List[str] = []
    for idx, item in enumerate(results[:limit], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "Untitled result").strip()
        url = str(item.get("url", "") or "").strip()
        snippet = (
            item.get("summary")
            or item.get("snippet")
            or item.get("raw_excerpt")
            or ""
        )
        snippet = re.sub(r"\s+", " ", str(snippet or "")).strip()
        if len(snippet) > 700:
            snippet = snippet[:700] + "..."
        block = f"[{idx}] {title}"
        if url:
            block += f"\nURL: {url}"
        if snippet:
            block += f"\nEvidence: {snippet}"
        blocks.append(block)
    return "\n\n".join(blocks)


def _run_fast_agent_search(
    query: str,
    config: RunnableConfig,
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    if not query:
        return None, []

    call_kwargs = {"query": query, "max_results": 3}

    if len(settings.search_engines_list) > 1:
        from tools.search.fallback_search import run_fallback_search

        if settings.tool_retry:
            return retry_call(
                run_fallback_search,
                attempts=settings.tool_retry_max_attempts,
                backoff=settings.tool_retry_backoff,
                **call_kwargs,
            )
        return run_fallback_search(**call_kwargs)

    if settings.tool_retry:
        results = retry_call(
            tavily_search.invoke,
            attempts=settings.tool_retry_max_attempts,
            backoff=settings.tool_retry_backoff,
            **{"input": call_kwargs, "config": config},
        )
    else:
        results = tavily_search.invoke(call_kwargs, config=config)
    return getattr(tavily_search, "name", "tavily_search"), results or []


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.compat.nodes")
    if compat is not None:
        return compat
    return sys.modules[__name__]


def _answer_simple_agent_query(
    state: AgentState,
    config: RunnableConfig,
    _deps: Any = None,
) -> Optional[Dict[str, Any]]:
    deps = _resolve_deps(_deps)
    user_input = str(state.get("input", "") or "").strip()
    search_query = deps._build_fast_agent_search_query(user_input)
    if not search_query:
        return None

    t0 = time.time()
    try:
        provider, results = deps._run_fast_agent_search(search_query, config)
    except Exception as e:
        logger.warning(f"[agent_node] Fast search path failed for '{search_query[:80]}': {e}")
        return None

    if not results:
        logger.info("[agent_node] Fast search path found no results; falling back to full agent")
        return None

    evidence = deps._format_fast_search_results(results)
    if not evidence:
        return None

    messages: List[Any] = []
    for seeded in state.get("messages") or []:
        if isinstance(seeded, SystemMessage):
            messages.append(seeded)

    messages.append(
        SystemMessage(
            content=(
                "You are Weaver in fast verification mode. "
                "You already have current web evidence. "
                "Answer the user's question directly using only the provided evidence. "
                "Prefer the most authoritative and consistent evidence. "
                "If the request is a comparison, compare only the specific dimension the user asked for and do not introduce adjacent metrics. "
                "Keep the answer concise. If the user requested an exact reply format, follow it exactly. "
                "Do not add a sources section unless the user explicitly asked for it."
            )
        )
    )
    messages.append(
        HumanMessage(
            content=(
                f"User question:\n{user_input}\n\n"
                f"Search query used:\n{search_query}\n\n"
                f"Current search evidence:\n{evidence}\n\n"
                "Return the best final answer."
            )
        )
    )

    llm = deps._chat_model(deps._model_for_task("writing", config), temperature=0.2)
    response = llm.invoke(messages, config=config)
    deps._log_usage(response, "agent_fast_search")

    content = response.content if hasattr(response, "content") else str(response)
    content = deps._apply_output_contract(user_input, content)

    logger.info(f"[timing] agent_fast_search {(time.time() - t0):.3f}s")
    return {
        "scraped_content": [
            {
                "query": search_query,
                "results": results,
                "provider": provider,
                "timestamp": datetime.now().isoformat(),
                "fast_path": True,
            }
        ],
        "draft_report": content,
        "final_report": content,
        "is_complete": False,
        "messages": [AIMessage(content=content)],
    }


def _chat_model(
    model: str,
    temperature: float,
    extra_body: Optional[Dict[str, Any]] = None,
) -> ChatOpenAI:
    """
    Build a ChatOpenAI instance honoring custom base URL / Azure / timeout / extra body.
    """
    params: Dict[str, Any] = {
        "temperature": temperature,
        "model": model,
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout or None,
    }

    if settings.use_azure:
        params.update(
            {
                "azure_endpoint": settings.azure_endpoint or None,
                "azure_deployment": model,
                "api_version": settings.azure_api_version or None,
                "api_key": settings.azure_api_key or settings.openai_api_key,
            }
        )
    elif settings.openai_base_url:
        params["base_url"] = settings.openai_base_url

    merged_extra: Dict[str, Any] = {}
    if settings.openai_extra_body:
        try:
            merged_extra.update(json.loads(settings.openai_extra_body))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in openai_extra_body; ignoring.")
    if extra_body:
        merged_extra.update(extra_body)
    if merged_extra:
        params["extra_body"] = merged_extra

    return ChatOpenAI(**params)


def _log_usage(response: Any, node: str) -> None:
    """Best-effort logging of token usage."""
    if not response:
        return
    usage = None
    if hasattr(response, "usage_metadata"):
        usage = getattr(response, "usage_metadata", None)
    if not usage and hasattr(response, "response_metadata"):
        usage = getattr(response, "response_metadata", None)
    if usage:
        logger.info(f"[usage] {node}: {usage}")


def initialize_enhanced_tools() -> None:
    """
    Initialize enhanced tool system (Phase 1-4).

    Auto-discovers and registers all WeaverTool instances from the tools directory.
    Should be called once at application startup.
    """
    if not ENHANCED_TOOLS_AVAILABLE:
        logger.info("Enhanced tools not available, skipping initialization")
        return

    try:
        if not bool(getattr(settings, "enhanced_tool_discovery_enabled", True)):
            logger.info("Enhanced tool discovery disabled, skipping initialization")
            return

        registry = get_global_registry()

        discovered = []

        logger.info("Discovering tools from module 'tools'...")
        try:
            discovered.extend(
                registry.discover_from_module(
                    module_name="tools",
                    tags=["weaver", "auto_discovered"],
                )
            )
        except Exception as e:
            logger.warning(f"Failed to discover tools from module 'tools': {e}")

        if bool(getattr(settings, "enhanced_tool_discovery_recursive", False)):
            exclude_dirs = set(getattr(settings, "enhanced_tool_discovery_exclude_list", []) or [])
            logger.info("Discovering tools from 'tools' directory (recursive)...")
            discovered.extend(
                registry.discover_from_directory(
                    directory="tools",
                    pattern="*.py",
                    recursive=True,
                    tags=["weaver", "auto_discovered"],
                    exclude_dirs=exclude_dirs,
                    exclude_globs=[
                        "tools/core/*",
                        "tools/examples/*",
                    ],
                )
            )

        logger.info(f"Discovered and registered {len(discovered)} tools")

        all_tools = registry.list_names()
        logger.info(f"Total tools in registry: {len(all_tools)}")
        if all_tools:
            logger.info(
                f"Available tools: {', '.join(all_tools[:10])}{'...' if len(all_tools) > 10 else ''}"
            )

    except Exception as e:
        logger.error(f"Failed to initialize enhanced tools: {e}", exc_info=True)


def _selected_model(config: RunnableConfig, fallback: str) -> str:
    cfg = _configurable(config)
    val = cfg.get("model")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return fallback


def _selected_reasoning_model(config: RunnableConfig, fallback: str) -> str:
    cfg = _configurable(config)
    val = cfg.get("reasoning_model")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return fallback


def _model_for_task(task_type: str, config: RunnableConfig) -> str:
    """
    Get model name for a specific task type using the ModelRouter.

    Respects runtime config overrides, per-task settings, and defaults.
    Falls back to _selected_model/_selected_reasoning_model for compatibility.
    """
    try:
        from agent.core.multi_model import TaskType, get_model_router

        tt = TaskType(task_type)
        router = get_model_router()
        return router.get_model_name(tt, config)
    except Exception:
        if task_type in ("planning", "evaluation", "critique", "routing", "reflection", "gap_analysis"):
            return _selected_reasoning_model(config, settings.reasoning_model)
        return _selected_model(config, settings.primary_model)


def _extract_tool_call_fields(
    tool_call: Any,
) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    """
    Normalize tool call objects across LangChain 0.x/1.x.
    Returns (name, args_dict, tool_call_id).
    """
    if isinstance(tool_call, dict):
        name = tool_call.get("name")
        raw_args = tool_call.get("args") or tool_call.get("arguments")
        tool_call_id = tool_call.get("id") or tool_call.get("tool_call_id")
    else:
        name = getattr(tool_call, "name", None)
        raw_args = getattr(tool_call, "args", None) or getattr(tool_call, "arguments", None)
        tool_call_id = getattr(tool_call, "id", None) or getattr(tool_call, "tool_call_id", None)

    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except json.JSONDecodeError:
            raw_args = {"code": raw_args}
    elif raw_args is None:
        raw_args = {}
    elif not isinstance(raw_args, dict):
        raw_args = {"code": raw_args}

    return name, raw_args, tool_call_id


def _get_writer_tools() -> List[Any]:
    tools: List[Any] = [execute_python_code]
    tools.extend(get_registered_tools())
    return tools


def _guess_mime(name: Optional[str]) -> str:
    mime, _ = mimetypes.guess_type(name or "")
    return mime or "image/png"


def _normalize_images(images: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    """
    Normalize image payloads to data URLs for OpenAI-compatible multimodal inputs.
    Accepts items with either `data` (base64 without prefix) or `url` (already data URL).
    """
    normalized: List[Dict[str, str]] = []
    if not images:
        return normalized

    for img in images:
        if not isinstance(img, dict):
            continue
        raw_data = (img.get("data") or img.get("url") or "").strip()
        if not raw_data:
            continue
        mime = img.get("mime") or _guess_mime(img.get("name"))

        if raw_data.startswith("data:"):
            data_url = raw_data
        else:
            data_url = f"data:{mime};base64,{raw_data}"

        normalized.append(
            {
                "url": data_url,
                "name": img.get("name", ""),
                "mime": mime,
            }
        )
    return normalized


def _build_user_content(
    text: str, images: Optional[List[Dict[str, Any]]]
) -> Union[str, List[Dict[str, Any]]]:
    """
    Build multimodal content for HumanMessage.
    Returns plain text if no images, otherwise a mixed list with text + image_url parts.
    """
    parts: List[Dict[str, Any]] = []
    text = text or ""
    normalized_images = _normalize_images(images)

    if text:
        parts.append({"type": "text", "text": text})
    elif normalized_images:
        parts.append({"type": "text", "text": "See attached images and respond accordingly."})

    for img in normalized_images:
        parts.append({"type": "image_url", "image_url": {"url": img["url"]}})

    if not parts:
        return ""
    if len(parts) == 1 and parts[0].get("type") == "text":
        return parts[0]["text"]
    return parts


__all__ = [
    "ENHANCED_TOOLS_AVAILABLE",
    "_answer_simple_agent_query",
    "_apply_output_contract",
    "_auto_mode_prefers_linear",
    "_build_compact_unique_source_preview",
    "_build_fast_agent_search_query",
    "_build_user_content",
    "_chat_model",
    "_configurable",
    "_event_results_limit",
    "_extract_exact_reply_target",
    "_extract_tool_call_fields",
    "_format_fast_search_results",
    "_get_writer_tools",
    "_guess_mime",
    "_is_narrow_comparison_prompt",
    "_is_tool_enabled",
    "_log_usage",
    "_model_for_task",
    "_normalize_images",
    "_run_fast_agent_search",
    "_selected_model",
    "_selected_reasoning_model",
    "_should_use_fast_agent_path",
    "check_cancellation",
    "handle_cancellation",
    "initialize_enhanced_tools",
    "logger",
    "settings",
]
