from __future__ import annotations

from common.checkpoint_runtime import extract_deep_research_artifacts


def test_extract_deep_research_artifacts_drops_legacy_control_plane_payload() -> None:
    state = {
        "route": "deep",
        "deep_research_artifacts": {
            "mode": "multi_agent",
            "queries": ["q1"],
            "quality_summary": {"summary_count": 1},
            "control_plane": {
                "active_agent": "supervisor",
                "latest_handoff": {"from": "scope", "to": "supervisor"},
                "handoff_history": [{"from": "scope", "to": "supervisor"}],
            },
        },
    }

    artifacts = extract_deep_research_artifacts(state)

    assert artifacts["queries"] == ["q1"]
    assert "control_plane" not in artifacts


def test_extract_deep_research_artifacts_does_not_backfill_runtime_handoff_fields() -> None:
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
                    },
                ]
            },
            "artifact_store": {"final_report": {"report_markdown": ""}},
            "runtime_state": {
                "active_agent": "reviewer",
                "handoff_envelope": {"from": "researcher", "to": "reviewer"},
                "handoff_history": [{"from": "researcher", "to": "reviewer"}],
            },
            "agent_runs": [],
        },
    }

    artifacts = extract_deep_research_artifacts(state)

    assert artifacts["runtime_state"]["active_agent"] == "reviewer"
    assert "control_plane" not in artifacts
