import importlib
import sys

import pytest
from psycopg.rows import dict_row

from agent.runtime import graph


@pytest.mark.asyncio
async def test_create_checkpointer_uses_langgraph_postgres_connection_settings(monkeypatch):
    captured: dict[str, object] = {}
    sentinel_conn = object()

    class DummySaver:
        def __init__(self, conn):
            captured["conn"] = conn

        async def setup(self):
            captured["setup_called"] = True

    async def fake_connect(database_url, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return sentinel_conn

    monkeypatch.setattr(graph.psycopg.AsyncConnection, "connect", fake_connect)
    monkeypatch.setattr(graph, "AsyncPostgresSaver", DummySaver)

    checkpointer = await graph.create_checkpointer("postgresql://example")

    assert isinstance(checkpointer, DummySaver)
    assert captured["conn"] is sentinel_conn
    assert captured["database_url"] == "postgresql://example"
    assert captured["kwargs"] == {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }
    assert captured["setup_called"] is True


def test_init_store_uses_langgraph_postgres_connection_settings(monkeypatch):
    captured: dict[str, object] = {}
    sentinel_conn = object()

    class DummyStore:
        def __init__(self, conn):
            captured["conn"] = conn

        def setup(self):
            captured["setup_called"] = True

    def fake_connect(database_url, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return sentinel_conn

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("MEMORY_STORE_BACKEND", "memory")
    monkeypatch.setenv("MEMORY_STORE_URL", "")
    main = sys.modules.get("main") or importlib.import_module("main")

    monkeypatch.setattr(main.settings, "memory_store_backend", "postgres")
    monkeypatch.setattr(main.settings, "memory_store_url", "postgresql://store")
    monkeypatch.setattr(main.psycopg, "connect", fake_connect)
    monkeypatch.setattr("langgraph.store.postgres.PostgresStore", DummyStore)

    store = main._init_store()

    assert isinstance(store, DummyStore)
    assert captured["conn"] is sentinel_conn
    assert captured["database_url"] == "postgresql://store"
    assert captured["kwargs"] == {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }
    assert captured["setup_called"] is True
