from agent.core.context import ResearchWorkerContext
from agent.runtime.deep.orchestration.graph import _restore_worker_result
from agent.runtime.deep.schema import (
    BranchBrief,
    BranchSynthesis,
    EvidenceCard,
    EvidencePassage,
    FetchedDocument,
    KnowledgeGap,
    ReportSectionDraft,
    ResearchTask,
    SourceCandidate,
    VerificationResult,
    WorkerExecutionResult,
)
from agent.runtime.deep.store import ArtifactStore, ResearchTaskQueue


def test_branch_task_and_artifacts_are_checkpoint_safe():
    queue = ResearchTaskQueue()
    task = ResearchTask(
        id="task-1",
        goal="AI chip branch",
        query="AI chip roadmap",
        priority=1,
        objective="Map the current AI chip roadmap",
        task_kind="branch_research",
        acceptance_criteria=["Explain the current roadmap"],
        allowed_tools=["search", "read", "extract", "synthesize"],
        input_artifact_ids=["scope-1"],
        output_artifact_types=["branch_synthesis", "evidence_passage"],
        query_hints=["AI chip roadmap"],
        branch_id="branch-1",
        stage="extract",
    )
    queue.enqueue([task])

    restored_queue = ResearchTaskQueue.from_snapshot(queue.snapshot())
    restored_task = restored_queue.get(task.id)

    assert restored_task is not None
    assert restored_task.objective == task.objective
    assert restored_task.task_kind == "branch_research"
    assert restored_task.allowed_tools == ["search", "read", "extract", "synthesize"]
    assert restored_task.stage == "extract"

    store = ArtifactStore()
    store.put_brief(
        BranchBrief(
            id="branch-1",
            topic="AI chips",
            summary="Investigate roadmap evidence",
            objective=task.objective,
            task_kind=task.task_kind,
            acceptance_criteria=list(task.acceptance_criteria),
            allowed_tools=list(task.allowed_tools),
            latest_task_id=task.id,
            current_stage="synthesize",
        )
    )
    store.add_source_candidates(
        [
            SourceCandidate(
                id="source-1",
                task_id=task.id,
                branch_id="branch-1",
                title="Roadmap article",
                url="https://example.com/roadmap",
                summary="Roadmap summary",
            )
        ]
    )
    store.add_fetched_documents(
        [
            FetchedDocument(
                id="doc-1",
                task_id=task.id,
                branch_id="branch-1",
                source_candidate_id="source-1",
                url="https://example.com/roadmap",
                title="Roadmap article",
                content="Roadmap content",
            )
        ]
    )
    store.add_evidence_passages(
        [
            EvidencePassage(
                id="passage-1",
                task_id=task.id,
                branch_id="branch-1",
                document_id="doc-1",
                url="https://example.com/roadmap",
                text="Roadmap content",
                quote="Roadmap content",
                source_title="Roadmap article",
            )
        ]
    )
    store.add_evidence(
        [
            EvidenceCard(
                id="evidence-1",
                task_id=task.id,
                branch_id="branch-1",
                source_title="Roadmap article",
                source_url="https://example.com/roadmap",
                summary="Roadmap summary",
                excerpt="Roadmap content",
            )
        ]
    )
    store.add_branch_synthesis(
        BranchSynthesis(
            id="synthesis-1",
            task_id=task.id,
            branch_id="branch-1",
            objective=task.objective,
            summary="Roadmap synthesis",
            findings=["Roadmap finding"],
            evidence_passage_ids=["passage-1"],
            source_document_ids=["doc-1"],
            citation_urls=["https://example.com/roadmap"],
        )
    )
    store.add_verification_results(
        [
            VerificationResult(
                id="verify-1",
                task_id=task.id,
                branch_id="branch-1",
                synthesis_id="synthesis-1",
                validation_stage="claim_check",
                outcome="passed",
                summary="Claim check passed",
            ),
            VerificationResult(
                id="verify-2",
                task_id=task.id,
                branch_id="branch-1",
                synthesis_id="synthesis-1",
                validation_stage="coverage_check",
                outcome="passed",
                summary="Coverage check passed",
            ),
        ]
    )
    store.replace_gaps(
        [
            KnowledgeGap(
                id="gap-1",
                aspect="pricing",
                importance="medium",
                reason="Needs more evidence",
                branch_id="branch-1",
            )
        ]
    )
    store.add_section_draft(
        ReportSectionDraft(
            id="section-1",
            task_id=task.id,
            branch_id="branch-1",
            title="Roadmap",
            summary="Roadmap synthesis",
            evidence_ids=["evidence-1"],
        )
    )

    restored_store = ArtifactStore.from_snapshot(store.snapshot())

    assert restored_store.get_brief("branch-1") is not None
    assert len(restored_store.source_candidates(branch_id="branch-1")) == 1
    assert len(restored_store.fetched_documents(branch_id="branch-1")) == 1
    assert len(restored_store.evidence_passages(branch_id="branch-1")) == 1
    assert len(restored_store.branch_syntheses(branch_id="branch-1")) == 1
    assert len(restored_store.verification_results(branch_id="branch-1")) == 2


def test_worker_execution_result_roundtrip_preserves_branch_bundle():
    task = ResearchTask(
        id="task-2",
        goal="AI chip branch",
        query="AI chip roadmap",
        priority=1,
        objective="Map the current AI chip roadmap",
        task_kind="branch_research",
        branch_id="branch-2",
        stage="synthesize",
    )
    context = ResearchWorkerContext(scope_id="scope-1", task_id=task.id, agent_id="researcher-1", query=task.query)
    result = WorkerExecutionResult(
        task=task,
        context=context,
        source_candidates=[
            SourceCandidate(
                id="source-2",
                task_id=task.id,
                branch_id="branch-2",
                title="Roadmap article",
                url="https://example.com/roadmap",
                summary="Roadmap summary",
            )
        ],
        fetched_documents=[
            FetchedDocument(
                id="doc-2",
                task_id=task.id,
                branch_id="branch-2",
                source_candidate_id="source-2",
                url="https://example.com/roadmap",
                title="Roadmap article",
                content="Roadmap content",
            )
        ],
        evidence_passages=[
            EvidencePassage(
                id="passage-2",
                task_id=task.id,
                branch_id="branch-2",
                document_id="doc-2",
                url="https://example.com/roadmap",
                text="Roadmap content",
                quote="Roadmap content",
                source_title="Roadmap article",
            )
        ],
        branch_synthesis=BranchSynthesis(
            id="synthesis-2",
            task_id=task.id,
            branch_id="branch-2",
            objective=task.objective,
            summary="Roadmap synthesis",
            findings=["Roadmap finding"],
            evidence_passage_ids=["passage-2"],
            source_document_ids=["doc-2"],
            citation_urls=["https://example.com/roadmap"],
        ),
        evidence_cards=[],
        section_draft=None,
        coordination_requests=[],
        submission=None,
        raw_results=[{"url": "https://example.com/roadmap", "summary": "Roadmap summary"}],
        tokens_used=42,
        searches_used=2,
        branch_id="branch-2",
        task_stage="synthesize",
        result_status="completed",
        agent_run=None,
    )

    restored = _restore_worker_result(result.to_dict())

    assert restored.searches_used == 2
    assert restored.task_stage == "synthesize"
    assert restored.branch_synthesis is not None
    assert restored.branch_synthesis.summary == "Roadmap synthesis"
    assert restored.source_candidates[0].url == "https://example.com/roadmap"
