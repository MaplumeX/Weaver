import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, HumanMessage

import main


@pytest.mark.asyncio
async def test_chat_stream_creates_session_and_persists_messages(monkeypatch):
    captured: list[tuple[str, dict]] = []

    class FakeSessionService:
        async def start_session_run(self, **payload):
            captured.append(("start", payload))

        async def finalize_assistant_message(self, **payload):
            captured.append(("assistant", payload))

    async def fake_stream_agent_events(*args, **kwargs):
        yield '0:{"type":"text","data":{"content":"assistant answer"}}\n'
        yield '0:{"type":"done","data":{"metrics":{"run_id":"run-1"}}}\n'

    monkeypatch.setattr(main, "session_service", FakeSessionService(), raising=False)
    monkeypatch.setattr(main, "stream_agent_events", fake_stream_agent_events)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                    "search_mode": {"mode": "agent"},
                },
            )

    assert resp.status_code == 200
    assert captured[0][0] == "start"
    assert captured[0][1]["initial_user_message"] == "hello"
    assert captured[1][0] == "assistant"
    assert captured[1][1]["content"] == "assistant answer"


@pytest.mark.asyncio
async def test_chat_stream_persists_process_events_tools_and_sources(monkeypatch):
    captured: list[tuple[str, dict]] = []

    class FakeSessionService:
        async def start_session_run(self, **payload):
            captured.append(("start", payload))

        async def finalize_assistant_message(self, **payload):
            captured.append(("assistant", payload))

    async def fake_stream_agent_events(*args, **kwargs):
        yield '0:{"type":"thinking","data":{"text":"Analyzing request"}}\n'
        yield '0:{"type":"tool_start","data":{"name":"search_docs","toolCallId":"tool-1","args":{"query":"persistence"}}}\n'
        yield '0:{"type":"tool_result","data":{"name":"search_docs","toolCallId":"tool-1","args":{"query":"persistence"},"result":{"hits":2}}}\n'
        yield '0:{"type":"sources","data":{"items":[{"title":"Doc","url":"https://example.com/doc"}]}}\n'
        yield '0:{"type":"text","data":{"content":"assistant answer"}}\n'
        yield '0:{"type":"done","data":{"metrics":{"run_id":"run-1","duration_ms":27000}}}\n'

    monkeypatch.setattr(main, "session_service", FakeSessionService(), raising=False)
    monkeypatch.setattr(main, "stream_agent_events", fake_stream_agent_events)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
                "search_mode": {"mode": "agent"},
            },
        )

    assert resp.status_code == 200
    assert captured[1][0] == "assistant"
    assert captured[1][1]["content"] == "assistant answer"
    assert captured[1][1]["sources"] == [{"title": "Doc", "url": "https://example.com/doc"}]
    assert captured[1][1]["metrics"] == {"run_id": "run-1", "duration_ms": 27000}
    assert captured[1][1]["tool_invocations"] == [
        {
            "toolName": "search_docs",
            "toolCallId": "tool-1",
            "state": "completed",
            "args": {"query": "persistence"},
            "result": {"hits": 2},
        }
    ]
    assert [event["type"] for event in captured[1][1]["process_events"]] == ["thinking", "tool", "tool", "done"]


@pytest.mark.asyncio
async def test_chat_stream_reuses_provided_thread_id_for_follow_up_messages(monkeypatch):
    captured: list[tuple[str, dict]] = []

    class FakeSessionService:
        async def start_session_run(self, **payload):
            captured.append(("start", payload))

        async def finalize_assistant_message(self, **payload):
            captured.append(("assistant", payload))

    async def fake_stream_agent_events(*args, **kwargs):
        yield '0:{"type":"text","data":{"content":"assistant answer"}}\n'
        yield '0:{"type":"done","data":{"metrics":{"run_id":"run-1"}}}\n'

    async def fake_require_thread_owner(*_args, **_kwargs):
        return None

    monkeypatch.setattr(main, "session_service", FakeSessionService(), raising=False)
    monkeypatch.setattr(main, "stream_agent_events", fake_stream_agent_events)
    monkeypatch.setattr(main, "_require_thread_owner", fake_require_thread_owner)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat",
            json={
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                    {"role": "user", "content": "follow up"},
                ],
                "stream": True,
                "search_mode": {"mode": "agent"},
                "thread_id": "thread-existing",
            },
        )

    assert resp.status_code == 200
    assert resp.headers["x-thread-id"] == "thread-existing"
    assert captured[0][1]["thread_id"] == "thread-existing"


