"""
Planning and search-dispatch graph nodes.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send
from pydantic import BaseModel, Field

import agent.contracts.search_cache as _search_cache_contracts
import agent.runtime.nodes._shared as _shared
from agent.core.middleware import enforce_tool_call_limit, retry_call
from tools import tavily_search

QueryDeduplicator = _search_cache_contracts.QueryDeduplicator
_build_user_content = _shared._build_user_content
_chat_model = _shared._chat_model
_log_usage = _shared._log_usage
_model_for_task = _shared._model_for_task
check_cancellation = _shared.check_cancellation
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.workflows.nodes")
    if compat is not None:
        return compat
    return sys.modules[__name__]


def perform_parallel_search(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Executes a single search query in parallel.
    """
    from agent.contracts.search_cache import get_search_cache

    deps = _resolve_deps(_deps)
    query = state["query"]
    logger.info(f"Executing parallel search for: {query}")

    try:
        deps.check_cancellation(state)

        try:
            import threading

            from agent.workflows.browser_visualizer import show_browser_status_page

            threading.Thread(
                target=lambda: show_browser_status_page(
                    state=state,
                    config=config,
                    title="Searching the web…",
                    detail=query,
                ),
                daemon=True,
            ).start()
        except Exception:
            pass

        cache = get_search_cache()
        cached_results = cache.get(query)
        if cached_results is not None:
            logger.info(f"[search] Cache hit for: {query[:50]}")
            try:
                import threading

                from agent.workflows.browser_visualizer import visualize_urls_from_results

                threading.Thread(
                    target=lambda rs=cached_results: visualize_urls_from_results(
                        state=state,
                        config=config,
                        results=rs if isinstance(rs, list) else [],
                        max_urls=1,
                        reason="web_plan:search:cached",
                    ),
                    daemon=True,
                ).start()
            except Exception:
                pass
            return {
                "scraped_content": [
                    {
                        "query": query,
                        "results": cached_results,
                        "timestamp": datetime.now().isoformat(),
                        "cached": True,
                    }
                ]
            }

        enforce_tool_call_limit(state, settings.tool_call_limit)

        call_kwargs = {"query": query, "max_results": 5}
        if settings.tool_retry:
            results = retry_call(
                tavily_search.invoke,
                attempts=settings.tool_retry_max_attempts,
                backoff=settings.tool_retry_backoff,
                **{"input": call_kwargs, "config": config},
            )
        else:
            results = tavily_search.invoke(call_kwargs, config=config)

        deps.check_cancellation(state)

        if results:
            cache.set(query, results)
            try:
                import threading

                from agent.workflows.browser_visualizer import visualize_urls_from_results

                threading.Thread(
                    target=lambda rs=results: visualize_urls_from_results(
                        state=state,
                        config=config,
                        results=rs if isinstance(rs, list) else [],
                        max_urls=1,
                        reason="web_plan:search",
                    ),
                    daemon=True,
                ).start()
            except Exception:
                pass

        search_data = {
            "query": query,
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }

        return {"scraped_content": [search_data]}

    except asyncio.CancelledError as e:
        logger.info(f"Search cancelled for {query}: {e}")
        return {"scraped_content": [], "is_cancelled": True}
    except Exception as e:
        logger.error(f"Parallel search error for {query}: {str(e)}")
        return {"scraped_content": []}


def initiate_research(state: Dict[str, Any], *, _deps: Any = None) -> List[Send]:
    """
    Map step: Generates search tasks for each query in the plan.
    """
    deps = _resolve_deps(_deps)
    plan = state.get("research_plan", [])

    deduplicator = deps.QueryDeduplicator(similarity_threshold=0.85)
    unique_queries, duplicates = deduplicator.deduplicate(plan)

    if duplicates:
        logger.info(f"Removed {len(duplicates)} duplicate queries from plan")

    logger.info(
        f"Initiating parallel research for {len(unique_queries)} queries (original: {len(plan)})"
    )

    return [Send("perform_parallel_search", {"query": q}) for q in unique_queries]


def planner_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Planning node: Creates a structured research plan.
    """
    deps = _resolve_deps(_deps)
    logger.info("Executing planner node")

    try:
        deps.check_cancellation(state)

        llm = deps._chat_model(
            deps._model_for_task("planning", config), temperature=1
        )
        t0 = time.time()

        class PlanResponse(BaseModel):
            queries: List[str] = Field(description="3-7 targeted search queries")
            reasoning: str = Field(description="Brief explanation of the research strategy")

        system_msg = SystemMessage(
            content="You are an expert research planner. Return JSON with 3-7 targeted search queries and a brief reasoning."
        )
        human_msg = HumanMessage(content=deps._build_user_content(state["input"], state.get("images")))

        response = (
            llm.with_structured_output(PlanResponse)
            .with_retry(stop_after_attempt=2)
            .invoke([system_msg, human_msg], config=config)
        )

        deps.check_cancellation(state)

        deps._log_usage(response, "planner")
        logger.info(f"[timing] planner {(time.time() - t0):.3f}s")
        plan_data = response.dict()

        raw_queries = plan_data.get("queries", [state["input"]])
        seen = set()
        queries: List[str] = []
        for q in raw_queries:
            if not isinstance(q, str):
                continue
            q = q.strip()
            if not q or q.lower() in seen:
                continue
            seen.add(q.lower())
            queries.append(q)
            if len(queries) >= 6:
                break
        if not queries:
            queries = [state["input"]]

        reasoning = plan_data.get("reasoning", "")

        logger.info(f"Generated {len(queries)} research queries")

        return {
            "research_plan": queries,
            "current_step": 0,
            "messages": [
                AIMessage(
                    content=f"Research Plan:\n{reasoning}\n\nQueries:\n"
                    + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(queries))
                )
            ],
        }

    except asyncio.CancelledError as e:
        return deps.handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Planner error: {str(e)}")
        return {
            "research_plan": [state["input"]],
            "current_step": 0,
            "errors": [f"Planning error: {str(e)}"],
            "messages": [
                AIMessage(content=f"Using fallback plan: direct search for '{state['input']}'")
            ],
        }


def refine_plan_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Refinement node: creates follow-up queries based on evaluator feedback.
    """
    deps = _resolve_deps(_deps)
    logger.info("Executing refine plan node (feedback-driven queries)")

    feedback = state.get("evaluation", "") or state.get("verdict", "")
    original_question = state.get("input", "")
    existing_plan = state.get("research_plan", []) or []
    seen = {q.lower().strip() for q in existing_plan if isinstance(q, str)}

    suggested_queries = state.get("suggested_queries", []) or []
    missing_topics = state.get("missing_topics", []) or []

    new_queries: List[str] = []

    for q in suggested_queries:
        if not isinstance(q, str):
            continue
        q_norm = q.strip()
        if q_norm and q_norm.lower() not in seen:
            seen.add(q_norm.lower())
            new_queries.append(q_norm)

    if len(new_queries) < 3 and missing_topics:
        for topic in missing_topics:
            if len(new_queries) >= 3:
                break
            topic_query = f"{original_question} {topic}".strip()
            if topic_query.lower() not in seen:
                seen.add(topic_query.lower())
                new_queries.append(topic_query)

    if not new_queries:
        logger.info("No evaluator suggestions, generating via LLM")
        llm = deps._chat_model(
            deps._model_for_task("planning", config), temperature=0.8
        )
        t0 = time.time()

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a research strategist. Generate up to 3 follow-up search queries to close the gaps called out in feedback.

