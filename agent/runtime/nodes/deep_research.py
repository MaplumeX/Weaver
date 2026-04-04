"""
Deep-research orchestration graph nodes.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphBubbleUp

import agent.contracts.events as _events
import agent.runtime.deep as _deep_runtime
import agent.runtime.nodes._shared as _shared
import agent.runtime.nodes.answer as _answer_nodes
from common.cancellation import check_cancellation as _check_cancellation

_auto_mode_prefers_linear = _shared._auto_mode_prefers_linear
_build_compact_unique_source_preview = _shared._build_compact_unique_source_preview
_configurable = _shared._configurable
_event_results_limit = _shared._event_results_limit
project_state_updates = _shared.project_state_updates
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings
ToolEventType = _events.ToolEventType
get_emitter_sync = _events.get_emitter_sync
run_deep_research = _deep_runtime.run_deep_research
agent_node = _answer_nodes.agent_node


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


def deep_research_node(
    state: dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> dict[str, Any]:
    """Deep Research node that runs the canonical runtime."""
    deps = _resolve_deps(_deps)
    logger.info("Executing deep research node")
    cfg = deps._configurable(config)
    thread_id = str(cfg.get("thread_id") or state.get("cancel_token_id") or "").strip()
    emitter = None

    if thread_id:
        try:
            emitter = deps.get_emitter_sync(thread_id)
            emitter.emit_sync(
                deps.ToolEventType.RESEARCH_NODE_START,
                {
                    "node_id": "deep_research",
                    "topic": state.get("input", "") or "Deep Research",
                    "depth": 0,
                    "parent_id": None,
                },
            )
        except Exception as e:
            logger.debug(f"[deep_research_node] failed to emit start event: {e}")

    try:
        input_text = str(state.get("input", "") or "").strip()
        if input_text and deps._auto_mode_prefers_linear(input_text):
            logger.info("[deep_research_node] Delegating simple factual deep query to agent node")
            delegated_state = dict(state)
            delegated_state["route"] = "agent"
            return deps.agent_node(delegated_state, config)

        token_id = state.get("cancel_token_id")
        if token_id:
            _check_cancellation(token_id)
        result = deps.run_deep_research(state, config)

        if emitter and isinstance(result, dict):
            try:
                runner_events_emitted = bool(result.get("_deep_research_events_emitted")) and not bool(
                    result.get("is_cancelled")
                )
                if not runner_events_emitted:
                    quality_summary = result.get("quality_summary", {})
                    if isinstance(quality_summary, dict) and quality_summary:
                        payload = {"stage": "final", **quality_summary}
                        emitter.emit_sync(deps.ToolEventType.QUALITY_UPDATE, payload)

                    artifacts = result.get("deep_research_artifacts", {})
                    research_topology = (
                        artifacts.get("research_topology")
                        if isinstance(artifacts, dict)
                        else None
                    )
                    if isinstance(research_topology, dict) and research_topology:
                        emitter.emit_sync(
                            deps.ToolEventType.DEEP_RESEARCH_TOPOLOGY_UPDATE,
                            {
                                "topology": research_topology,
                                "quality": quality_summary if isinstance(quality_summary, dict) else {},
                            },
                        )

                    report_text = (
                        result.get("final_report")
                        or result.get("draft_report")
                        or ""
                    )
                    report_preview = str(report_text).strip()
                    if len(report_preview) > 1200:
                        report_preview = report_preview[:1200] + "..."
                    source_preview = deps._build_compact_unique_source_preview(
                        result.get("scraped_content", []),
                        limit=deps._event_results_limit(),
                    )
                    if not source_preview:
                        source_preview = deps._build_compact_unique_source_preview(
                            result.get("sources", []),
                            limit=deps._event_results_limit(),
                        )

                    emitter.emit_sync(
                        deps.ToolEventType.RESEARCH_NODE_COMPLETE,
                        {
                            "node_id": "deep_research",
                            "summary": report_preview,
                            "sources": source_preview,
                            "quality": quality_summary if isinstance(quality_summary, dict) else {},
                        },
                    )
            except Exception as e:
                logger.debug(f"[deep_research_node] failed to emit completion events: {e}")

        return deps.project_state_updates(state, result)
    except asyncio.CancelledError as e:
        return deps.handle_cancellation(state, e)
    except GraphBubbleUp:
        raise
    except Exception as e:
        logger.error(f"Deep Research error: {e!s}", exc_info=settings.debug)
        err_text = str(e)
        if "Model Not Exist" in err_text or "model_not_found" in err_text:
            msg = (
                "Deep Research failed because the model is not available at your configured provider. "
                "Check OPENAI_BASE_URL/PRIMARY_MODEL and ensure OPENAI_API_KEY matches that provider "
                f"(current PRIMARY_MODEL={settings.primary_model}, BASE_URL={settings.openai_base_url or 'https://api.openai.com/v1'}). "
                "For DeepSeek, set PRIMARY_MODEL=deepseek-chat and use a valid DeepSeek API key."
            )
        else:
            msg = f"Deep Research failed: {err_text}"
        return deps.project_state_updates(
            state,
            {
                "errors": [msg],
                "final_report": msg,
                "draft_report": msg,
                "is_complete": False,
                "messages": [AIMessage(content=msg)],
            },
        )


__all__ = ["deep_research_node"]
