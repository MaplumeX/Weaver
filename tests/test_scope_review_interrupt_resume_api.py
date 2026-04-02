import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

import main


class ScopeReviewState(TypedDict, total=False):
    final_report: str


def _make_scope_review_graph(*, thread_id: str):
    from main import checkpointer

    def node(state: ScopeReviewState):
        updated = interrupt(
            {
                "checkpoint": "deep_research_scope_review",
                "instruction": "Approve the scope draft or submit feedback.",
                "content": "scope version 1",
                "scope_draft": {
                    "id": "scope_test",
                    "version": 1,
                    "research_goal": "Research AI chips",
                },
                "scope_version": 1,
                "available_actions": ["approve_scope", "revise_scope"],
                "allow_direct_edit": False,
            }
        )
        action = str(updated.get("action") or "").strip().lower()
        if action == "approve_scope":
            return {"final_report": "approved v1"}
        if action == "revise_scope":
            updated = interrupt(
                {
                    "checkpoint": "deep_research_scope_review",
                    "instruction": "Approve the revised scope draft or submit more feedback.",
                    "content": "scope version 2",
                    "scope_draft": {
                        "id": "scope_test",
                        "version": 2,
                        "research_goal": "Research AI chips with revised supply chain focus",
                    },
                    "scope_version": 2,
                    "available_actions": ["approve_scope", "revise_scope"],
                    "allow_direct_edit": False,
                }
            )
            if str(updated.get("action") or "").strip().lower() == "approve_scope":
                return {"final_report": "approved v2"}
        return {}

    builder = StateGraph(ScopeReviewState)
    builder.add_node("node", node)
    builder.add_edge(START, "node")
    builder.add_edge("node", END)
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke({}, {"configurable": {"thread_id": thread_id}, "recursion_limit": 10})
    return graph


def _decode_legacy_stream_events(raw: str) -> list[dict]:
    events = []
    for line in raw.splitlines():
        if not line.startswith("0:"):
            continue
        events.append(json.loads(line[2:]))
    return events


@pytest.mark.asyncio
async def test_interrupt_resume_api_accepts_approve_scope(monkeypatch):
    thread_id = f"scope-approve-{uuid.uuid4().hex}"
    graph = _make_scope_review_graph(thread_id=thread_id)
    monkeypatch.setattr(main, "research_graph", graph)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/interrupt/resume",
            json={"thread_id": thread_id, "payload": {"action": "approve_scope"}},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "approved v1"


@pytest.mark.asyncio
async def test_interrupt_resume_api_accepts_revise_scope_and_returns_next_interrupt(monkeypatch):
    thread_id = f"scope-revise-{uuid.uuid4().hex}"
    graph = _make_scope_review_graph(thread_id=thread_id)
    monkeypatch.setattr(main, "research_graph", graph)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/interrupt/resume",
            json={
                "thread_id": thread_id,
                "payload": {
                    "action": "revise_scope",
                    "scope_feedback": "Focus more on supply chain resilience",
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "interrupted"
    assert data["interrupts"][0]["checkpoint"] == "deep_research_scope_review"
    assert data["interrupts"][0]["scope_version"] == 2


@pytest.mark.asyncio
async def test_interrupt_resume_api_rejects_direct_scope_draft_edits(monkeypatch):
    thread_id = f"scope-direct-edit-{uuid.uuid4().hex}"
    graph = _make_scope_review_graph(thread_id=thread_id)
    monkeypatch.setattr(main, "research_graph", graph)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/interrupt/resume",
            json={
                "thread_id": thread_id,
                "payload": {
                    "action": "approve_scope",
                    "scope_draft": {"research_goal": "Bypass the scope agent"},
                },
            },
        )

    assert resp.status_code == 400
    assert "direct scope draft edits" in resp.text


@pytest.mark.asyncio
async def test_interrupt_resume_api_streams_approve_scope_completion(monkeypatch):
    thread_id = f"scope-stream-approve-{uuid.uuid4().hex}"
    graph = _make_scope_review_graph(thread_id=thread_id)
    monkeypatch.setattr(main, "research_graph", graph)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/interrupt/resume",
            json={
                "thread_id": thread_id,
                "payload": {"action": "approve_scope"},
                "stream": True,
            },
        )

    assert resp.status_code == 200
    events = _decode_legacy_stream_events((await resp.aread()).decode())
    event_types = [event["type"] for event in events]
    assert "status" in event_types
    assert "completion" in event_types
    assert event_types[-1] == "done"
    completion = next(event for event in events if event["type"] == "completion")
    assert completion["data"]["content"] == "approved v1"


@pytest.mark.asyncio
async def test_interrupt_resume_api_streams_revise_scope_interrupt(monkeypatch):
    thread_id = f"scope-stream-revise-{uuid.uuid4().hex}"
    graph = _make_scope_review_graph(thread_id=thread_id)
    monkeypatch.setattr(main, "research_graph", graph)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/interrupt/resume",
            json={
                "thread_id": thread_id,
                "payload": {
                    "action": "revise_scope",
                    "scope_feedback": "Focus more on supply chain resilience",
                },
                "stream": True,
            },
        )

    assert resp.status_code == 200
    events = _decode_legacy_stream_events((await resp.aread()).decode())
    event_types = [event["type"] for event in events]
    assert "status" in event_types
    assert event_types[-1] == "interrupt"
    interrupt_event = next(event for event in events if event["type"] == "interrupt")
    assert interrupt_event["data"]["prompts"][0]["checkpoint"] == "deep_research_scope_review"
    assert interrupt_event["data"]["prompts"][0]["scope_version"] == 2
