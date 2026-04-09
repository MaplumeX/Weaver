from langchain_core.messages import AIMessage, HumanMessage

from agent.core import chat_context


def test_build_recent_runtime_messages_uses_latest_window(monkeypatch):
    monkeypatch.setattr(chat_context.settings, "chat_recent_turns", 3, raising=False)

    messages = [
        {"seq": 1, "role": "user", "content": "u1"},
        {"seq": 2, "role": "assistant", "content": "a1"},
        {"seq": 3, "role": "user", "content": "u2"},
        {"seq": 4, "role": "assistant", "content": "a2"},
    ]

    runtime_messages = chat_context.build_recent_runtime_messages(messages)

    assert [type(message) for message in runtime_messages] == [AIMessage, HumanMessage, AIMessage]
    assert [message.content for message in runtime_messages] == ["a1", "u2", "a2"]


def test_build_short_term_snapshot_updates_summary_incrementally(monkeypatch):
    monkeypatch.setattr(chat_context.settings, "chat_recent_turns", 3, raising=False)
    monkeypatch.setattr(
        chat_context.settings,
        "chat_short_term_summary_trigger_turns",
        4,
        raising=False,
    )
    monkeypatch.setattr(chat_context.settings, "chat_short_term_pinned_max_items", 8, raising=False)
    monkeypatch.setattr(
        chat_context.settings,
        "chat_short_term_recent_tools_max_items",
        5,
        raising=False,
    )
    monkeypatch.setattr(
        chat_context.settings,
        "chat_short_term_recent_sources_max_items",
        5,
        raising=False,
    )

    captured = {}

    def fake_summarize(messages, *, previous_summary=""):
        captured["previous_summary"] = previous_summary
        captured["contents"] = [message.content for message in messages]
        return "updated summary"

    monkeypatch.setattr(chat_context, "summarize_history_slice", fake_summarize)

    snapshot = chat_context.build_short_term_snapshot(
        [
            {"seq": 1, "role": "user", "content": "请用中文回答"},
            {"seq": 2, "role": "assistant", "content": "好的"},
            {"seq": 3, "role": "user", "content": "先解释上下文回填"},
            {"seq": 4, "role": "assistant", "content": "这是已有摘要吗？"},
            {"seq": 5, "role": "user", "content": "继续"},
        ],
        previous_snapshot={
            "version": 1,
            "summarized_through_seq": 1,
            "rolling_summary": "old summary",
        },
        now_iso="2026-04-09T12:00:00Z",
    )

    assert captured["previous_summary"] == "old summary"
    assert captured["contents"] == ["好的"]
    assert snapshot["rolling_summary"] == "updated summary"
    assert snapshot["summarized_through_seq"] == 2
    assert snapshot["pinned_items"] == ["请用中文回答"]
    assert snapshot["updated_at"] == "2026-04-09T12:00:00Z"


def test_build_short_term_snapshot_extracts_recent_tools_sources_and_open_questions(monkeypatch):
    monkeypatch.setattr(chat_context.settings, "chat_recent_turns", 4, raising=False)
    monkeypatch.setattr(
        chat_context.settings,
        "chat_short_term_summary_trigger_turns",
        10,
        raising=False,
    )
    monkeypatch.setattr(
        chat_context.settings,
        "chat_short_term_recent_tools_max_items",
        5,
        raising=False,
    )
    monkeypatch.setattr(
        chat_context.settings,
        "chat_short_term_recent_sources_max_items",
        5,
        raising=False,
    )
    monkeypatch.setattr(
        chat_context.settings,
        "chat_short_term_open_questions_max_items",
        5,
        raising=False,
    )

    snapshot = chat_context.build_short_term_snapshot(
        [
            {"seq": 1, "role": "user", "content": "帮我查文档"},
            {
                "seq": 2,
                "role": "assistant",
                "content": "你还想看数据库还是运行时？",
                "sources": [{"title": "Doc", "url": "https://example.com/doc"}],
                "tool_invocations": [
                    {
                        "toolName": "search_docs",
                        "state": "completed",
                        "args": {"query": "runtime persistence"},
                    }
                ],
                "process_events": [
                    {
                        "type": "tool",
                        "data": {
                            "name": "search_docs",
                            "status": "completed",
                            "args": {"query": "runtime persistence"},
                        },
                    }
                ],
            },
        ],
        now_iso="2026-04-09T12:30:00Z",
    )

    assert snapshot["open_questions"] == ["你还想看数据库还是运行时？"]
    assert any("search_docs" in item for item in snapshot["recent_tools"])
    assert any("Doc" in item for item in snapshot["recent_sources"])
