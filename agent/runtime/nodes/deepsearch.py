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
_chat_model = _shared._chat_model
_model_for_task = _shared._model_for_task
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings
ToolEventType = _events.ToolEventType
get_emitter_sync = _events.get_emitter_sync
run_deepsearch_auto = _deep_runtime.run_deepsearch_auto
direct_answer_node = _answer_nodes.direct_answer_node


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.compat.nodes")
    if compat is not None:
        return compat
    return sys.modules[__name__]


def coordinator_node(
    state: dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> dict[str, Any]:
    """
    Coordinator node that decides the next research action.
    """
    from agent.runtime.deep.roles import ResearchCoordinator

    deps = _resolve_deps(_deps)
    logger.info("Executing coordinator node")

    try:
        topic = state.get("input", "")
        research_plan = state.get("research_plan", [])
        scraped_content = state.get("scraped_content", [])
        summary_notes = state.get("summary_notes", [])
        revision_count = state.get("revision_count", 0)
        max_revisions = state.get("max_revisions", 2)
        eval_dimensions = state.get("eval_dimensions", {}) or {}
        quality_overall_score = state.get("quality_overall_score")
        if quality_overall_score is None and isinstance(eval_dimensions, dict) and eval_dimensions:
            numeric_values = [
                float(v)
                for v in eval_dimensions.values()
                if isinstance(v, (int, float))
            ]
            if numeric_values:
                quality_overall_score = sum(numeric_values) / len(numeric_values)

        quality_gap_count = state.get("quality_gap_count")
        if quality_gap_count is None:
            quality_gap_count = len(state.get("missing_topics", []) or [])

        citation_accuracy = None
        if isinstance(eval_dimensions, dict):
            if isinstance(eval_dimensions.get("citation_coverage"), (int, float)):
                citation_accuracy = float(eval_dimensions["citation_coverage"])
            elif isinstance(eval_dimensions.get("accuracy"), (int, float)):
                citation_accuracy = float(eval_dimensions["accuracy"])

        model = deps._model_for_task("routing", config)
        llm = deps._chat_model(model, temperature=0.3)

        coordinator = ResearchCoordinator(llm, config)
        knowledge_summary = "\n".join(summary_notes[:5]) if summary_notes else ""

        decision = coordinator.decide_next_action(
            topic=topic,
            num_queries=len(research_plan),
            num_sources=len(scraped_content),
            num_summaries=len(summary_notes),
            current_epoch=revision_count,
            max_epochs=max_revisions + 1,
            knowledge_summary=knowledge_summary,
            quality_score=quality_overall_score,
            quality_gap_count=int(quality_gap_count or 0),
            citation_accuracy=citation_accuracy,
        )

        logger.info(
            f"[coordinator] Decision: {decision.action.value} | "
            f"Reasoning: {decision.reasoning[:100]}"
        )

        return {
            "coordinator_action": decision.action.value,
            "coordinator_reasoning": decision.reasoning,
            "missing_topics": decision.priority_topics if decision.priority_topics else state.get("missing_topics", []),
            "coordinator_quality_snapshot": {
                "overall": quality_overall_score,
                "gap_count": int(quality_gap_count or 0),
                "citation_accuracy": citation_accuracy,
            },
        }
    except Exception as e:
        logger.error(f"Coordinator error: {e}", exc_info=True)
        return {
            "coordinator_action": "plan",
            "coordinator_reasoning": f"Coordinator error, defaulting to plan: {e!s}",
            "missing_topics": state.get("missing_topics", []),
        }


def deepsearch_node(
    state: dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> dict[str, Any]:
    """Deep search pipeline that iterates query → search → summarize."""
    deps = _resolve_deps(_deps)
    logger.info("Executing deepsearch node")
    cfg = deps._configurable(config)
    thread_id = str(
        cfg.get("thread_id")
        or state.get("cancel_token_id")
        or ""
    ).strip()
    emitter = None

    if thread_id:
        try:
            emitter = deps.get_emitter_sync(thread_id)
            emitter.emit_sync(
                deps.ToolEventType.RESEARCH_NODE_START,
                {
                    "node_id": "deepsearch",
                    "topic": state.get("input", "") or "DeepSearch",
                    "depth": 0,
                    "parent_id": None,
                },
            )
        except Exception as e:
            logger.debug(f"[deepsearch_node] failed to emit start event: {e}")

    try:
        input_text = str(state.get("input", "") or "").strip()
        if input_text and deps._auto_mode_prefers_linear(input_text):
            logger.info("[deepsearch_node] Delegating simple factual deep query to direct answer node")
            return deps.direct_answer_node(state, config)

        token_id = state.get("cancel_token_id")
        if token_id:
            _check_cancellation(token_id)
        result = deps.run_deepsearch_auto(state, config)

        if emitter and isinstance(result, dict):
            try:
                runner_events_emitted = bool(result.get("_deepsearch_events_emitted")) and not bool(
                    result.get("is_cancelled")
                )
                if not runner_events_emitted:
                    quality_summary = result.get("quality_summary", {})
                    if isinstance(quality_summary, dict) and quality_summary:
                        payload = {"stage": "final", **quality_summary}
                        emitter.emit_sync(deps.ToolEventType.QUALITY_UPDATE, payload)

                    artifacts = result.get("deepsearch_artifacts", {})
                    research_tree = (
                        artifacts.get("research_tree")
                        if isinstance(artifacts, dict)
                        else None
                    )
                    if isinstance(research_tree, dict) and research_tree:
                        emitter.emit_sync(
                            deps.ToolEventType.RESEARCH_TREE_UPDATE,
                            {
                                "tree": research_tree,
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
                            "node_id": "deepsearch",
                            "summary": report_preview,
                            "sources": source_preview,
                            "quality": quality_summary if isinstance(quality_summary, dict) else {},
                        },
                    )
            except Exception as e:
                logger.debug(f"[deepsearch_node] failed to emit completion events: {e}")

        return result
    except asyncio.CancelledError as e:
        return deps.handle_cancellation(state, e)
    except GraphBubbleUp:
        raise
    except Exception as e:
        logger.error(f"Deepsearch error: {e!s}", exc_info=settings.debug)
        err_text = str(e)
        if "Model Not Exist" in err_text or "model_not_found" in err_text:
            msg = (
                "Deep search failed because the model is not available at your configured provider. "
                "Check OPENAI_BASE_URL/PRIMARY_MODEL and ensure OPENAI_API_KEY matches that provider "
                f"(current PRIMARY_MODEL={settings.primary_model}, BASE_URL={settings.openai_base_url or 'https://api.openai.com/v1'}). "
                "For DeepSeek, set PRIMARY_MODEL=deepseek-chat and use a valid DeepSeek API key."
            )
        else:
            msg = f"Deep search failed: {err_text}"
        return {
            "errors": [msg],
            "final_report": msg,
            "draft_report": msg,
            "is_complete": False,
            "messages": [AIMessage(content=msg)],
        }


__all__ = ["coordinator_node", "deepsearch_node"]
