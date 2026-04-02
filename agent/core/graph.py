"""Compatibility shims for graph creation during the runtime migration."""

from __future__ import annotations

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row

from agent.runtime.graph import create_research_graph, export_graph_mermaid

__all__ = [
    "create_checkpointer",
    "create_research_graph",
    "export_graph_mermaid",
    "PostgresSaver",
    "psycopg",
]


def create_checkpointer(database_url: str):
    """
    Create a PostgreSQL checkpointer for state persistence.

    This remains here as a temporary compatibility shim because tests and
    existing callers still patch `agent.core.graph` directly.
    """
    if not database_url:
        raise ValueError("database_url is required to initialize the Postgres checkpointer.")

    try:
        conn = psycopg.connect(
            database_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Postgres for checkpointer: {e}") from e

    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return checkpointer
