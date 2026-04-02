from types import SimpleNamespace

from common.session_manager import SessionManager


def _fake_checkpoint_tuple(state):
    return SimpleNamespace(
        checkpoint={"channel_values": state},
        metadata={"created_at": "2026-02-06T00:00:00Z"},
        parent_config={"configurable": {"checkpoint_id": "cp_parent"}},
    )


def test_session_manager_extracts_deep_research_artifacts():
    state = {
        "route": "deep",
        "research_topology": {"nodes": {"root": {"topic": "AI"}}},
        "quality_summary": {"summary_count": 2, "source_count": 5},
        "deep_runtime": {
            "engine": "multi_agent",
            "task_queue": {
                "tasks": [
                    {"id": "task_1", "query": "q1", "priority": 1, "created_at": "2026-04-02T00:00:00Z"},
                    {"id": "task_2", "query": "q2", "priority": 2, "created_at": "2026-04-02T00:01:00Z"},
                ]
            },
            "artifact_store": {"final_report": {"report_markdown": ""}},
            "runtime_state": {},
            "agent_runs": [],
        },
    }

    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)

    session_state = manager.get_session_state("thread-1")
    assert session_state is not None
    payload = session_state.to_dict()

    artifacts = payload["deep_research_artifacts"]
    assert artifacts["queries"] == ["q1", "q2"]
    assert artifacts["research_topology"]["nodes"]["root"]["topic"] == "AI"
    assert artifacts["quality_summary"]["summary_count"] == 2
    assert "fetched_pages" in artifacts
    assert "passages" in artifacts


def test_session_manager_build_resume_state_preserves_canonical_artifacts_without_backfill():
    artifacts = {
        "mode": "multi_agent",
        "queries": ["q1", "q2", "q3"],
        "research_topology": {"nodes": {"root": {"topic": "AI"}}},
        "quality_summary": {"summary_count": 3},
        "query_coverage": {"score": 0.75, "covered": 3, "total": 4},
        "freshness_summary": {"known_count": 2, "fresh_count": 1, "fresh_ratio": 0.5},
    }
    state = {
        "route": "deep",
        "revision_count": 1,
        "deep_research_artifacts": artifacts,
    }

    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)

    restored = manager.build_resume_state("thread-2")
    assert restored is not None
    assert restored["deep_research_artifacts"]["queries"] == ["q1", "q2", "q3"]
    assert "research_plan" not in restored
    assert "research_topology" not in restored
    assert restored["resumed_from_checkpoint"] is True


def test_session_manager_extracts_empty_artifacts_without_deep_research_signals():
    state = {
        "route": "general",
        "revision_count": 0,
        "summary_notes": [],
        "scraped_content": [],
    }
    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)

    session_state = manager.get_session_state("thread-plain")
    assert session_state is not None
    assert session_state.deep_research_artifacts == {}


def test_session_manager_build_resume_state_does_not_inject_empty_artifacts():
    state = {
        "route": "general",
        "revision_count": 0,
    }
    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)

    restored = manager.build_resume_state("thread-plain")
    assert restored is not None
    assert "deep_research_artifacts" not in restored


def test_session_manager_extracts_query_coverage_from_quality_summary_fallback():
    state = {
        "route": "deep",
        "research_topology": {},
        "quality_summary": {"query_coverage_score": 0.6, "summary_count": 1},
        "deep_runtime": {
            "engine": "multi_agent",
            "task_queue": {"tasks": []},
            "artifact_store": {"final_report": {"report_markdown": ""}},
            "runtime_state": {},
            "agent_runs": [],
        },
    }
    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)

    session_state = manager.get_session_state("thread-fallback")
    assert session_state is not None
    artifacts = session_state.deep_research_artifacts
    assert artifacts["query_coverage"]["score"] == 0.6


def test_session_manager_preserves_sources_and_claims_in_deep_research_artifacts():
    state = {
        "route": "deep",
        "deep_research_artifacts": {
            "mode": "multi_agent",
            "queries": ["q1"],
            "research_topology": {"nodes": {"root": {"topic": "AI"}}},
            "quality_summary": {"summary_count": 1, "source_count": 1},
            "sources": [{"title": "Annual Report", "url": "https://example.com/"}],
            "claims": [
                {
                    "claim": "Revenue increased by 20% in 2024.",
                    "status": "verified",
                    "evidence_urls": ["https://example.com/"],
                    "evidence_passages": [],
                }
            ],
            "fetched_pages": [],
            "passages": [],
        },
    }

    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)
    session_state = manager.get_session_state("thread-evidence")
    assert session_state is not None

    artifacts = session_state.deep_research_artifacts
    assert artifacts["sources"][0]["url"] == "https://example.com/"
    assert artifacts["claims"][0]["evidence_urls"][0] == "https://example.com/"


def test_session_manager_extracts_artifacts_from_nested_deep_runtime():
    state = {
        "route": "deep",
        "deep_runtime": {
            "engine": "multi_agent",
            "task_queue": {
                "tasks": [
                    {
                        "id": "task_1",
                        "query": "q1",
                        "priority": 1,
                        "created_at": "2026-04-02T00:00:00Z",
                    }
                ],
                "stats": {"completed": 1},
            },
            "artifact_store": {},
            "runtime_state": {"engine": "multi_agent"},
            "agent_runs": [],
        },
        "quality_summary": {"summary_count": 1},
    }

    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)
    session_state = manager.get_session_state("thread-nested-runtime")

    assert session_state is not None
    artifacts = session_state.deep_research_artifacts
    assert artifacts["mode"] == "multi_agent"
    assert artifacts["queries"] == ["q1"]
