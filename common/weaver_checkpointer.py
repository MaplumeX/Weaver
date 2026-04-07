from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from langgraph.checkpoint.base import WRITES_IDX_MAP, BaseCheckpointSaver, CheckpointTuple
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from common.persistence_schema import CHECKPOINT_DDL_STATEMENTS


class WeaverPostgresCheckpointer(BaseCheckpointSaver[str]):
    def __init__(self, conn: Any, *, sync_conn: Any | None = None, serde: Any | None = None) -> None:
        super().__init__(serde=serde or JsonPlusSerializer())
        self.conn = conn
        self.sync_conn = sync_conn

    async def setup(self) -> None:
        for statement in CHECKPOINT_DDL_STATEMENTS:
            await self.conn.execute(statement)

    async def _fetchrow(self, sql: str, params: tuple[Any, ...]) -> Any:
        if hasattr(self.conn, "fetchrow"):
            return await self.conn.fetchrow(sql, params)
        cursor = await self.conn.execute(sql, params)
        return await cursor.fetchone()

    async def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[Any]:
        if hasattr(self.conn, "fetch"):
            return list(await self.conn.fetch(sql, params))
        cursor = await self.conn.execute(sql, params)
        return list(await cursor.fetchall())

    def _sync_fetchrow(self, sql: str, params: tuple[Any, ...]) -> Any:
        if self.sync_conn is None:
            raise RuntimeError("sync_conn is required for synchronous checkpoint access")
        cursor = self.sync_conn.execute(sql, params)
        return cursor.fetchone()

    def _sync_fetchall(self, sql: str, params: tuple[Any, ...]) -> list[Any]:
        if self.sync_conn is None:
            raise RuntimeError("sync_conn is required for synchronous checkpoint access")
        cursor = self.sync_conn.execute(sql, params)
        return list(cursor.fetchall())

    def _dump_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        task_id: str,
        task_path: str,
        writes: Sequence[tuple[str, Any]],
    ) -> list[tuple[Any, ...]]:
        return [
            (
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                task_id,
                task_path,
                WRITES_IDX_MAP.get(channel, write_idx),
                channel,
                *self.serde.dumps_typed(value),
            )
            for write_idx, (channel, value) in enumerate(writes)
        ]

    @staticmethod
    def _writes_sql(writes: Sequence[tuple[str, Any]]) -> str:
        base = (
            "INSERT INTO graph_checkpoint_writes "
            "(thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, write_idx, channel, value_type, value_payload) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
        )
        if all(channel in WRITES_IDX_MAP for channel, _ in writes):
            return (
                base
                + "ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx) DO UPDATE SET "
                + "channel = EXCLUDED.channel, "
                + "value_type = EXCLUDED.value_type, "
                + "value_payload = EXCLUDED.value_payload"
            )
        return (
            base
            + "ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx) DO NOTHING"
        )

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        configurable = dict(config.get("configurable", {}))
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])
        parent_checkpoint_id = str(configurable.get("checkpoint_id", "") or "") or None
        checkpoint_type, checkpoint_payload = self.serde.dumps_typed(checkpoint)
        metadata_type, metadata_payload = self.serde.dumps_typed(metadata)
        await self.conn.execute(
            "INSERT INTO graph_checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_payload, metadata_type, metadata_payload) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                parent_checkpoint_id,
                checkpoint_type,
                checkpoint_payload,
                metadata_type,
                metadata_payload,
            ),
        )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])
        query = self._writes_sql(writes)
        for params in self._dump_writes(
            thread_id,
            checkpoint_ns,
            checkpoint_id,
            task_id,
            task_path,
            writes,
        ):
            await self.conn.execute(
                query,
                params,
            )

    async def aget_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        configurable = dict((config or {}).get("configurable", {}))
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(configurable.get("checkpoint_id", "") or "")

        if checkpoint_id:
            row = await self._fetchrow(
                "SELECT * FROM graph_checkpoints WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s",
                (thread_id, checkpoint_ns, checkpoint_id),
            )
        else:
            row = await self._fetchrow(
                "SELECT * FROM graph_checkpoints WHERE thread_id = %s AND checkpoint_ns = %s "
                "ORDER BY checkpoint_id DESC LIMIT 1",
                (thread_id, checkpoint_ns),
            )

        if not row:
            return None

        writes = await self._fetchall(
            "SELECT task_id, channel, value_type, value_payload FROM graph_checkpoint_writes "
            "WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s ORDER BY task_id, write_idx",
            (thread_id, checkpoint_ns, row["checkpoint_id"]),
        )
        parent_config = None
        parent_checkpoint_id = row.get("parent_checkpoint_id")
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": row["checkpoint_id"],
                }
            },
            checkpoint=self.serde.loads_typed((row["checkpoint_type"], row["checkpoint_payload"])),
            metadata=self.serde.loads_typed((row["metadata_type"], row["metadata_payload"])),
            parent_config=parent_config,
            pending_writes=[
                (
                    str(item["task_id"]),
                    str(item["channel"]),
                    self.serde.loads_typed((item["value_type"], item["value_payload"])),
                )
                for item in writes
            ],
        )

    async def alist(
        self,
        config: dict[str, Any] | None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        configurable = dict((config or {}).get("configurable", {}))
        thread_id = str(configurable.get("thread_id", "") or "")
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        rows = await self._fetchall(
            "SELECT thread_id, checkpoint_ns, checkpoint_id FROM graph_checkpoints "
            "WHERE (%s = '' OR thread_id = %s) AND checkpoint_ns = %s "
            "ORDER BY checkpoint_id DESC LIMIT %s",
            (thread_id, thread_id, checkpoint_ns, int(limit or 100)),
        )
        for row in rows:
            checkpoint_tuple = await self.aget_tuple(
                {
                    "configurable": {
                        "thread_id": row["thread_id"],
                        "checkpoint_ns": row["checkpoint_ns"],
                        "checkpoint_id": row["checkpoint_id"],
                    }
                }
            )
            if checkpoint_tuple is not None:
                yield checkpoint_tuple

    async def adelete_thread(self, thread_id: str) -> None:
        await self.conn.execute("DELETE FROM graph_checkpoint_writes WHERE thread_id = %s", (thread_id,))
        await self.conn.execute("DELETE FROM graph_checkpoints WHERE thread_id = %s", (thread_id,))

    async def adelete(self, config: dict[str, Any]) -> None:
        thread_id = str((config or {}).get("configurable", {}).get("thread_id", "") or "")
        if thread_id:
            await self.adelete_thread(thread_id)

    def put(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        configurable = dict(config.get("configurable", {}))
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])
        parent_checkpoint_id = str(configurable.get("checkpoint_id", "") or "") or None
        checkpoint_type, checkpoint_payload = self.serde.dumps_typed(checkpoint)
        metadata_type, metadata_payload = self.serde.dumps_typed(metadata)
        self.sync_conn.execute(
            "INSERT INTO graph_checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_payload, metadata_type, metadata_payload) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                parent_checkpoint_id,
                checkpoint_type,
                checkpoint_payload,
                metadata_type,
                metadata_payload,
            ),
        )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])
        query = self._writes_sql(writes)
        for params in self._dump_writes(
            thread_id,
            checkpoint_ns,
            checkpoint_id,
            task_id,
            task_path,
            writes,
        ):
            self.sync_conn.execute(
                query,
                params,
            )

    def get_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        configurable = dict((config or {}).get("configurable", {}))
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(configurable.get("checkpoint_id", "") or "")

        if checkpoint_id:
            row = self._sync_fetchrow(
                "SELECT * FROM graph_checkpoints WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s",
                (thread_id, checkpoint_ns, checkpoint_id),
            )
        else:
            row = self._sync_fetchrow(
                "SELECT * FROM graph_checkpoints WHERE thread_id = %s AND checkpoint_ns = %s "
                "ORDER BY checkpoint_id DESC LIMIT 1",
                (thread_id, checkpoint_ns),
            )

        if not row:
            return None

        writes = self._sync_fetchall(
            "SELECT task_id, channel, value_type, value_payload FROM graph_checkpoint_writes "
            "WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s ORDER BY task_id, write_idx",
            (thread_id, checkpoint_ns, row["checkpoint_id"]),
        )
        parent_config = None
        parent_checkpoint_id = row.get("parent_checkpoint_id")
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": row["checkpoint_id"],
                }
            },
            checkpoint=self.serde.loads_typed((row["checkpoint_type"], row["checkpoint_payload"])),
            metadata=self.serde.loads_typed((row["metadata_type"], row["metadata_payload"])),
            parent_config=parent_config,
            pending_writes=[
                (
                    str(item["task_id"]),
                    str(item["channel"]),
                    self.serde.loads_typed((item["value_type"], item["value_payload"])),
                )
                for item in writes
            ],
        )

    def list(
        self,
        config: dict[str, Any] | None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[CheckpointTuple]:
        configurable = dict((config or {}).get("configurable", {}))
        thread_id = str(configurable.get("thread_id", "") or "")
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        rows = self._sync_fetchall(
            "SELECT thread_id, checkpoint_ns, checkpoint_id FROM graph_checkpoints "
            "WHERE (%s = '' OR thread_id = %s) AND checkpoint_ns = %s "
            "ORDER BY checkpoint_id DESC LIMIT %s",
            (thread_id, thread_id, checkpoint_ns, int(limit or 100)),
        )
        result: list[CheckpointTuple] = []
        for row in rows:
            checkpoint_tuple = self.get_tuple(
                {
                    "configurable": {
                        "thread_id": row["thread_id"],
                        "checkpoint_ns": row["checkpoint_ns"],
                        "checkpoint_id": row["checkpoint_id"],
                    }
                }
            )
            if checkpoint_tuple is not None:
                result.append(checkpoint_tuple)
        return result

    def delete_thread(self, thread_id: str) -> None:
        if self.sync_conn is None:
            raise RuntimeError("sync_conn is required for synchronous checkpoint deletion")
        self.sync_conn.execute("DELETE FROM graph_checkpoint_writes WHERE thread_id = %s", (thread_id,))
        self.sync_conn.execute("DELETE FROM graph_checkpoints WHERE thread_id = %s", (thread_id,))

    def delete(self, config: dict[str, Any]) -> None:
        thread_id = str((config or {}).get("configurable", {}).get("thread_id", "") or "")
        if thread_id:
            self.delete_thread(thread_id)

    async def close(self) -> None:
        if self.conn is not None and hasattr(self.conn, "close"):
            await self.conn.close()
        if self.sync_conn is not None and hasattr(self.sync_conn, "close"):
            self.sync_conn.close()
