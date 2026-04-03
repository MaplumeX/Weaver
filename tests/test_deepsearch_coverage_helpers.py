from agent.runtime.deep.support.graph_helpers import criterion_is_covered


def test_criterion_is_covered_handles_chinese_acceptance_criteria():
    assert criterion_is_covered(
        "当前市场由NVIDIA主导，并且供应链仍然紧张。",
        "说明AI芯片当前市场格局",
    )


def test_criterion_is_covered_keeps_basic_english_overlap_matching():
    assert criterion_is_covered(
        "Explain the current AI chip market structure and leaders.",
        "Explain the current state of AI chips",
    )
