from agent.research.query_strategy import (
    analyze_query_coverage,
    backfill_diverse_queries,
    is_time_sensitive_topic,
)


def test_backfill_diverse_queries_improves_dimension_coverage():
    queries = backfill_diverse_queries(
        topic="deep research agent",
        existing_queries=["deep research agent architecture"],
        historical_queries=[],
        query_num=5,
    )

    coverage = analyze_query_coverage(queries)

    assert len(queries) == 5
    assert coverage["score"] >= 0.8
    assert "official" in coverage["covered_dimensions"]
    assert "evidence" in coverage["covered_dimensions"]
    assert "risk" in coverage["covered_dimensions"]


def test_is_time_sensitive_topic_supports_english_and_chinese():
    assert is_time_sensitive_topic("latest ai policy updates") is True
    assert is_time_sensitive_topic("AI 最新进展") is True
    assert is_time_sensitive_topic("history of relational databases") is False
