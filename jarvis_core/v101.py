from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from .v82 import DataFoundation
from .v100 import V100_STAGES


V101_VERSION = 101
V101_STAGES: List[Dict[str, Any]] = [
    *V100_STAGES,
    {
        "version": 101,
        "name": "Reliability & Self-Improvement",
        "capabilities": [
            "diagnóstico persistente",
            "agrupación de errores",
            "detección de regresiones",
            "propuestas verificables",
            "aprobación humana",
            "rollback planificado",
        ],
    },
]

ALLOWED_SEVERITIES = {"info", "low", "medium", "high", "critical"}
ALLOWED_ISSUE_STATES = {"open", "monitoring", "resolved", "ignored"}
ALLOWED_PROPOSAL_STATES = {"proposed", "reviewed", "approved", "rejected"}


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _safe_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


class ReliabilityCore:
    """Persistent reliability signals and supervised improvement proposals.

    The component may observe, classify and propose. It deliberately cannot edit
    source code, change credentials or deploy production.
    """

    def __init__(self, foundation: DataFoundation):
        self.foundation = foundation
        self._schema_ready = False

    @property
    def driver(self) -> str:
        return self.foundation.driver

    def _p(self) -> str:
        return "%s" if self.driver == "postgresql" else "?"

    def init_schema(self) -> None:
        if self.driver == "postgresql":
            statements = [
                """CREATE TABLE IF NOT EXISTS v101_issues (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'open',
                    context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    first_seen DOUBLE PRECISION NOT NULL,
                    last_seen DOUBLE PRECISION NOT NULL,
                    UNIQUE(session_id, fingerprint)
                )""",
                """CREATE INDEX IF NOT EXISTS idx_v101_issues_session
                    ON v101_issues(session_id, status, last_seen DESC)""",
                """CREATE TABLE IF NOT EXISTS v101_quality_runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    score DOUBLE PRECISION NOT NULL,
                    status TEXT NOT NULL,
                    checks_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at DOUBLE PRECISION NOT NULL
                )""",
                """CREATE INDEX IF NOT EXISTS idx_v101_quality_session
                    ON v101_quality_runs(session_id, created_at DESC)""",
                """CREATE TABLE IF NOT EXISTS v101_proposals (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    issue_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    change_plan_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    test_plan_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    risk TEXT NOT NULL DEFAULT 'low',
                    status TEXT NOT NULL DEFAULT 'proposed',
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                )""",
                """CREATE INDEX IF NOT EXISTS idx_v101_proposals_session
                    ON v101_proposals(session_id, status, created_at DESC)""",
                """INSERT INTO v82_schema_migrations(version, applied_at)
                    VALUES (101, EXTRACT(EPOCH FROM NOW())) ON CONFLICT(version) DO NOTHING""",
            ]
            with self.foundation.connection() as conn:
                for statement in statements:
                    conn.execute(statement)
        else:
            with self.foundation.connection() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS v101_issues (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        category TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        detail TEXT NOT NULL DEFAULT '',
                        occurrences INTEGER NOT NULL DEFAULT 1,
                        status TEXT NOT NULL DEFAULT 'open',
                        context_json TEXT NOT NULL DEFAULT '{}',
                        first_seen REAL NOT NULL,
                        last_seen REAL NOT NULL,
                        UNIQUE(session_id, fingerprint)
                    );
                    CREATE INDEX IF NOT EXISTS idx_v101_issues_session
                        ON v101_issues(session_id, status, last_seen DESC);
                    CREATE TABLE IF NOT EXISTS v101_quality_runs (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        score REAL NOT NULL,
                        status TEXT NOT NULL,
                        checks_json TEXT NOT NULL DEFAULT '{}',
                        created_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_v101_quality_session
                        ON v101_quality_runs(session_id, created_at DESC);
                    CREATE TABLE IF NOT EXISTS v101_proposals (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        issue_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        rationale TEXT NOT NULL,
                        change_plan_json TEXT NOT NULL DEFAULT '[]',
                        test_plan_json TEXT NOT NULL DEFAULT '[]',
                        risk TEXT NOT NULL DEFAULT 'low',
                        status TEXT NOT NULL DEFAULT 'proposed',
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_v101_proposals_session
                        ON v101_proposals(session_id, status, created_at DESC);
                    INSERT OR IGNORE INTO v82_schema_migrations(version, applied_at)
                        VALUES (101, strftime('%s','now'));
                    """
                )
        self._schema_ready = True

    def _ensure(self) -> None:
        if not self._schema_ready:
            self.init_schema()

    @staticmethod
    def fingerprint(category: str, title: str, detail: str = "") -> str:
        normalized = "|".join(
            [
                _clean(category, 80).lower(),
                _clean(title, 240).lower(),
                re.sub(r"\b\d+(?:\.\d+)?\b", "#", _clean(detail, 800).lower()),
            ]
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]

    def record_issue(
        self,
        session_id: str,
        *,
        category: str,
        title: str,
        detail: str = "",
        severity: str = "medium",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._ensure()
        clean_category = _clean(category, 80).lower() or "runtime"
        clean_title = _clean(title, 300) or "Incidencia sin título"
        clean_detail = _clean(detail, 4000)
        clean_severity = _clean(severity, 20).lower()
        if clean_severity not in ALLOWED_SEVERITIES:
            clean_severity = "medium"
        issue_id = str(uuid.uuid4())
        fingerprint = self.fingerprint(clean_category, clean_title, clean_detail)
        now = time.time()
        p = self._p()
        payload = (
            issue_id,
            session_id,
            fingerprint,
            clean_category,
            clean_severity,
            clean_title,
            clean_detail,
            1,
            "open",
            self.foundation._json_value(context or {}),
            now,
            now,
        )
        with self.foundation.connection() as conn:
            conn.execute(
                f"""INSERT INTO v101_issues(
                    id,session_id,fingerprint,category,severity,title,detail,
                    occurrences,status,context_json,first_seen,last_seen)
                    VALUES ({','.join([p] * 12)})
                    ON CONFLICT(session_id,fingerprint) DO UPDATE SET
                    occurrences=v101_issues.occurrences+1,
                    severity=excluded.severity,
                    detail=excluded.detail,
                    context_json=excluded.context_json,
                    status=CASE WHEN v101_issues.status='resolved' THEN 'monitoring'
                                ELSE v101_issues.status END,
                    last_seen=excluded.last_seen""",
                payload,
            )
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"SELECT * FROM v101_issues WHERE session_id={p} AND fingerprint={p}",
                    (session_id, fingerprint),
                )
            )
        return self._normalize_issue(rows[0]) if rows else {}

    def _normalize_issue(self, row: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(row)
        item["context"] = _safe_json(item.pop("context_json", {}), {})
        item["occurrences"] = int(item.get("occurrences") or 0)
        return item

    def list_issues(
        self,
        session_id: str,
        *,
        status: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        self._ensure()
        p = self._p()
        clauses = [f"session_id={p}"]
        values: List[Any] = [session_id]
        if status:
            clean_status = _clean(status, 20).lower()
            if clean_status not in ALLOWED_ISSUE_STATES:
                raise ValueError("Estado de incidencia no permitido.")
            clauses.append(f"status={p}")
            values.append(clean_status)
        values.append(max(1, min(int(limit), 300)))
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT * FROM v101_issues WHERE {' AND '.join(clauses)}
                        ORDER BY CASE severity
                            WHEN 'critical' THEN 5 WHEN 'high' THEN 4
                            WHEN 'medium' THEN 3 WHEN 'low' THEN 2 ELSE 1 END DESC,
                            last_seen DESC LIMIT {p}""",
                    tuple(values),
                )
            )
        return [self._normalize_issue(row) for row in rows]

    def update_issue(self, session_id: str, issue_id: str, status: str) -> Dict[str, Any]:
        clean_status = _clean(status, 20).lower()
        if clean_status not in ALLOWED_ISSUE_STATES:
            raise ValueError("Estado de incidencia no permitido.")
        p = self._p()
        with self.foundation.connection() as conn:
            cursor = conn.execute(
                f"UPDATE v101_issues SET status={p},last_seen={p} WHERE id={p} AND session_id={p}",
                (clean_status, time.time(), issue_id, session_id),
            )
            if not cursor.rowcount:
                raise KeyError("Incidencia no encontrada.")
            rows = self.foundation._dict_rows(
                conn.execute(f"SELECT * FROM v101_issues WHERE id={p} AND session_id={p}", (issue_id, session_id))
            )
        return self._normalize_issue(rows[0])

    def record_quality_run(
        self,
        session_id: str,
        checks: Dict[str, Any],
    ) -> Dict[str, Any]:
        self._ensure()
        normalized: Dict[str, Dict[str, Any]] = {}
        for name, value in (checks or {}).items():
            if isinstance(value, dict):
                ok = bool(value.get("ok"))
                detail = _clean(value.get("detail", ""), 1000)
            else:
                ok = bool(value)
                detail = ""
            normalized[_clean(name, 100) or "check"] = {"ok": ok, "detail": detail}
        total = len(normalized)
        passed = sum(1 for value in normalized.values() if value["ok"])
        score = round(passed / total, 4) if total else 0.0
        status = "healthy" if score >= 0.95 else "degraded" if score >= 0.7 else "critical"
        run_id = str(uuid.uuid4())
        now = time.time()
        p = self._p()
        with self.foundation.connection() as conn:
            conn.execute(
                f"""INSERT INTO v101_quality_runs(id,session_id,score,status,checks_json,created_at)
                    VALUES ({','.join([p] * 6)})""",
                (run_id, session_id, score, status, self.foundation._json_value(normalized), now),
            )
        for name, value in normalized.items():
            if not value["ok"]:
                self.record_issue(
                    session_id,
                    category="quality_check",
                    title=f"Falla de control: {name}",
                    detail=value["detail"],
                    severity="high" if status == "critical" else "medium",
                    context={"run_id": run_id, "check": name},
                )
        return {
            "id": run_id,
            "score": score,
            "status": status,
            "passed": passed,
            "total": total,
            "checks": normalized,
            "created_at": now,
        }

    def quality_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self._ensure()
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT * FROM v101_quality_runs WHERE session_id={p}
                        ORDER BY created_at DESC LIMIT {p}""",
                    (session_id, max(1, min(int(limit), 100))),
                )
            )
        result = []
        for row in rows:
            item = dict(row)
            item["checks"] = _safe_json(item.pop("checks_json", {}), {})
            result.append(item)
        return result

    @staticmethod
    def _proposal_plan(category: str) -> Dict[str, Any]:
        plans = {
            "provider": {
                "changes": [
                    "Ajustar timeout, reintentos y circuit breaker de la ruta afectada.",
                    "Reordenar el fallback usando telemetría de éxito y latencia.",
                    "Conservar herramientas locales cuando todos los proveedores fallen.",
                ],
                "tests": ["Simular 429, timeout y 5xx.", "Confirmar fallback y cero respuestas silenciosas."],
                "risk": "medium",
            },
            "latency": {
                "changes": [
                    "Reducir trabajo en el camino crítico y reutilizar caché.",
                    "Mover operaciones prolongadas a trabajos con checkpoints.",
                ],
                "tests": ["Medir p50 y p95.", "Ejecutar carga concurrente y verificar límites."],
                "risk": "low",
            },
            "frontend": {
                "changes": [
                    "Reproducir la excepción con una prueba E2E.",
                    "Añadir un estado de error visible y conservar la entrada del usuario.",
                ],
                "tests": ["Validar consola limpia.", "Comparar escritorio, tableta y móvil."],
                "risk": "low",
            },
            "quality_check": {
                "changes": [
                    "Aislar el componente que no superó el control.",
                    "Crear una prueba de regresión antes de modificar la implementación.",
                ],
                "tests": ["Repetir el control fallido.", "Ejecutar la suite completa y rollback simulado."],
                "risk": "medium",
            },
        }
        return plans.get(
            category,
            {
                "changes": ["Reproducir el problema de forma determinista.", "Aplicar el cambio mínimo verificable."],
                "tests": ["Añadir prueba de regresión.", "Ejecutar suite completa y diagnóstico."],
                "risk": "low",
            },
        )

    def create_proposal(self, session_id: str, issue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self._ensure()
        issue_id = str(issue.get("id") or "")
        if not issue_id:
            return None
        p = self._p()
        with self.foundation.connection() as conn:
            existing = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT * FROM v101_proposals
                        WHERE session_id={p} AND issue_id={p}
                        AND status IN ('proposed','reviewed','approved')
                        ORDER BY created_at DESC LIMIT 1""",
                    (session_id, issue_id),
                )
            )
        if existing:
            return self._normalize_proposal(existing[0])
        category = str(issue.get("category") or "runtime")
        plan = self._proposal_plan(category)
        now = time.time()
        proposal_id = str(uuid.uuid4())
        title = f"Corregir: {_clean(issue.get('title'), 240)}"
        rationale = (
            f"JARVIS detectó esta incidencia {int(issue.get('occurrences') or 1)} "
            "vez/veces. La propuesta prepara cambios y pruebas, pero no modifica producción."
        )
        with self.foundation.connection() as conn:
            conn.execute(
                f"""INSERT INTO v101_proposals(
                    id,session_id,issue_id,title,rationale,change_plan_json,
                    test_plan_json,risk,status,created_at,updated_at)
                    VALUES ({','.join([p] * 11)})""",
                (
                    proposal_id,
                    session_id,
                    issue_id,
                    title,
                    rationale,
                    self.foundation._json_value(plan["changes"]),
                    self.foundation._json_value(plan["tests"]),
                    plan["risk"],
                    "proposed",
                    now,
                    now,
                ),
            )
        return self.get_proposal(session_id, proposal_id)

    def _normalize_proposal(self, row: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(row)
        item["change_plan"] = _safe_json(item.pop("change_plan_json", []), [])
        item["test_plan"] = _safe_json(item.pop("test_plan_json", []), [])
        return item

    def get_proposal(self, session_id: str, proposal_id: str) -> Optional[Dict[str, Any]]:
        self._ensure()
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"SELECT * FROM v101_proposals WHERE id={p} AND session_id={p}",
                    (proposal_id, session_id),
                )
            )
        return self._normalize_proposal(rows[0]) if rows else None

    def list_proposals(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        self._ensure()
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT * FROM v101_proposals WHERE session_id={p}
                        ORDER BY created_at DESC LIMIT {p}""",
                    (session_id, max(1, min(int(limit), 200))),
                )
            )
        return [self._normalize_proposal(row) for row in rows]

    def review_proposal(self, session_id: str, proposal_id: str, status: str) -> Dict[str, Any]:
        clean_status = _clean(status, 20).lower()
        if clean_status not in ALLOWED_PROPOSAL_STATES - {"proposed"}:
            raise ValueError("Decisión de propuesta no permitida.")
        p = self._p()
        with self.foundation.connection() as conn:
            cursor = conn.execute(
                f"""UPDATE v101_proposals SET status={p},updated_at={p}
                    WHERE id={p} AND session_id={p}""",
                (clean_status, time.time(), proposal_id, session_id),
            )
        if not cursor.rowcount:
            raise KeyError("Propuesta no encontrada.")
        return self.get_proposal(session_id, proposal_id) or {}

    def analyze(
        self,
        session_id: str,
        *,
        operations: Iterable[Dict[str, Any]],
        recent: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        detected: List[Dict[str, Any]] = []
        for operation in operations:
            requests = max(1, int(operation.get("requests") or 0))
            failed = int(operation.get("failed") or 0)
            average_ms = float(operation.get("average_ms") or 0)
            name = _clean(operation.get("operation"), 180) or "operación"
            if failed / requests >= 0.1 and failed >= 2:
                detected.append(
                    self.record_issue(
                        session_id,
                        category="provider" if "provider" in name or "chat" in name else "runtime",
                        title=f"Tasa de error elevada en {name}",
                        detail=f"{failed} fallos en {requests} solicitudes.",
                        severity="high" if failed / requests >= 0.3 else "medium",
                        context={"operation": name, "requests": requests, "failed": failed},
                    )
                )
            if average_ms >= 8000 and requests >= 2:
                detected.append(
                    self.record_issue(
                        session_id,
                        category="latency",
                        title=f"Latencia elevada en {name}",
                        detail=f"Promedio observado: {round(average_ms)} ms.",
                        severity="medium",
                        context={"operation": name, "average_ms": average_ms},
                    )
                )
        for event in list(recent)[:30]:
            if str(event.get("status") or "") not in {"error", "timeout"}:
                continue
            name = _clean(event.get("operation"), 180) or "operación"
            detected.append(
                self.record_issue(
                    session_id,
                    category="frontend" if name.startswith("frontend:") else "provider" if "provider" in name else "runtime",
                    title=f"Error reciente en {name}",
                    detail=_clean(event.get("detail"), 1500),
                    severity="medium",
                    context={"operation": name, "status": event.get("status")},
                )
            )
        unique = {str(item.get("id")): item for item in detected if item.get("id")}
        proposals = [self.create_proposal(session_id, issue) for issue in unique.values()]
        return {
            "issues_detected": list(unique.values()),
            "proposals": [item for item in proposals if item],
            "guardrails": {
                "can_modify_source": False,
                "can_change_secrets": False,
                "can_deploy": False,
                "requires_human_approval": True,
            },
        }

    def status(self, session_id: str = "default_session") -> Dict[str, Any]:
        try:
            self._ensure()
            p = self._p()
            with self.foundation.connection() as conn:
                issue_rows = self.foundation._dict_rows(
                    conn.execute(
                        f"""SELECT status,COUNT(*) total FROM v101_issues
                            WHERE session_id={p} GROUP BY status""",
                        (session_id,),
                    )
                )
                proposal_rows = self.foundation._dict_rows(
                    conn.execute(
                        f"""SELECT status,COUNT(*) total FROM v101_proposals
                            WHERE session_id={p} GROUP BY status""",
                        (session_id,),
                    )
                )
            quality = self.quality_history(session_id, 1)
            return {
                "version": V101_VERSION,
                "connected": True,
                "issues": {row["status"]: int(row["total"]) for row in issue_rows},
                "proposals": {row["status"]: int(row["total"]) for row in proposal_rows},
                "latest_quality": quality[0] if quality else None,
                "supervised": True,
                "autonomous_production_changes": False,
            }
        except Exception as exc:
            return {
                "version": V101_VERSION,
                "connected": False,
                "detail": f"{type(exc).__name__}: {str(exc)[:180]}",
                "supervised": True,
                "autonomous_production_changes": False,
            }
