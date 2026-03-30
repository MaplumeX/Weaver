import json

import pytest

import main


class _DummyGraph:
    async def astream_events(self, *args, **kwargs):
        final_output = {
            "is_complete": True,
            "final_report": "FINAL",
            "scraped_content": [
                {
                    "results": [
                        {"title": "A", "url": "https://example.com/report"},
                    ]
                }
            ],
        }

        yield {
            "event": "on_node_end",
            "name": "human_review",
            "data": {"output": final_output},
        }
        yield {
            "event": "on_graph_end",
            "name": "human_review",
            "data": {"output": final_output},
        }


async def _noop_async(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_stream_emits_single_final_report_artifact_for_duplicate_end_events(monkeypatch):
    memory_calls: list[str] = []
    interaction_calls: list[tuple[str, str]] = []
    store_calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(main, "research_graph", _DummyGraph())
    monkeypatch.setattr(main, "add_memory_entry", lambda report: memory_calls.append(report))
    monkeypatch.setattr(
        main,
        "store_interaction",
        lambda prompt, report: interaction_calls.append((prompt, report)),
    )
    monkeypatch.setattr(
        main,
        "_store_add",
        lambda prompt, report, user_id=None: store_calls.append((prompt, report, user_id)),
    )
    monkeypatch.setattr(main, "fetch_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)

    chunks: list[str] = []
    async for chunk in main.stream_agent_events("hi", thread_id="thread_test"):
        chunks.append(chunk)

    payloads = [
        json.loads(chunk[2:])
        for chunk in chunks
        if chunk.startswith("0:")
    ]

    completion_payloads = [p for p in payloads if p.get("type") == "completion"]
    artifact_payloads = [p for p in payloads if p.get("type") == "artifact"]
    source_payloads = [p for p in payloads if p.get("type") == "sources"]

    assert len(completion_payloads) == 1
    assert completion_payloads[0]["data"]["content"] == "FINAL"

    assert len(artifact_payloads) == 1
    assert artifact_payloads[0]["data"]["type"] == "report"
    assert artifact_payloads[0]["data"]["content"] == "FINAL"

    assert len(source_payloads) == 1
    assert source_payloads[0]["data"]["items"][0]["url"] == "https://example.com/report"

    assert memory_calls == ["FINAL"]
    assert interaction_calls == [("hi", "FINAL")]
    assert store_calls == [("hi", "FINAL", main.settings.memory_user_id)]
