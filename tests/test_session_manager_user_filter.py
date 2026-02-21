from __future__ import annotations

from common.session_manager import SessionManager


class _FakeCheckpointer:
    def __init__(self, storage):
        self.storage = storage


class _Cfg:
    def __init__(self, thread_id: str):
        self.configurable = {"thread_id": thread_id}

    def __hash__(self) -> int:  # pragma: no cover
        return hash(self.configurable["thread_id"])

    def __eq__(self, other: object) -> bool:  # pragma: no cover
        return isinstance(other, _Cfg) and other.configurable == self.configurable


def test_list_sessions_can_filter_by_user_id():
    checkpointer = _FakeCheckpointer(
        storage={
            _Cfg("thread_alice"): {
                "channel_values": {
                    "user_id": "alice",
                    "input": "hello",
                    "route": "direct",
                }
            },
            _Cfg("thread_bob"): {
                "channel_values": {
                    "user_id": "bob",
                    "input": "hi",
                    "route": "direct",
                }
            },
        }
    )

    manager = SessionManager(checkpointer)
    sessions = manager.list_sessions(limit=50, user_id_filter="alice")

    assert [s.thread_id for s in sessions] == ["thread_alice"]
