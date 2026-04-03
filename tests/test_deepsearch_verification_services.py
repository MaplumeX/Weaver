from agent.runtime.deep.schema import (
    BranchSynthesis,
    CoverageEvaluationResult,
    CoverageObligation,
    ResearchTask,
)
from agent.runtime.deep.services.knowledge_gap import GapAnalysisResult
from agent.runtime.deep.services.verification import (
    build_gap_result,
    evaluate_obligations,
)


def test_evaluate_obligations_requires_meaningful_coverage_not_topic_overlap():
    criterion = "Explain the current state of AI chips aspect 1"
    task = ResearchTask(
        id="task_1",
        goal="AI chips",
        query="AI chips aspect 1",
        priority=1,
        objective=criterion,
        acceptance_criteria=[criterion],
        branch_id="branch_1",
    )
    synthesis = BranchSynthesis(
        id="synthesis_1",
        task_id=task.id,
        branch_id=task.branch_id,
        objective=criterion,
        summary="AI chips -> partial notes only",
        citation_urls=["https://example.com/ai-chips"],
    )
    obligation = CoverageObligation(
        id="obligation_1",
        task_id=task.id,
        branch_id=task.branch_id,
        source="task.acceptance_criteria",
        target=criterion,
        completion_criteria=[criterion],
    )

    results = evaluate_obligations(
        task=task,
        synthesis=synthesis,
        obligations=[obligation],
        claim_units=[],
        grounding_results=[],
    )

    assert len(results) == 1
    assert results[0].status == "unsatisfied"
    assert results[0].metadata["missing_criteria"] == [criterion]


def test_build_gap_result_preserves_fallback_gaps_when_contract_rows_pass():
    obligation = CoverageObligation(
        id="obligation_1",
        task_id="task_1",
        branch_id="branch_1",
        source="task.acceptance_criteria",
        target="Explain the current state of AI chips aspect 1",
        completion_criteria=["Explain the current state of AI chips aspect 1"],
    )
    coverage_result = CoverageEvaluationResult(
        id="coverage_eval_1",
        task_id="task_1",
        branch_id="branch_1",
        obligation_id=obligation.id,
        status="satisfied",
        summary="obligation satisfied",
    )
    fallback_result = GapAnalysisResult.from_dict(
        {
            "overall_coverage": 0.32,
            "confidence": 0.64,
            "gaps": [
                {
                    "aspect": "AI chips acceptance criteria",
                    "importance": "high",
                    "reason": "critical evidence is still missing",
                }
            ],
            "suggested_queries": ["AI chips follow-up evidence"],
            "covered_aspects": [],
            "analysis": "coverage is still incomplete",
        }
    )

    result = build_gap_result(
        obligations=[obligation],
        coverage_results=[coverage_result],
        fallback_result=fallback_result,
        fallback_analysis=fallback_result.analysis,
        fallback_queries=fallback_result.suggested_queries,
    )

    assert result.overall_coverage == 0.32
    assert result.is_sufficient is False
    assert [gap.aspect for gap in result.gaps] == ["AI chips acceptance criteria"]
    assert result.suggested_queries == ["AI chips follow-up evidence"]
