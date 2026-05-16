"""Persistent task queue backed by SQLite.

Originator lifecycle:  queued → sent → completed | failed
Receiver lifecycle:    received → running → completed | failed
Retry:                 failed → queued
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_DEFAULT_DB = Path.home() / ".config" / "agentrelay" / "tasks.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id                  TEXT PRIMARY KEY,
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL,
    source_node         TEXT NOT NULL,
    source_agent        TEXT,
    target_node         TEXT NOT NULL,
    target_agent        TEXT NOT NULL,
    message             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'queued',
    permission_profile  TEXT,
    session_id          TEXT,
    originator_task_id  TEXT,
    reply_to            TEXT,
    result              TEXT,
    error               TEXT,
    retry_count         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tasks_status  ON tasks(status);
CREATE INDEX IF NOT EXISTS tasks_target  ON tasks(target_node, target_agent);
CREATE INDEX IF NOT EXISTS tasks_created ON tasks(created_at);
"""

# Columns added after initial release — added via _migrate() for existing DBs
_MIGRATE_COLS: dict[str, str] = {
    "originator_task_id": "TEXT",
    "reply_to": "TEXT",
}

# Valid forward transitions
_TRANSITIONS: dict[str, set[str]] = {
    "queued":    {"sent", "failed"},
    "sent":      {"completed", "failed"},   # originator: callback arrives
    "received":  {"running", "failed"},     # receiver: PTY launched
    "running":   {"completed", "failed"},
    "completed": set(),
    "failed":    {"queued"},                # retry
}

TERMINAL_STATUSES = frozenset({"completed", "failed"})


class TaskQueue:
    """Thread-safe, async-friendly wrapper around a SQLite task store."""

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._path = db_path
        self._write_lock = asyncio.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _migrate(self, conn: sqlite3.Connection) -> None:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        for col, coltype in _MIGRATE_COLS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {coltype}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if d.get("result"):
            try:
                d["result"] = json.loads(d["result"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        source_node: str,
        target_node: str,
        target_agent: str,
        message: str,
        source_agent: str | None = None,
        permission_profile: str | None = None,
        status: str = "queued",
        originator_task_id: str | None = None,
        reply_to: str | None = None,
    ) -> str:
        """Insert a new task and return its ID. Use status='received' on the receiver side."""
        task_id = uuid.uuid4().hex
        now = time.time()
        loop = asyncio.get_running_loop()
        async with self._write_lock:
            await loop.run_in_executor(
                None, self._insert,
                task_id, now, source_node, source_agent,
                target_node, target_agent, message, permission_profile,
                status, originator_task_id, reply_to,
            )
        return task_id

    def _insert(
        self, task_id: str, now: float,
        source_node: str, source_agent: str | None,
        target_node: str, target_agent: str, message: str,
        permission_profile: str | None,
        status: str,
        originator_task_id: str | None,
        reply_to: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO tasks
                       (id, created_at, updated_at, source_node, source_agent,
                        target_node, target_agent, message, status,
                        permission_profile, originator_task_id, reply_to)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, now, now, source_node, source_agent,
                 target_node, target_agent, message, status,
                 permission_profile, originator_task_id, reply_to),
            )

    async def update_status(
        self,
        task_id: str,
        status: str,
        *,
        result: Any = None,
        error: str | None = None,
        session_id: str | None = None,
    ) -> bool:
        """Advance a task to a new status. Returns False if the transition is invalid."""
        loop = asyncio.get_running_loop()
        async with self._write_lock:
            return await loop.run_in_executor(
                None, self._do_update, task_id, status, result, error, session_id)

    def _do_update(
        self, task_id: str, status: str,
        result: Any, error: str | None, session_id: str | None,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if not row:
                return False
            if status not in _TRANSITIONS.get(row["status"], set()):
                return False
            result_json = json.dumps(result) if result is not None else None
            conn.execute(
                """UPDATE tasks
                   SET status=?, updated_at=?, result=?, error=?,
                       session_id=COALESCE(?, session_id)
                   WHERE id=?""",
                (status, time.time(), result_json, error, session_id, task_id),
            )
        return True

    async def ack(self, task_id: str, *, session_id: str | None = None) -> bool:
        """Shorthand: advance queued/sent → acked."""
        return await self.update_status(task_id, "acked", session_id=session_id)

    async def mark_running(self, task_id: str, session_id: str) -> bool:
        """Shorthand: advance acked → running and record the PTY session_id."""
        return await self.update_status(task_id, "running", session_id=session_id)

    async def complete(self, task_id: str, result: Any = None) -> bool:
        return await self.update_status(task_id, "completed", result=result)

    async def fail(self, task_id: str, error: str) -> bool:
        return await self.update_status(task_id, "failed", error=error)

    async def requeue(self, task_id: str) -> bool:
        """Move a failed task back to queued for retry."""
        loop = asyncio.get_running_loop()
        async with self._write_lock:
            return await loop.run_in_executor(None, self._do_requeue, task_id)

    def _do_requeue(self, task_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if not row or row["status"] != "failed":
                return False
            conn.execute(
                """UPDATE tasks
                   SET status='queued', updated_at=?, error=NULL,
                       retry_count=retry_count+1
                   WHERE id=?""",
                (time.time(), task_id),
            )
        return True

    async def get(self, task_id: str) -> dict[str, Any] | None:
        loop = asyncio.get_running_loop()
        row = await loop.run_in_executor(None, self._fetch_one, task_id)
        return row

    def _fetch_one(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
        return self._to_dict(row) if row else None

    async def list_tasks(
        self,
        *,
        status: str | None = None,
        target_node: str | None = None,
        source_node: str | None = None,
        limit: int = 100,
        since: float = 0.0,
    ) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._fetch_many, status, target_node, source_node, limit, since)

    def _fetch_many(
        self,
        status: str | None,
        target_node: str | None,
        source_node: str | None,
        limit: int,
        since: float,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = ["created_at > ?"]
        params: list[Any] = [since]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if target_node:
            clauses.append("target_node = ?")
            params.append(target_node)
        if source_node:
            clauses.append("source_node = ?")
            params.append(source_node)
        params.append(limit)
        sql = (
            "SELECT * FROM tasks WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._to_dict(r) for r in rows]

    async def pending_for_peer(self, target_node: str) -> list[dict[str, Any]]:
        """Return queued tasks destined for a peer (useful when it comes back online)."""
        return await self.list_tasks(status="queued", target_node=target_node)

    async def prune(self, older_than_days: int = 30) -> int:
        """Delete terminal-state tasks older than N days. Returns count removed."""
        cutoff = time.time() - older_than_days * 86400
        loop = asyncio.get_running_loop()
        async with self._write_lock:
            return await loop.run_in_executor(None, self._do_prune, cutoff)

    def _do_prune(self, cutoff: float) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM tasks WHERE status IN ('completed','failed') AND updated_at < ?",
                (cutoff,),
            )
        return cur.rowcount
