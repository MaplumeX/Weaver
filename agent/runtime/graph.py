import logging

import psycopg
from langgraph.graph import END, StateGraph
from psycopg.rows import dict_row

from agent.core.state import AgentState
from agent.runtime.nodes import (
    chat_respond_node,
    deep_research_node,
    finalize_answer_node,
    human_review_node,
    route_node,
    tool_agent_node,
)
from common.weaver_checkpointer import WeaverPostgresCheckpointer

logger = logging.getLogger(__name__)


def create_research_graph(checkpointer=None, interrupt_before=None, store=None):
    """
    Create the root research graph.

    The root graph only orchestrates top-level routing:
    router -> chat_respond|deep_research -> tool_agent?|finalize -> human_review -> END
    """
    from common.config import settings

    workflow = StateGraph(AgentState)

    workflow.add_node("router", route_node)
    workflow.add_node("chat_respond", chat_respond_node)
    workflow.add_node("tool_agent", tool_agent_node)
    workflow.add_node("finalize", finalize_answer_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("deep_research", deep_research_node)

    workflow.set_entry_point("router")

    def route_decision(state: AgentState) -> str:
        route = state.get("route", "agent")
        logger.info(f"[route_decision] state['route'] = '{route}'")

        if route == "deep":
            logger.info("[route_decision] → Routing to 'deep_research' node")
            return "deep_research"
        if route == "agent":
            logger.info("[route_decision] → Routing to 'chat_respond' node")
            return "chat_respond"

        logger.info("[route_decision] → Routing to 'chat_respond' node (default)")
        return "chat_respond"

    workflow.add_conditional_edges("router", route_decision, ["chat_respond", "deep_research"])

    def after_chat(state: AgentState) -> str:
        return "tool_agent" if state.get("needs_tools") else "finalize"

    workflow.add_conditional_edges("chat_respond", after_chat, ["tool_agent", "finalize"])
    workflow.add_edge("tool_agent", "finalize")
    workflow.add_edge("finalize", "human_review")
    workflow.add_edge("deep_research", "human_review")
    workflow.add_edge("human_review", END)

    # HITL checkpoints are implemented via explicit review nodes that use
    # `langgraph.types.interrupt()` (see agent/workflows/nodes.py).
    hitl_checkpoints = getattr(settings, "hitl_checkpoints", "") or ""
    if hitl_checkpoints.strip():
        logger.info(f"HITL checkpoints enabled: {hitl_checkpoints}")

    # Compile the graph
    graph = workflow.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
    )

    logger.info("Research graph compiled successfully")

    return graph

async def create_checkpointer(database_url: str):
    """
    Create a PostgreSQL checkpointer for state persistence.

    This allows long-running agents to pause/resume and handle failures.
    """
    if not database_url:
        raise ValueError("database_url is required to initialize the Postgres checkpointer.")

    # Match LangGraph's documented Postgres connection requirements.
    try:
        conn = await psycopg.AsyncConnection.connect(
            database_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
        sync_conn = psycopg.connect(
            database_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Postgres for checkpointer: {e}") from e

    checkpointer = WeaverPostgresCheckpointer(conn, sync_conn=sync_conn)

    # Setup tables
    await checkpointer.setup()

    logger.info("PostgreSQL checkpointer initialized")
    return checkpointer
