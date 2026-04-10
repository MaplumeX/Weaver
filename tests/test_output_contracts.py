import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.chat.finalize import finalize_answer_node


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
    assert result["is_complete"] is True


def test_finalize_answer_node_preserves_report_without_exact_reply_contract():
    result = finalize_answer_node(
        {
            "input": "What is the capital of France?",
            "assistant_draft": "Paris is the capital of France.",
            "messages": [],
        },
        {"configurable": {}},
    )

    assert result["final_report"] == "Paris is the capital of France."
    assert result["is_complete"] is True
