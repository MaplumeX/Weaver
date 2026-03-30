"""
Answer-generation and tool-agent graph nodes.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

import agent.runtime.nodes._shared as _shared
import agent.workflows.agent_factory as _agent_factory
import agent.workflows.agent_tools as _agent_tools
import agent.workflows.stuck_middleware as _stuck_middleware
from agent.workflows.browser_context_helper import build_browser_context_hint

ENHANCED_TOOLS_AVAILABLE = _shared.ENHANCED_TOOLS_AVAILABLE
_answer_simple_agent_query = _shared._answer_simple_agent_query
_build_user_content = _shared._build_user_content
_chat_model = _shared._chat_model
_configurable = _shared._configurable
_log_usage = _shared._log_usage
_model_for_task = _shared._model_for_task
_should_use_fast_agent_path = _shared._should_use_fast_agent_path
check_cancellation = _shared.check_cancellation
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings
build_tool_agent = _agent_factory.build_tool_agent
build_writer_agent = _agent_factory.build_writer_agent
build_agent_tools = _agent_tools.build_agent_tools
detect_stuck = _stuck_middleware.detect_stuck
inject_stuck_hint = _stuck_middleware.inject_stuck_hint


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.workflows.nodes")
    if compat is not None:
        return compat
    return sys.modules[__name__]


def direct_answer_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """Direct answer without research."""
    deps = _resolve_deps(_deps)
    logger.info("Executing direct answer node")
    t0 = time.time()
    llm = deps._chat_model(deps._model_for_task("writing", config), temperature=0.7)
    messages = [
        SystemMessage(content="You are a helpful assistant. Answer succinctly and accurately."),
        HumanMessage(content=deps._build_user_content(state["input"], state.get("images"))),
    ]
    response = llm.invoke(messages, config=config)
    deps._log_usage(response, "direct_answer")
    logger.info(f"[timing] direct_answer {(time.time() - t0):.3f}s")
    content = response.content if hasattr(response, "content") else str(response)
    return {
        "draft_report": content,
        "final_report": content,
        "messages": [AIMessage(content=content)],
        "is_complete": False,
    }


def agent_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Agent node: Tool-calling loop (GPTs/Manus-like) with enhanced features.
    """
    deps = _resolve_deps(_deps)
    logger.info("Executing agent node (tool-calling)")
    try:
        deps.check_cancellation(state)

        if deps._should_use_fast_agent_path(state, config):
            fast_result = deps._answer_simple_agent_query(state, config)
            if fast_result is not None:
                logger.info("[agent_node] Served simple verification query via fast search path")
                return fast_result

        cfg = deps._configurable(config)
        profile = cfg.get("agent_profile") or {}
        thread_id = str(cfg.get("thread_id") or "default")

        model = deps._model_for_task("research", config)
        tools = deps.build_agent_tools(config)

        tool_names = [getattr(t, "name", t.__class__.__name__) for t in tools]
        logger.info(f"Agent loaded {len(tools)} tools: {tool_names}")

        if ENHANCED_TOOLS_AVAILABLE and hasattr(settings, "agent_use_enhanced_registry"):
            try:
                from tools.core.registry import get_global_registry

                registry = get_global_registry()
                if registry.list_names():
                    logger.info(
                        f"Using enhanced tool registry with {len(registry.list_names())} tools"
                    )
            except Exception as e:
                logger.warning(f"Failed to use enhanced registry: {e}")

        agent = deps.build_tool_agent(model=model, tools=tools, temperature=0.7)
        t0 = time.time()

        from agent.prompts.system_prompts import get_agent_prompt

        profile_prompt_pack = profile.get("prompt_pack")
        profile_prompt_variant = profile.get("prompt_variant", "full")

        enhanced_system_prompt = get_agent_prompt(
            mode="agent",
            context={
                "current_time": datetime.now(),
                "enabled_tools": [tool.__class__.__name__ for tool in tools] if tools else [],
                "prompt_pack": profile_prompt_pack,
                "prompt_variant": profile_prompt_variant,
            },
        )
        browser_hint = None
        if profile.get("browser_context_helper", settings.enable_browser_context_helper):
            browser_hint = build_browser_context_hint(thread_id)

        if ENHANCED_TOOLS_AVAILABLE and getattr(settings, "agent_xml_tool_calling", False):
            xml_instruction = """\n\nXML Tool Calling Format (optional):
You can also use XML format for tool calls:
<function_calls>
<invoke name="tool_name">
<parameter name="param1">value1</parameter>
<parameter name="param2">value2</parameter>
</invoke>
</function_calls>"""
            enhanced_system_prompt += xml_instruction

        messages: List[Any] = []
        seeded = state.get("messages") or []
        has_system_msg = False
        if isinstance(seeded, list):
            for msg in seeded:
                if isinstance(msg, SystemMessage):
                    has_system_msg = True
                    break
            messages.extend(seeded)

        if not has_system_msg:
            messages.insert(0, SystemMessage(content=enhanced_system_prompt))

        if browser_hint:
            messages.append(SystemMessage(content=browser_hint))

        messages.append(
            HumanMessage(content=deps._build_user_content(state.get("input", ""), state.get("images")))
        )

        response = agent.invoke({"messages": messages}, config=config)
        logger.info(f"[timing] agent {(time.time() - t0):.3f}s")

        text = ""
        if isinstance(response, dict) and response.get("messages"):
            last = response["messages"][-1]
            text = getattr(last, "content", "") if hasattr(last, "content") else str(last)
        else:
            text = getattr(response, "content", None) or str(response)

        if deps.detect_stuck(
            response.get("messages", []) if isinstance(response, dict) else [], threshold=1
        ):
            result_messages = response.get("messages", []) if isinstance(response, dict) else []
            result_messages = deps.inject_stuck_hint(result_messages)
            response = {"messages": result_messages}
            text = getattr(result_messages[-1], "content", text)

        continuation_needed = False
        if ENHANCED_TOOLS_AVAILABLE and getattr(settings, "agent_xml_tool_calling", False):
            try:
                from agent.parsers.xml_parser import XMLToolParser

                parser = XMLToolParser()
                xml_calls = parser.parse_content(text)
                if xml_calls:
                    logger.info(f"Detected {len(xml_calls)} XML tool calls in response")
                    continuation_needed = True
            except Exception as e:
                logger.debug(f"XML parsing skipped: {e}")

        result = {
            "draft_report": text,
            "final_report": text,
            "is_complete": False,
            "messages": [AIMessage(content=text)],
        }

        if continuation_needed:
            result["continuation_needed"] = True
            result["xml_tool_calls_detected"] = True

        return result

    except asyncio.CancelledError as e:
        return deps.handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Agent node error: {e}", exc_info=settings.debug)
        msg = f"Agent mode failed: {e}"
        return {
            "errors": [msg],
            "final_report": msg,
            "draft_report": msg,
            "is_complete": False,
            "messages": [AIMessage(content=msg)],
        }


