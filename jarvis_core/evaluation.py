from __future__ import annotations

import sqlite3
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List


class EvaluationStore:
    """Stores objective quality signals and produces reviewable proposals.

    It never edits or deploys code. Improvement remains a measured, human-
    approved process rather than uncontrolled self-modification.
    """

    def __init__(self, db_file: str) -> None:
        self.db_file = str(db_file)

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_file).expanduser().resolve()
        conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    passed INTEGER NOT NULL,
                    checks_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS improvement_proposals (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def record(self, session_id: str, target_type: str, target_id: str, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        import json
        normalized = []
        for check in checks:
            weight = max(0.0, float(check.get("weight", 1.0)))
            value = max(0.0, min(1.0, float(check.get("score", 0.0))))
            normalized.append({**check, "weight": weight, "score": value})
        denominator = sum(item["weight"] for item in normalized) or 1.0
        score = round(sum(item["score"] * item["weight"] for item in normalized) / denominator, 3)
        run_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO evaluation_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, session_id, target_type[:80], target_id[:160], score, int(score >= 0.7), json.dumps(normalized, ensure_ascii=False), time.time()),
            )
        return {"id": run_id, "score": score, "passed": score >= 0.7, "checks": normalized}

    def report(self, days: int = 7) -> Dict[str, Any]:
        since = time.time() - max(1, min(int(days), 90)) * 86400
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM evaluation_runs WHERE created_at >= ? ORDER BY created_at DESC LIMIT 500", (since,)).fetchall()
            proposals = conn.execute("SELECT * FROM improvement_proposals ORDER BY created_at DESC LIMIT 30").fetchall()
        scores = [float(row["score"]) for row in rows]
        return {
            "runs": len(rows),
            "pass_rate": round(sum(int(row["passed"]) for row in rows) / len(rows), 3) if rows else 0.0,
            "average_score": round(statistics.mean(scores), 3) if scores else 0.0,
            "recent": [dict(row) for row in rows[:20]],
            "proposals": [dict(row) for row in proposals],
            "automatic_code_changes": False,
        }

    def propose(self, title: str, rationale: str, evidence: List[Dict[str, Any]], risk: str = "low") -> Dict[str, Any]:
        import json
        proposal_id = str(uuid.uuid4())
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO improvement_proposals VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?)",
                (proposal_id, title[:300], rationale[:4000], json.dumps(evidence, ensure_ascii=False), risk[:30], now, now),
            )
        return {"id": proposal_id, "title": title, "rationale": rationale, "risk": risk, "status": "proposed"}
