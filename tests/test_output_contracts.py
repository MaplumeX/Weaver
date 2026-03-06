import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.workflows import nodes


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