@pytest.mark.asyncio
async def test_chat_non_stream_persists_session_and_final_report(monkeypatch):
    captured: list[tuple[str, dict]] = []

    class FakeSessionService:
        async def start_session_run(self, **payload):
            captured.append(("start", payload))

        async def finalize_assistant_message(self, **payload):
            captured.append(("assistant", payload))

    class FakeGraph:
        async def ainvoke(self, _state, config=None):
            return {"final_report": "final answer"}

    monkeypatch.setattr(main, "session_service", FakeSessionService(), raising=False)
    monkeypatch.setattr(main, "get_agent_profile", lambda _agent_id: None)
    monkeypatch.setattr(
        main,
        "_build_initial_agent_state",
        lambda **_kwargs: {"input": "hello", "messages": []},
    )
    monkeypatch.setattr(
        main,
        "_build_agent_graph_config",
        lambda **_kwargs: {"configurable": {"thread_id": "thread-test"}},
    )
    monkeypatch.setattr(main, "research_graph", FakeGraph())

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
                "search_mode": {"mode": "agent"},
            },
        )

    assert resp.status_code == 200
    assert captured[0][0] == "start"
    assert captured[1][0] == "assistant"
    assert captured[1][1]["content"] == "final answer"
    assert captured[1][1]["status"] == "completed"


@pytest.mark.asyncio
async def test_chat_non_stream_backfills_recent_session_history_into_runtime_state(monkeypatch):
    captured: dict[str, object] = {}

    class FakeSessionService:
        async def list_messages(self, thread_id: str, *, limit: int = 50):
            captured["thread_id"] = thread_id
            captured["limit"] = limit
            return [
                {"id": "m1", "role": "user", "content": "hello"},
                {"id": "m2", "role": "assistant", "content": "world"},
            ]

        async def start_session_run(self, **payload):
            captured["start"] = payload

        async def finalize_assistant_message(self, **payload):
            captured["assistant"] = payload

    class FakeGraph:
        async def ainvoke(self, state, config=None):
            captured["messages"] = state["messages"]
            return {"final_report": "final answer"}

    async def fake_require_thread_owner(*_args, **_kwargs):
        return None

    monkeypatch.setattr(main, "session_service", FakeSessionService(), raising=False)
    monkeypatch.setattr(main, "_require_thread_owner", fake_require_thread_owner)
    monkeypatch.setattr(main, "get_agent_profile", lambda _agent_id: None)
    monkeypatch.setattr(
        main,
        "_build_agent_graph_config",
        lambda **_kwargs: {"configurable": {"thread_id": "thread-existing"}},
    )
    monkeypatch.setattr(main, "research_graph", FakeGraph())

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat",
            json={
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                    {"role": "user", "content": "follow up"},
                ],
                "stream": False,
                "search_mode": {"mode": "agent"},
                "thread_id": "thread-existing",
            },
        )

    assert resp.status_code == 200
    assert captured["thread_id"] == "thread-existing"
    assert [type(message) for message in captured["messages"]] == [HumanMessage, AIMessage, HumanMessage]
    assert [message.content for message in captured["messages"]] == ["hello", "world", "follow up"]


@pytest.mark.asyncio
async def test_interrupt_resume_stream_persists_final_assistant_message(monkeypatch):
    captured: list[tuple[str, dict]] = []

    class FakeSessionService:
        async def append_user_message(self, **payload):
            captured.append(("user", payload))

        async def finalize_assistant_message(self, **payload):
            captured.append(("assistant", payload))

    class FakeCheckpointer:
        async def aget_tuple(self, config):
            return type(
                "CheckpointTuple",
                (),
                {
                    "checkpoint": {"channel_values": {"route": "agent", "user_id": "default_user"}},
                    "metadata": {},
                    "parent_config": None,
                    "pending_writes": [],
                },
            )()

    async def fake_stream_resumed_agent_events(**kwargs):
        yield '0:{"type":"text","data":{"content":"resumed answer"}}\n'
        yield '0:{"type":"done","data":{"metrics":{"run_id":"run-resume"}}}\n'

    monkeypatch.setattr(main, "session_service", FakeSessionService(), raising=False)
    monkeypatch.setattr(main, "stream_resumed_agent_events", fake_stream_resumed_agent_events)
    monkeypatch.setattr(main, "checkpointer", FakeCheckpointer())
    async def fake_require_thread_owner(*_args, **_kwargs):
        return None

    monkeypatch.setattr(main, "_require_thread_owner", fake_require_thread_owner)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/interrupt/resume",
            json={
                "thread_id": "thread-resume",
                "payload": {"clarify_answer": "continue"},
                "stream": True,
                "search_mode": {"mode": "agent"},
            },
        )

    assert resp.status_code == 200
    assert captured[0][0] == "user"
    assert captured[0][1]["content"] == "continue"
    assert captured[1][0] == "assistant"
    assert captured[1][1]["thread_id"] == "thread-resume"
    assert captured[1][1]["content"] == "resumed answer"