Rules:
- Target missing evidence, data, or counterpoints.
- Avoid repeating prior queries unless wording needs to be more specific.
- Keep queries concise and specific.

Return ONLY a JSON object:
{"queries": ["q1", "q2", ...]}""",
                ),
                (
                    "human",
                    "Question: {question}\nFeedback: {feedback}\nExisting queries: {existing}",
                ),
            ]
        )

        try:
            response = llm.invoke(
                prompt.format_messages(
                    question=original_question,
                    feedback=feedback,
                    existing="\n".join(existing_plan),
                ),
                config=config,
            )
            deps._log_usage(response, "refine_plan")
            logger.info(f"[timing] refine_plan LLM {(time.time() - t0):.3f}s")
            content = response.content if hasattr(response, "content") else str(response)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(content[start:end])
                    raw_queries = data.get("queries", [])
                    for q in raw_queries:
                        if not isinstance(q, str):
                            continue
                        q_norm = q.strip()
                        if not q_norm or q_norm.lower() in seen:
                            continue
                        seen.add(q_norm.lower())
                        new_queries.append(q_norm)
                        if len(new_queries) >= 3:
                            break
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.error(f"Refine plan LLM error: {str(e)}")

    if not new_queries:
        new_queries = [f"{original_question} {feedback[:50]}".strip()]

    merged_plan = existing_plan + new_queries
    revision_count = int(state.get("revision_count", 0)) + 1

    logger.info(f"Refine plan added {len(new_queries)} queries; total plan size {len(merged_plan)}")
    return {
        "research_plan": merged_plan,
        "revision_count": revision_count,
        "messages": [
            AIMessage(
                content="Added follow-up queries:\n" + "\n".join(f"- {q}" for q in new_queries)
            )
        ],
    }


def web_search_plan_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """Simple plan for web search only mode."""
    logger.info("Executing web search plan node")
    return {
        "research_plan": [state["input"]],
        "current_step": 0,
        "messages": [AIMessage(content=f"Web search plan: direct search for '{state['input']}'")],
    }


def compressor_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Compressor node: Extracts and structures key facts from research.
    """
    from agent.workflows.compressor import ResearchCompressor

    deps = _resolve_deps(_deps)
    logger.info("Executing compressor node")

    topic = state.get("input", "")
    scraped_content = state.get("scraped_content", [])
    summary_notes = state.get("summary_notes", [])

    if not scraped_content:
        logger.info("[compressor] No content to compress")
        return {"compressed_knowledge": {}}

    try:
        model = deps._model_for_task("research", config)
        llm = deps._chat_model(model, temperature=0.3)

        compressor = ResearchCompressor(llm, config)
        existing_knowledge = state.get("compressed_knowledge", {})

        knowledge = compressor.compress(
            topic=topic,
            scraped_content=scraped_content,
            summary_notes=summary_notes,
        )

        if existing_knowledge and existing_knowledge.get("facts"):
            from agent.workflows.compressor import CompressedKnowledge, ExtractedFact

            existing = CompressedKnowledge(
                topic=existing_knowledge.get("topic", topic),
                facts=[
                    ExtractedFact(**f) for f in existing_knowledge.get("facts", [])
                ],
                statistics=existing_knowledge.get("statistics", []),
                key_entities=existing_knowledge.get("key_entities", []),
                summary=existing_knowledge.get("summary", ""),
            )
            knowledge = compressor.merge_knowledge(existing, knowledge)

        compressed_dict = knowledge.to_dict()

        logger.info(
            f"[compressor] Compressed: {len(knowledge.facts)} facts, "
            f"{len(knowledge.statistics)} stats"
        )

        return {"compressed_knowledge": compressed_dict}

    except Exception as e:
        logger.error(f"Compressor error: {e}", exc_info=True)
        return {"compressed_knowledge": {}}


__all__ = [
    "QueryDeduplicator",
    "compressor_node",
    "initiate_research",
    "perform_parallel_search",
    "planner_node",
    "refine_plan_node",
    "web_search_plan_node",
]
