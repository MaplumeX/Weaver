from langgraph.constants import END, START
from langgraph.graph import StateGraph
from typing_extensions import TypedDict

import agent.runtime.nodes.routing as routing
from agent.runtime.graph import create_research_graph


class RouteState(TypedDict, total=False):
    input: str
    images: list[dict]
    route: str
    routing_reasoning: str
    routing_confidence: float


def test_create_research_graph_only_keeps_active_root_nodes():
    graph = create_research_graph()
    node_names = set(graph.get_graph().nodes.keys())

    assert {"router", "agent", "deep_research", "human_review"} <= node_names

    removed = {
        "clarify",
        "planner",
        "refine_plan",
        "hitl_plan_review",
        "perform_parallel_search",
        "writer",
        "hitl_draft_review",
        "evaluator",
        "reviser",
        "compressor",
        "hitl_sources_review",
    }
    assert removed.isdisjoint(node_names)


def test_route_node_low_confidence_falls_back_to_agent(monkeypatch):
    monkeypatch.setattr(
        "agent.core.smart_router.smart_route",
        lambda **_kwargs: {
            "route": "deep",
            "routing_reasoning": "uncertain",
            "routing_confidence": 0.18,
        },
    )

    result = routing.route_node(
        {"input": "help me with this", "images": []},
        {"configurable": {"routing_confidence_threshold": 0.6}},
    )

    assert result["route"] == "agent"
    assert result["routing_confidence"] == 0.18
    assert "needs_clarification" not in result
    assert "clarification_question" not in result


def test_route_node_receives_runnable_config_when_invoked_by_graph(monkeypatch):
    monkeypatch.setattr(
        "agent.core.smart_router.smart_route",
        lambda **_kwargs: {
            "route": "agent",
            "routing_reasoning": "default",
            "routing_confidence": 0.9,
        },
    )

    builder = StateGraph(RouteState)
    builder.add_node("router", routing.route_node)
    builder.add_edge(START, "router")
    builder.add_edge("router", END)
    graph = builder.compile()

    result = graph.invoke(
        {"input": "hello", "images": []},
        {"configurable": {"routing_confidence_threshold": 0.6}, "recursion_limit": 10},
    )

    assert result["route"] == "agent"
    assert result["routing_confidence"] == 0.9
