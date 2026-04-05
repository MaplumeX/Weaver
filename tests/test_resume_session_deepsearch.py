import os
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep tests on in-memory checkpointer
os.environ["DATABASE_URL"] = ""

import main
from common.session_manager import SessionState


@pytest.mark.asyncio
async def test_resume_session_returns_deep_research_artifact_context(monkeypatch):
    artifacts = {
        "mode": "multi_agent",
        "queries": ["q1", "q2"],
        "research_topology": {"nodes": {"root": {"topic": "AI"}}},
        "quality_summary": {"summary_count": 2, "source_count": 5},
        "query_coverage": {"score": 0.8, "covered": 2, "total": 3},
        "freshness_summary": {"known_count": 3, "fresh_count": 1, "fresh_ratio": 0.33},
    }
    state = SessionState(
        thread_id="thread-123",
        state={
            "route": "deep",
            "final_report": "",
            "deep_research_artifacts": artifacts,
        },
        checkpoint_ts="",
        parent_checkpoint_id=None,
        deep_research_artifacts=artifacts,
    )

    class FakeManager:
        @staticmethod
        async def acan_resume(thread_id: str):
            return True, "ok"

        @staticmethod
        async def aget_session_state(thread_id: str):
            return state

        @staticmethod
        async def abuild_resume_state(thread_id: str, additional_input=None, update_state=None):
            restored = dict(state.state)
            restored["resumed_from_checkpoint"] = True
            return restored

    monkeypatch.setattr(main, "checkpointer", object())
    monkeypatch.setattr(
        "common.session_manager.get_session_manager",
        lambda checkpointer: FakeManager(),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/sessions/thread-123/resume", json={})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["current_state"]["has_deep_research_artifacts"] is True
    assert data["deep_research_resume"]["artifacts_restored"] is True
    assert data["deep_research_resume"]["mode"] == "multi_agent"
    assert data["deep_research_resume"]["query_coverage_score"] == 0.8
    assert data["deep_research_resume"]["freshness_warning"] == ""
    assert "research_plan_count" not in data["resume_state"]


@pytest.mark.asyncio
async def test_resume_session_uses_quality_summary_coverage_fallback(monkeypatch):
    artifacts = {
        "mode": "multi_agent",
        "queries": ["q1"],
        "quality_summary": {"query_coverage_score": 0.6, "summary_count": 1},
    }
    state = SessionState(
        thread_id="thread-coverage-fallback",
        state={
            "route": "deep",
            "deep_research_artifacts": artifacts,
        },
        checkpoint_ts="",
        parent_checkpoint_id=None,
        deep_research_artifacts=artifacts,
    )

    class FakeManager:
        @staticmethod
        async def acan_resume(thread_id: str):
            return True, "ok"

        @staticmethod
        async def aget_session_state(thread_id: str):
            return state

        @staticmethod
        async def abuild_resume_state(thread_id: str, additional_input=None, update_state=None):
            restored = dict(state.state)
            restored["resumed_from_checkpoint"] = True
            return restored

    monkeypatch.setattr(main, "checkpointer", object())
    monkeypatch.setattr(
        "common.session_manager.get_session_manager",
        lambda checkpointer: FakeManager(),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/sessions/thread-coverage-fallback/resume", json={})

    assert resp.status_code == 200
    data = resp.json()
    assert data["deep_research_resume"]["query_coverage_score"] == 0.6
