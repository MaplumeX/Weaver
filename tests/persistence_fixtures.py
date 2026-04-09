from __future__ import annotations


class RecordingAsyncConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.rows: dict[str, list[dict[str, object]]] = {
            "graph_checkpoints": [],
            "graph_checkpoint_writes": [],
            "sessions": [],
            "session_messages": [],
        }

    async def execute(self, sql: str, params: tuple | None = None):
        self.executed.append((sql, params))
        if params is None:
            return
        if "INSERT INTO graph_checkpoints" in sql:
            self.rows["graph_checkpoints"].append(
                {
                    "thread_id": params[0],
                    "checkpoint_ns": params[1],
                    "checkpoint_id": params[2],
                    "parent_checkpoint_id": params[3],
                    "checkpoint_type": params[4],
                    "checkpoint_payload": params[5],
                    "metadata_type": params[6],
                    "metadata_payload": params[7],
                }
            )
        elif "INSERT INTO graph_checkpoint_writes" in sql:
            row = {
                "thread_id": params[0],
                "checkpoint_ns": params[1],
                "checkpoint_id": params[2],
                "task_id": params[3],
                "task_path": params[4],
                "write_idx": params[5],
                "channel": params[6],
                "value_type": params[7],
                "value_payload": params[8],
            }
            duplicate = next(
                (
                    item
                    for item in self.rows["graph_checkpoint_writes"]
                    if item["thread_id"] == row["thread_id"]
                    and item["checkpoint_ns"] == row["checkpoint_ns"]
                    and item["checkpoint_id"] == row["checkpoint_id"]
                    and item["task_id"] == row["task_id"]
                    and item["write_idx"] == row["write_idx"]
                ),
                None,
            )
            if duplicate is None:
                self.rows["graph_checkpoint_writes"].append(row)
            elif "DO UPDATE SET" in sql:
                duplicate.update(row)
        elif "DELETE FROM graph_checkpoint_writes" in sql:
            thread_id = params[0]
            self.rows["graph_checkpoint_writes"] = [
                item
                for item in self.rows["graph_checkpoint_writes"]
                if item["thread_id"] != thread_id
            ]
        elif "DELETE FROM graph_checkpoints" in sql:
            thread_id = params[0]
            self.rows["graph_checkpoints"] = [
                item for item in self.rows["graph_checkpoints"] if item["thread_id"] != thread_id
            ]
        elif "INSERT INTO sessions" in sql:
            self.rows["sessions"].append(
                {
                    "thread_id": params[0],
                    "user_id": params[1],
                    "title": params[2],
                    "route": params[3],
                    "status": params[4],
                    "summary": "",
                    "context_snapshot": {},
                    "is_pinned": False,
                    "tags": [],
                    "created_at": "2026-04-06T00:00:00Z",
                    "updated_at": "2026-04-06T00:00:00Z",
                }
            )
        elif "INSERT INTO session_messages" in sql:
            thread_id = params[1]
            next_seq = max(
                [
                    int(item["seq"])
                    for item in self.rows["session_messages"]
                    if item["thread_id"] == thread_id
                ],
                default=0,
            ) + 1
            attachments = []
            sources = []
            tool_invocations = []
            process_events = []
            metrics = {}
            created_at = params[5]
            completed_at = None
            if len(params) >= 12:
                attachments = getattr(params[5], "obj", params[5])
                sources = getattr(params[6], "obj", params[6])
                tool_invocations = getattr(params[7], "obj", params[7])
                process_events = getattr(params[8], "obj", params[8])
                metrics = getattr(params[9], "obj", params[9])
                created_at = params[10]
                completed_at = params[11]
            self.rows["session_messages"].append(
                {
                    "id": str(params[0]),
                    "thread_id": thread_id,
                    "seq": next_seq,
                    "role": params[3],
                    "content": params[4],
                    "attachments": attachments,
                    "sources": sources,
                    "tool_invocations": tool_invocations,
                    "process_events": process_events,
                    "metrics": metrics,
                    "created_at": created_at,
                    "completed_at": completed_at,
                }
            )
        elif "UPDATE sessions" in sql:
            thread_id = params[-1]
            session = next(
                (item for item in self.rows["sessions"] if item["thread_id"] == thread_id),
                None,
            )
            if session is not None:
                assignments = [
                    part.strip()
                    for part in sql.split("SET", 1)[1].split("WHERE", 1)[0].split(",")
                ]
                for index, assignment in enumerate(assignments):
                    field = assignment.split("=", 1)[0].strip()
                    value = params[index]
                    if field == "status":
                        session["status"] = value
                    elif field == "summary":
                        session["summary"] = value
                    elif field == "title":
                        session["title"] = value
                    elif field == "is_pinned":
                        session["is_pinned"] = value
                    elif field == "tags":
                        session["tags"] = getattr(value, "obj", value)
                    elif field == "route":
                        session["route"] = value
                    elif field == "context_snapshot":
                        session["context_snapshot"] = getattr(value, "obj", value)
                    elif field == "updated_at":
                        session["updated_at"] = value

    async def fetchrow(self, sql: str, params: tuple | None = None):
        params = params or ()
        if "graph_checkpoints" not in sql:
            if "FROM sessions" in sql:
                return next(
                    (row for row in self.rows["sessions"] if row["thread_id"] == params[0]),
                    None,
                )
            return None
        if "checkpoint_id = %s" in sql:
            return next(
                (
                    row
                    for row in self.rows["graph_checkpoints"]
                    if row["thread_id"] == params[0]
                    and row["checkpoint_ns"] == params[1]
                    and row["checkpoint_id"] == params[2]
                ),
                None,
            )
        candidates = [
            row
            for row in self.rows["graph_checkpoints"]
            if row["thread_id"] == params[0] and row["checkpoint_ns"] == params[1]
        ]
        if "ORDER BY checkpoint_id DESC" in sql:
            ordered = sorted(candidates, key=lambda row: str(row["checkpoint_id"]), reverse=True)
            return ordered[0] if ordered else None
        return candidates[-1] if candidates else None

    async def fetch(self, sql: str, params: tuple | None = None):
        params = params or ()
        if "graph_checkpoint_writes" in sql:
            return [
                row
                for row in self.rows["graph_checkpoint_writes"]
                if row["thread_id"] == params[0]
                and row["checkpoint_ns"] == params[1]
                and row["checkpoint_id"] == params[2]
            ]
        if "FROM session_messages" in sql:
            rows = [
                row
                for row in self.rows["session_messages"]
                if row["thread_id"] == params[0]
            ]
            if "AND seq > %s" in sql:
                rows = [row for row in rows if int(row["seq"]) > int(params[1])]
                rows = sorted(rows, key=lambda row: int(row["seq"]))
                if len(params) > 2:
                    rows = rows[: int(params[2])]
                return rows
            if "ORDER BY seq DESC" in sql:
                rows = sorted(rows, key=lambda row: int(row["seq"]), reverse=True)
                if len(params) > 1:
                    rows = rows[: int(params[1])]
                return rows
            return rows
        if "FROM sessions" in sql:
            user_id = params[0]
            return [row for row in self.rows["sessions"] if row["user_id"] == user_id]
        if "graph_checkpoints" in sql:
            thread_id = params[0]
            checkpoint_ns = params[2]
            limit = int(params[3])
            filtered = [
                row
                for row in self.rows["graph_checkpoints"]
                if (not thread_id or row["thread_id"] == thread_id)
                and row["checkpoint_ns"] == checkpoint_ns
            ]
            if "ORDER BY checkpoint_id DESC" in sql:
                return sorted(
                    filtered,
                    key=lambda row: str(row["checkpoint_id"]),
                    reverse=True,
                )[:limit]
            return list(reversed(filtered))[:limit]
        return []

    async def fetchval(self, sql: str, params: tuple | None = None):
        params = params or ()
        if "graph_checkpoints" in sql:
            return sum(1 for row in self.rows["graph_checkpoints"] if row["thread_id"] == params[0])
        return 0


def build_fake_pg_conn() -> RecordingAsyncConn:
    return RecordingAsyncConn()
