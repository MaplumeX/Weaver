"""
Answer-generation graph nodes.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

import agent.infrastructure.agents.factory as _agent_factory
import agent.runtime.nodes._shared as _shared
from agent.infrastructure.agents.stuck_middleware import detect_stuck, inject_stuck_hint
from agent.infrastructure.browser_context import build_browser_context_hint
from agent.infrastructure.tools import build_agent_toolset
from agent.prompts import get_prompt_manager

ENHANCED_TOOLS_AVAILABLE = _shared.ENHANCED_TOOLS_AVAILABLE
_answer_simple_agent_query = _shared._answer_simple_agent_query
_build_user_content = _shared._build_user_content
_configurable = _shared._configurable
_model_for_task = _shared._model_for_task
_should_use_fast_agent_path = _shared._should_use_fast_agent_path
project_state_updates = _shared.project_state_updates
check_cancellation = _shared.check_cancellation
handle_cancellation = _shared.handle_cancellation
logger = _shared.logger
settings = _shared.settings
build_tool_agent = _agent_factory.build_tool_agent


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


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
        tools = deps.build_agent_toolset(config)

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

        profile_prompt_pack = profile.get("prompt_pack")
        profile_prompt_variant = profile.get("prompt_variant", "full")

        enhanced_system_prompt = get_prompt_manager().get_agent_prompt(
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

        return deps.project_state_updates(state, result)

    except asyncio.CancelledError as e:
        return deps.handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Agent node error: {e}", exc_info=settings.debug)
        msg = f"Agent mode failed: {e}"
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


__all__ = ["agent_node"]
