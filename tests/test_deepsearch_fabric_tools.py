import time
from types import SimpleNamespace

import pytest

from agent.runtime.deep.multi_agent.schema import (
    BranchSynthesis,
    ResearchTask,
    VerificationResult,
)
from agent.runtime.deep.multi_agent.store import ArtifactStore, ResearchTaskQueue
from agent.runtime.deep.multi_agent.tool_agents import (
    DeepResearchToolAgentSession,
    build_deep_research_fabric_tools,
)


class _FakeRuntime:
    def __init__(self):
        self.start_ts = time.time()
        self.searches_used = 0
        self.tokens_used = 0
        self.max_seconds = 3600.0
        self.max_tokens = 100_000
        self.max_searches = 5
        self.config = {}
        self.task_queue = ResearchTaskQueue()
        self.artifact_store = ArtifactStore()
        self.claim_verifier = SimpleNamespace(verify_report=lambda *_args, **_kwargs: [])
        self.verifier = SimpleNamespace(
            analyze=lambda *_args, **_kwargs: SimpleNamespace(
                to_dict=lambda: {
                    "overall_coverage": 1.0,
                    "confidence": 1.0,
                    "gaps": [],
                    "suggested_queries": [],
                    "covered_aspects": [],
                    "analysis": "sufficient",
                },
                overall_coverage=1.0,
                confidence=1.0,
                gaps=[],
                suggested_queries=[],
                analysis="sufficient",
            )
        )

    def _search_with_tracking(self, payload, _config):
        query = str(payload["query"])
        return [
            {
                "title": f"{query} title",
                "url": f"https://example.com/{query.replace(' ', '-')}",
                "summary": f"{query} summary",
                "raw_excerpt": f"{query} excerpt",
                "provider": "fake",
            }
        ]


def _make_task() -> ResearchTask:
    return ResearchTask(
        id="task-1",
        goal="Assess AI chips",
        query="AI chips",
        priority=1,
        objective="Assess AI chips market and supply chain",
        branch_id="branch-1",
        allowed_tools=["search", "read", "extract"],
        acceptance_criteria=["Explain the current state of AI chips"],
    )


def _tool_map(session: DeepResearchToolAgentSession):
    return {tool.name: tool for tool in build_deep_research_fabric_tools(session)}


def test_researcher_fabric_tools_create_follow_up_and_research_bundle():
    runtime = _FakeRuntime()
    task = _make_task()
    session = DeepResearchToolAgentSession(
        runtime=runtime,
        role="researcher",
        topic="AI chips",
        graph_run_id="graph-1",
        branch_id=task.branch_id,
        task=task,
        allowed_capabilities={"search", "read", "extract"},
        approved_scope={"id": "scope-1", "status": "approved"},
    )
    tools = _tool_map(session)

    search_results = tools["fabric_search"].invoke({"query": "AI chips", "max_results": 1})
    extracted = tools["fabric_extract"].invoke({"url": search_results[0]["url"]})
    follow_up = tools["fabric_request_follow_up"].invoke(
        {
            "request_type": "follow_up",
            "summary": "Need one more earnings-call source",
            "suggested_queries": ["AI chips earnings call"],
        }
    )
    submission = tools["fabric_submit_research_bundle"].invoke(
        {
            "summary": "AI chips demand remains strong across cloud and training workloads.",
            "findings": ["Demand remains strong across cloud and training workloads."],
        }
    )

    assert extracted["source_candidate_id"]
    assert follow_up["request_type"] == "follow_up"
    assert session.branch_synthesis is not None
    assert session.submissions[-1].submission_kind == "research_bundle"
    assert submission["result_status"] == "completed"


def test_reporter_fabric_tool_returns_only_fully_verified_branch_summaries():
    runtime = _FakeRuntime()
    passed = BranchSynthesis(
        id="synth-1",
        task_id="task-1",
        branch_id="branch-1",
        objective="Passed branch",
        summary="Passed summary",
    )
    failed = BranchSynthesis(
        id="synth-2",
        task_id="task-2",
        branch_id="branch-2",
        objective="Failed branch",
        summary="Failed summary",
    )
    runtime.artifact_store.add_branch_synthesis(passed)
    runtime.artifact_store.add_branch_synthesis(failed)
    runtime.artifact_store.add_verification_results(
        [
            VerificationResult(
                id="claim-1",
                task_id="task-1",
                branch_id="branch-1",
                synthesis_id="synth-1",
                validation_stage="claim_check",
                outcome="passed",
                summary="ok",
            ),
            VerificationResult(
                id="coverage-1",
                task_id="task-1",
                branch_id="branch-1",
                synthesis_id="synth-1",
                validation_stage="coverage_check",
                outcome="passed",
                summary="ok",
            ),
            VerificationResult(
                id="claim-2",
                task_id="task-2",
                branch_id="branch-2",
                synthesis_id="synth-2",
                validation_stage="claim_check",
                outcome="passed",
                summary="ok",
            ),
            VerificationResult(
                id="coverage-2",
                task_id="task-2",
                branch_id="branch-2",
                synthesis_id="synth-2",
                validation_stage="coverage_check",
                outcome="failed",
                summary="not ok",
            ),
        ]
    )
    session = DeepResearchToolAgentSession(
        runtime=runtime,
        role="reporter",
        topic="AI chips",
        graph_run_id="graph-1",
        branch_id="root-1",
    )
    tools = _tool_map(session)

    verified = tools["fabric_get_verified_branch_summaries"].invoke({})

    assert [item["task_id"] for item in verified] == ["task-1"]


def test_fabric_search_rejects_budget_exhaustion():
    runtime = _FakeRuntime()
    runtime.searches_used = 1
    runtime.max_searches = 1
    task = _make_task()
    session = DeepResearchToolAgentSession(
        runtime=runtime,
        role="researcher",
        topic="AI chips",
        graph_run_id="graph-1",
        branch_id=task.branch_id,
        task=task,
        allowed_capabilities={"search"},
    )
    tools = _tool_map(session)

    with pytest.raises(RuntimeError, match="search_budget_exceeded"):
        tools["fabric_search"].invoke({"query": "AI chips", "max_results": 1})
