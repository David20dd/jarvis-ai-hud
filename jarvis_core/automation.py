from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _next_due(schedule_type: str, value: str, now: Optional[float] = None) -> float:
    now = float(now or time.time())
    kind = (schedule_type or "once").lower()
    if kind == "interval":
        return now + max(60, min(int(value or "3600"), 31 * 86400))
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except Exception:
        return now + 60


class AutomationStore:
    def __init__(self, db_file: str) -> None:
        self.db_file = str(db_file)

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_file).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS automations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    schedule_value TEXT NOT NULL,
                    next_run_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_job_id TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    run_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_automations_due
                    ON automations(status, next_run_at);
                """
            )

    def create(self, session_id: str, title: str, prompt: str, schedule_type: str, schedule_value: str) -> Dict[str, Any]:
        kind = (schedule_type or "once").lower()
        if kind not in {"once", "interval"}:
            raise ValueError("schedule_type debe ser once o interval")
        item_id = str(uuid.uuid4())
        now = time.time()
        due = _next_due(kind, schedule_value, now)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO automations VALUES (?, ?, ?, ?, ?, ?, ?, 'active', '', '', 0, ?, ?)",
                (item_id, session_id, title[:300], prompt[:30000], kind, schedule_value[:120], due, now, now),
            )
        return self.get(item_id, session_id) or {}

    def get(self, item_id: str, session_id: str = "") -> Optional[Dict[str, Any]]:
        clauses, params = ["id = ?"], [item_id]
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        with self._connect() as conn:
            row = conn.execute(f"SELECT * FROM automations WHERE {' AND '.join(clauses)}", params).fetchone()
        return dict(row) if row else None

    def list(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM automations WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, max(1, min(int(limit), 200))),
            ).fetchall()
        return [dict(row) for row in rows]

    def due(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM automations WHERE status = 'active' AND next_run_at <= ? ORDER BY next_run_at LIMIT ?",
                (time.time(), max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_dispatched(self, item_id: str, job_id: str) -> None:
        item = self.get(item_id)
        if not item:
            return
        now = time.time()
        if item["schedule_type"] == "once":
            status, next_run = "completed", float(item["next_run_at"])
        else:
            status = "active"
            next_run = _next_due("interval", item["schedule_value"], now)
        with self._connect() as conn:
            conn.execute(
                "UPDATE automations SET status = ?, next_run_at = ?, last_job_id = ?, last_error = '', run_count = run_count + 1, updated_at = ? WHERE id = ?",
                (status, next_run, job_id, now, item_id),
            )

    def mark_error(self, item_id: str, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE automations SET last_error = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
                (error[:1000], time.time() + 300, time.time(), item_id),
            )

    def set_status(self, item_id: str, session_id: str, status: str) -> Optional[Dict[str, Any]]:
        if status not in {"active", "paused", "cancelled"}:
            raise ValueError("Estado de automatización no válido")
        with self._connect() as conn:
            conn.execute(
                "UPDATE automations SET status = ?, updated_at = ? WHERE id = ? AND session_id = ?",
                (status, time.time(), item_id, session_id),
            )
        return self.get(item_id, session_id)

    def delete(self, item_id: str, session_id: str) -> bool:
        with self._connect() as conn:
            return bool(conn.execute("DELETE FROM automations WHERE id = ? AND session_id = ?", (item_id, session_id)).rowcount)

    def counts(self) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) count FROM automations GROUP BY status").fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}
