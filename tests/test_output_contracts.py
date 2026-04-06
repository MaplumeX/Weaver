import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.runtime.nodes.review as nodes
from agent.runtime.nodes.finalize import finalize_answer_node


def test_human_review_node_enforces_exact_reply_contract():
    result = nodes.human_review_node(
        {
            "input": "Use current web search to verify: What is the capital of France? Reply with exactly Paris.",
            "final_report": "Based on the search results, the capital of France is Paris.\n\nParis",
        },
        {"configurable": {}},
    )

    assert result["is_complete"] is True
    assert result["final_report"] == "Paris"


def test_human_review_node_preserves_report_without_exact_reply_contract():
    result = nodes.human_review_node(
        {
            "input": "What is the capital of France?",
            "final_report": "Paris is the capital of France.",
        },
        {"configurable": {}},
    )

    assert result["final_report"] == "Paris is the capital of France."


def test_finalize_answer_node_enforces_exact_reply_contract():
    result = finalize_answer_node(
        {
            "input": 'Reply with exactly "Paris".',
            "assistant_draft": "The answer is Paris.",
            "messages": [],
        },
        {"configurable": {}},
    )

    assert result["final_report"] == "Paris"
