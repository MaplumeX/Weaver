"""
Customer Support Agent with runtime memory context.

Provides a simple LangGraph that:
- Receives structured memory context from the caller
- Adds a system prompt with context
- Returns the assistant response
"""

import json
from contextlib import suppress
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from common.config import settings


class SupportState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    memory_context: dict[str, list[str]]


def _support_model() -> ChatOpenAI:
    params = {
        "temperature": 0.3,
        "model": settings.primary_model,
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout or None,
    }
    if settings.use_azure:
        params.update(
            {
                "azure_endpoint": settings.azure_endpoint or None,
                "azure_deployment": settings.primary_model,
                "api_version": settings.azure_api_version or None,
                "api_key": settings.azure_api_key or settings.openai_api_key,
            }
        )
    elif settings.openai_base_url:
        params["base_url"] = settings.openai_base_url

    extra = {}
    if settings.openai_extra_body:
        with suppress(Exception):
            extra.update(json.loads(settings.openai_extra_body))
    if extra:
        params["extra_body"] = extra
    return ChatOpenAI(**params)


def support_node(state: SupportState):
    messages = state["messages"]
    memory_context = state.get("memory_context") or {}
    stored = [str(item).strip() for item in (memory_context.get("stored") or []) if str(item).strip()]
    relevant = [str(item).strip() for item in (memory_context.get("relevant") or []) if str(item).strip()]
    context_parts: list[str] = []
    if stored:
        context_parts.append("Stored user memory:\n" + "\n".join(f"- {item}" for item in stored))
    if relevant:
        context_parts.append("Relevant user memory:\n" + "\n".join(f"- {item}" for item in relevant))

    system_prompt = "You are a helpful customer support assistant. Use provided context to personalize and remember user preferences."
    if context_parts:
        system_prompt += "\n" + "\n\n".join(context_parts)

    llm = _support_model()
    response = llm.invoke([SystemMessage(content=system_prompt), *messages])
    reply_text = response.content if hasattr(response, "content") else str(response)

    return {"messages": [AIMessage(content=reply_text)]}


def create_support_graph(checkpointer=None, store=None):
    graph = StateGraph(SupportState)
    graph.add_node("support", support_node)
    graph.add_edge(START, "support")
    graph.add_edge("support", END)
    return graph.compile(checkpointer=checkpointer, store=store)
