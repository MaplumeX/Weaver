from __future__ import annotations

from types import SimpleNamespace

import pytest

from common.checkpoint_runtime import build_resume_state, extract_deep_research_artifacts


def _fake_checkpointer(state: dict):
    return SimpleNamespace(
        get_tuple=lambda config: SimpleNamespace(
            checkpoint={"channel_values": state},
            metadata={"created_at": "2026-02-06T00:00:00Z"},
            parent_config={"configurable": {"checkpoint_id": "cp_parent"}},
        )
    )


def test_extract_deep_research_artifacts_from_nested_runtime() -> None:
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

  artifacts = extract_deep_research_artifacts(state)
  assert artifacts["queries"] == ["q1", "q2"]
  assert artifacts["research_topology"]["nodes"]["root"]["topic"] == "AI"
  assert artifacts["quality_summary"]["summary_count"] == 2
  assert "fetched_pages" in artifacts
  assert "passages" in artifacts


def test_extract_deep_research_artifacts_preserves_sources_and_strips_legacy_fields() -> None:
  state = {
      "route": "deep",
      "deep_research_artifacts": {
          "mode": "multi_agent",
          "queries": ["q1"],
          "research_topology": {"nodes": {"root": {"topic": "AI"}}},
          "quality_summary": {"summary_count": 1, "source_count": 1},
          "sources": [{"title": "Annual Report", "url": "https://example.com/"}],
          "claims": [{"claim": "deprecated", "status": "verified"}],
          "answer_units": [{"id": "answer_1"}],
          "coverage_obligations": [{"id": "obligation_1"}],
          "fetched_pages": [],
          "passages": [],
      },
  }

  artifacts = extract_deep_research_artifacts(state)
  assert artifacts["sources"][0]["url"] == "https://example.com/"
  assert "claims" not in artifacts
  assert "answer_units" not in artifacts
  assert "coverage_obligations" not in artifacts


def test_extract_deep_research_artifacts_drops_legacy_claims_but_preserves_passages() -> None:
  state = {
      "deep_research_artifacts": {
          "claims": [
              {
                  "claim": "Revenue increased in 2024.",
                  "status": "verified",
                  "evidence_urls": ["https://example.com/earnings"],
                  "evidence_passages": [
                      {
                          "url": "https://example.com/earnings",
                          "snippet_hash": "passage_123",
                          "quote": "In 2024, the company's revenue increased by 5% year over year.",
                          "heading_path": ["Results"],
                      }
                  ],
              }
          ],
          "passages": [
              {
                  "url": "https://example.com/earnings",
                  "text": "In 2024, the company's revenue increased by 5% year over year.",
                  "snippet_hash": "passage_123",
                  "quote": "In 2024, the company's revenue increased by 5% year over year.",
                  "heading_path": ["Results"],
              }
          ],
      },
  }

  artifacts = extract_deep_research_artifacts(state)
  assert "claims" not in artifacts
  passage = (artifacts.get("passages") or [None])[0] or {}
  assert passage.get("snippet_hash") == "passage_123"
  assert passage.get("heading_path") == ["Results"]
  assert passage.get("url") == "https://example.com/earnings"


@pytest.mark.asyncio
async def test_build_resume_state_preserves_canonical_artifacts_without_backfill() -> None:
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

  restored = await build_resume_state(_fake_checkpointer(state), "thread-2")
  assert restored is not None
  assert restored["deep_research_artifacts"]["queries"] == ["q1", "q2", "q3"]
  assert "research_plan" not in restored
  assert "research_topology" not in restored
  assert restored["resumed_from_checkpoint"] is True


@pytest.mark.asyncio
async def test_build_resume_state_does_not_inject_empty_artifacts() -> None:
  state = {
      "route": "general",
      "revision_count": 0,
  }

  restored = await build_resume_state(_fake_checkpointer(state), "thread-plain")
  assert restored is not None
  assert "deep_research_artifacts" not in restored
