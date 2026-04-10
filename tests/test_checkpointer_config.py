import importlib
import sys

import pytest
from psycopg.rows import dict_row

from agent.execution import graph
from common import memory_store as memory_store_module


@pytest.mark.asyncio
async def test_create_checkpointer_uses_langgraph_postgres_connection_settings(monkeypatch):
    captured: dict[str, object] = {}
    sentinel_async_conn = object()
    sentinel_sync_conn = object()

    class DummySaver:
        def __init__(self, conn, *, sync_conn=None):
            captured["conn"] = conn
            captured["sync_conn"] = sync_conn

        async def setup(self):
            captured["setup_called"] = True

    async def fake_async_connect(database_url, **kwargs):
        captured["database_url"] = database_url
        captured["async_kwargs"] = kwargs
        return sentinel_async_conn

    def fake_sync_connect(database_url, **kwargs):
        captured["sync_database_url"] = database_url
        captured["sync_kwargs"] = kwargs
        return sentinel_sync_conn

    monkeypatch.setattr(graph.psycopg.AsyncConnection, "connect", fake_async_connect)
    monkeypatch.setattr(graph.psycopg, "connect", fake_sync_connect)
    monkeypatch.setattr(graph, "WeaverPostgresCheckpointer", DummySaver, raising=False)

    checkpointer = await graph.create_checkpointer("postgresql://example")

    assert isinstance(checkpointer, DummySaver)
    assert captured["conn"] is sentinel_async_conn
    assert captured["sync_conn"] is sentinel_sync_conn
    assert captured["database_url"] == "postgresql://example"
    assert captured["sync_database_url"] == "postgresql://example"
    assert captured["async_kwargs"] == {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }
    assert captured["sync_kwargs"] == {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }
    assert captured["setup_called"] is True


def test_create_memory_store_uses_psycopg_connection_settings(monkeypatch):
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

    monkeypatch.setattr(memory_store_module.psycopg, "connect", fake_connect)
    monkeypatch.setattr(memory_store_module, "MemoryStore", DummyStore, raising=False)

    store = memory_store_module.create_memory_store("postgresql://store")

    assert isinstance(store, DummyStore)
    assert captured["conn"] is sentinel_conn
    assert captured["database_url"] == "postgresql://store"
    assert captured["kwargs"] == {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }
    assert captured["setup_called"] is True


def test_init_store_uses_database_url_when_backend_is_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("MEMORY_STORE_BACKEND", "memory")
    main = sys.modules.get("main") or importlib.import_module("main")

    captured: dict[str, object] = {}

    class DummyStore:
        conn = object()

    def fake_create_memory_store(database_url: str):
        captured["database_url"] = database_url
        return DummyStore()

    monkeypatch.setattr(main.settings, "memory_store_backend", "postgres")
    monkeypatch.setattr(main.settings, "database_url", "postgresql://primary")
    monkeypatch.setattr(main, "create_memory_store", fake_create_memory_store)

    store = main._init_store()

    assert isinstance(store, DummyStore)
    assert captured["database_url"] == "postgresql://primary"
