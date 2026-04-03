from agent.runtime.deep.schema import (
    BranchSynthesis,
    ClaimGroundingResult,
    ClaimUnit,
    CoverageEvaluationResult,
    CoverageObligation,
    ResearchTask,
)
from agent.runtime.deep.services.knowledge_gap import GapAnalysisResult
from agent.runtime.deep.services.verification import (
    aggregate_revision_issues,
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


def test_evaluate_obligations_uses_grounded_claim_evidence_mapping():
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
        summary="Short summary only",
        citation_urls=["https://example.com/ai-chips"],
        evidence_passage_ids=["passage-1"],
    )
    obligation = CoverageObligation(
        id="obligation_1",
        task_id=task.id,
        branch_id=task.branch_id,
        source="task.acceptance_criteria",
        target=criterion,
        completion_criteria=[criterion],
    )
    claim = ClaimUnit(
        id="claim_1",
        task_id=task.id,
        branch_id=task.branch_id,
        claim="The current state of AI chips aspect 1 is dominated by supply-constrained accelerators.",
        citation_urls=["https://example.com/ai-chips"],
        evidence_passage_ids=["passage-1"],
    )
    grounding = ClaimGroundingResult(
        id="grounding_1",
        task_id=task.id,
        branch_id=task.branch_id,
        claim_id=claim.id,
        status="grounded",
        summary="grounded with filing evidence",
        evidence_urls=["https://example.com/ai-chips"],
        evidence_passage_ids=["passage-1"],
    )

    results = evaluate_obligations(
        task=task,
        synthesis=synthesis,
        obligations=[obligation],
        claim_units=[claim],
        grounding_results=[grounding],
    )

    assert len(results) == 1
    assert results[0].status == "satisfied"
    assert results[0].metadata["supported_claim_ids"] == [claim.id]
    assert results[0].metadata["used_grounded_claims_only"] is True


def test_build_gap_result_keeps_fallback_gaps_advisory_when_contract_rows_pass():
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

    assert result.overall_coverage == 1.0
    assert result.is_sufficient is True
    assert [gap.aspect for gap in result.gaps] == ["AI chips acceptance criteria"]
    assert all(gap.advisory for gap in result.gaps)
    assert result.suggested_queries == ["AI chips follow-up evidence"]


def test_aggregate_revision_issues_keeps_partially_satisfied_obligation_non_blocking():
    task = ResearchTask(
        id="task_1",
        goal="AI chips",
        query="AI chips aspect 1",
        priority=1,
        objective="Explain the current state of AI chips aspect 1",
        branch_id="branch_1",
    )
    claim = ClaimUnit(
        id="claim_1",
        task_id=task.id,
        branch_id=task.branch_id,
        claim="AI chips aspect 1 has partial evidence",
    )
    obligation = CoverageObligation(
        id="obligation_1",
        task_id=task.id,
        branch_id=task.branch_id,
        source="task.acceptance_criteria",
        target="Explain the current state of AI chips aspect 1",
        completion_criteria=["Explain the current state of AI chips aspect 1"],
    )
    coverage_result = CoverageEvaluationResult(
        id="coverage_eval_1",
        task_id=task.id,
        branch_id=task.branch_id,
        obligation_id=obligation.id,
        status="partially_satisfied",
        summary="obligation partially satisfied",
        evidence_urls=["https://example.com/ai-chips"],
        evidence_passage_ids=["passage-1"],
    )

    issues = aggregate_revision_issues(
        task=task,
        claim_units=[claim],
        obligations=[obligation],
        grounding_results=[],
        coverage_results=[coverage_result],
        consistency_results=[],
    )

    assert len(issues) == 1
    assert issues[0].blocking is False
    assert issues[0].recommended_action == "spawn_follow_up_branch"
