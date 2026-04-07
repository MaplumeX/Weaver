from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict


class StatusState(TypedDict, total=False):
    foo: str


def _make_interrupt_checkpoint(*, thread_id: str):
    # Use the same checkpointer instance as the FastAPI app so the status endpoint
    # can observe pending interrupt writes.
    from main import checkpointer

    def node(state: StatusState):
        interrupt(
            {
                "checkpoint": "status_test",
                "instruction": "Do you approve?",
                "content": "hello",
            }
        )
        return {"foo": "unreachable"}

    builder = StateGraph(StatusState)
    builder.add_node("node", node)
    builder.add_edge(START, "node")
    builder.add_edge("node", END)
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke({}, {"configurable": {"thread_id": thread_id}, "recursion_limit": 10})

@pytest.mark.asyncio
async def test_interrupt_status_uses_async_checkpointer_interface(monkeypatch):
    import main

    class AsyncOnlyCheckpointer:
        async def aget_tuple(self, config):
            assert config == {"configurable": {"thread_id": "status-async"}}
            return SimpleNamespace(
                checkpoint={"channel_values": {}},
                pending_writes=[
                    (
                        "node",
                        "__interrupt__",
                        [
                            {
                                "checkpoint": "status_async",
                                "instruction": "Do you approve?",
                                "content": "hello",
                            }
                        ],
                    )
                ],
            )

        def get_tuple(self, config):  # pragma: no cover - regression guard
            raise AssertionError("sync get_tuple should not be called")

    monkeypatch.setattr(main, "checkpointer", AsyncOnlyCheckpointer())

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/interrupt/status-async/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_interrupted"] is True
    assert data["prompts"][0]["checkpoint"] == "status_async"
