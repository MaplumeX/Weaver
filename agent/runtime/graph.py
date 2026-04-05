import logging

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from psycopg.rows import dict_row

from agent.core.state import AgentState
from agent.runtime.nodes import (
    agent_node,
    clarify_node,
    compressor_node,
    deep_research_node,
    evaluator_node,
    human_review_node,
    initiate_research,
    hitl_draft_review_node,
    hitl_plan_review_node,
    hitl_sources_review_node,
    perform_parallel_search,
    planner_node,
    refine_plan_node,
    revise_report_node,
    route_node,
    writer_node,
)

logger = logging.getLogger(__name__)


def create_research_graph(checkpointer=None, interrupt_before=None, store=None):
    """
    Create the research agent graph.

    The graph flow:
    1. START -> planner (creates research plan)
    2. planner -> [parallel] perform_parallel_search (executes searches)
    3. perform_parallel_search -> writer (aggregates results)
    4. writer -> END

    Deep Research requests are routed to the canonical `deep_research` node.
    """
    from common.config import settings

    # Initialize the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("router", route_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("clarify", clarify_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("refine_plan", refine_plan_node)
    workflow.add_node("hitl_plan_review", hitl_plan_review_node)
    workflow.add_node("perform_parallel_search", perform_parallel_search)
    workflow.add_node("writer", writer_node)
    workflow.add_node("hitl_draft_review", hitl_draft_review_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("reviser", revise_report_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("deep_research", deep_research_node)
    workflow.add_node("compressor", compressor_node)
    workflow.add_node("hitl_sources_review", hitl_sources_review_node)

    # Set entry point
    workflow.set_entry_point("router")

    def route_decision(state: AgentState) -> str:
        route = state.get("route", "agent")
        logger.info(f"[route_decision] state['route'] = '{route}'")

        if route == "deep":
            logger.info("[route_decision] → Routing to 'deep_research' node")
            return "deep_research"
        if route == "agent":
            logger.info("[route_decision] → Routing to 'agent' node")
            return "agent"
        if route == "clarify":
            logger.info("[route_decision] → Routing to 'clarify' node")
            return "clarify"

        logger.info("[route_decision] → Routing to 'agent' node (default)")
        return "agent"

    workflow.add_conditional_edges("router", route_decision, ["agent", "clarify", "deep_research"])

    def after_clarify(state: AgentState) -> str:
        return "human_review" if state.get("needs_clarification") else "planner"

    workflow.add_conditional_edges("clarify", after_clarify, ["planner", "human_review"])

    # Planning path (agent + deep)
    workflow.add_edge("planner", "hitl_plan_review")
    workflow.add_edge("refine_plan", "hitl_plan_review")

    # Plan review (optional HITL) then dispatch searches
    workflow.add_conditional_edges(
        "hitl_plan_review", initiate_research, ["perform_parallel_search"]
    )

    # After search: deep mode goes through compressor, others go directly to writer
    def after_search(state: AgentState) -> str:
        if state.get("route") == "deep":
            return "compressor"
        return "writer"

    workflow.add_conditional_edges("perform_parallel_search", after_search, ["compressor", "writer"])

    # Compressor feeds into (optional) sources review, then writer.
    workflow.add_edge("compressor", "hitl_sources_review")
    workflow.add_edge("hitl_sources_review", "writer")

    def after_writer(state: AgentState) -> str:
        if state.get("route") == "deep":
            return "evaluator"
        return "human_review"

    workflow.add_edge("writer", "hitl_draft_review")
    workflow.add_conditional_edges("hitl_draft_review", after_writer, ["evaluator", "human_review"])

    def after_evaluator(state: AgentState) -> str:
        """
        Decide next step based on evaluator verdict and dimensions.

        Routes:
        - "pass" → human_review (report is good)
        - "revise" with low coverage/missing topics → refine_plan (need more info)
        - "revise" with acceptable coverage → reviser (rewrite report)
        - "incomplete" → refine_plan (major gaps)
        - max_revisions exceeded → human_review (stop iterating)
        """
        verdict = state.get("verdict", "pass")
        revision_count = int(state.get("revision_count", 0))
        max_revisions = int(state.get("max_revisions", 0))

        # Check if we've exceeded max revisions
        if revision_count >= max_revisions:
            logger.info(f"Max revisions ({max_revisions}) reached, proceeding to human review")
            return "human_review"

        if verdict == "pass":
            return "human_review"

        if verdict == "incomplete":
            return "refine_plan"

        # For "revise" verdict, check if we need more research or just a rewrite
        eval_dims = state.get("eval_dimensions", {})
        coverage = eval_dims.get("coverage", 0.7)
        missing_topics = state.get("missing_topics", [])

        # Low coverage or missing topics → need more research
        if coverage < 0.6 or missing_topics:
            logger.info(f"Low coverage ({coverage:.2f}) or missing topics, routing to refine_plan")
            return "refine_plan"

        # Acceptable coverage but poor writing → rewrite
        logger.info("Coverage acceptable, routing to reviser for rewrite")
        return "reviser"

    workflow.add_conditional_edges(
        "evaluator", after_evaluator, ["refine_plan", "reviser", "human_review"]
    )

    # Reviser rewrites the report and goes back to evaluator
    workflow.add_edge("reviser", "evaluator")

    workflow.add_edge("agent", "human_review")

    # Final edge
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
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Postgres for checkpointer: {e}") from e

    checkpointer = AsyncPostgresSaver(conn)

    # Setup tables
    await checkpointer.setup()

    logger.info("PostgreSQL checkpointer initialized")
    return checkpointer