def writer_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Writer node: Synthesizes research into a comprehensive report.
    """
    from agent.workflows.result_aggregator import ResultAggregator

    deps = _resolve_deps(_deps)
    logger.info("Executing writer node (with ResultAggregator)")

    try:
        deps.check_cancellation(state)

        route = str(state.get("route") or "").strip().lower()
        model = deps._model_for_task("writing", config)
        use_tools = route != "web"
        agent, writer_tools = deps.build_writer_agent(model) if use_tools else (None, [])
        t0 = time.time()
        code_results: List[Dict[str, Any]] = []

        scraped_content = state.get("scraped_content", [])
        original_query = state.get("input", "")

        aggregator = ResultAggregator(
            similarity_threshold=0.7,
            max_results_per_query=3,
            tier_1_threshold=0.6,
            tier_2_threshold=0.3,
        )
        aggregated = aggregator.aggregate(scraped_content, original_query)

        research_context, sources_table = aggregated.to_context(
            max_tier_1=5,
            max_tier_2=3,
            max_tier_3=2,
            max_content_length=500,
        )

        logger.info(
            f"[writer] Aggregated {aggregated.total_before} -> {aggregated.total_after} results, "
            f"tiers: {len(aggregated.tier_1)}/{len(aggregated.tier_2)}/{len(aggregated.tier_3)}"
        )

        from agent.prompts.system_prompts import get_writer_prompt

        writer_system_prompt = get_writer_prompt()

        messages: List[Any] = [
            SystemMessage(content=writer_system_prompt),
            HumanMessage(content=deps._build_user_content(state["input"], state.get("images"))),
        ]

        human_guidance = state.get("human_guidance")
        if isinstance(human_guidance, str) and human_guidance.strip():
            messages.append(
                HumanMessage(content=f"User guidance (HITL):\n{human_guidance.strip()}")
            )
        if research_context:
            messages.append(
                HumanMessage(
                    content=f"Research context:\n{research_context}\n\nSources:\n{sources_table}"
                )
            )

        if use_tools and agent is not None:
            response = agent.invoke({"messages": messages}, config=config)
        else:
            llm = deps._chat_model(model, temperature=0.7)
            response = llm.invoke(messages)
        logger.info(f"[timing] writer {(time.time() - t0):.3f}s")

        report = ""
        if isinstance(response, dict) and response.get("messages"):
            last = response["messages"][-1]
            report = getattr(last, "content", "") if hasattr(last, "content") else str(last)
        else:
            report = getattr(response, "content", None) or str(response)

        compressed_knowledge = state.get("compressed_knowledge", {})
        if compressed_knowledge and getattr(settings, "enable_report_charts", True):
            try:
                from agent.workflows.viz_planner import VizPlanner, embed_charts_in_report

                viz_llm = deps._chat_model(deps._model_for_task("writing", config), temperature=0.3)
                viz_planner = VizPlanner(viz_llm, config)

                charts = viz_planner.generate_all_charts(
                    compressed_knowledge,
                    report_text=report,
                    max_charts=3,
                )

                if charts:
                    report = embed_charts_in_report(report, charts, format="markdown")
                    logger.info(f"[writer] Embedded {len(charts)} charts in report")

            except Exception as e:
                logger.warning(f"[writer] Chart generation skipped: {e}")

        return {
            "draft_report": report,
            "final_report": report,
            "is_complete": False,
            "messages": [AIMessage(content=report)],
            "code_results": code_results,
        }

    except asyncio.CancelledError as e:
        return deps.handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Writer error: {str(e)}", exc_info=True)
        return {
            "final_report": "Error generating report",
            "is_complete": True,
            "errors": [f"Writing error: {str(e)}"],
            "messages": [AIMessage(content=f"Failed to generate report: {str(e)}")],
        }


__all__ = ["agent_node", "direct_answer_node", "writer_node"]
