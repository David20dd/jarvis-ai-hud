from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TERMINAL_STATES = {"completed", "failed", "cancelled", "rejected"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _terms(text: str) -> List[str]:
    return [item for item in re.findall(r"[\wáéíóúüñ]+", (text or "").lower()) if len(item) > 2]


class UnifiedIntelligenceStore:
    """Persistent decisions, verified facts and safe interactive artifacts."""

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
                CREATE TABLE IF NOT EXISTS intelligence_decisions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    complexity TEXT NOT NULL,
                    route_json TEXT NOT NULL,
                    budget_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'planned',
                    workflow_id TEXT NOT NULL DEFAULT '',
                    quality_score REAL NOT NULL DEFAULT 0,
                    latency_ms REAL NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_intelligence_session
                    ON intelligence_decisions(session_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS knowledge_facts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_name TEXT NOT NULL DEFAULT 'General',
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_text TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'user',
                    source_ref TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    expires_at REAL NOT NULL DEFAULT 0,
                    verified INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_facts_scope
                    ON knowledge_facts(session_id, project_name, updated_at DESC);

                CREATE TABLE IF NOT EXISTS interactive_artifacts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_session
                    ON interactive_artifacts(session_id, updated_at DESC);
                """
            )

    def save_decision(self, session_id: str, objective: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        item_id = str(uuid.uuid4())
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO intelligence_decisions(
                    id,session_id,objective,intent,complexity,route_json,budget_json,
                    status,workflow_id,quality_score,latency_ms,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,'planned','',0,0,?,?)
                """,
                (
                    item_id, session_id, objective[:30000], plan["intent"], plan["complexity"],
                    _json(plan.get("route", [])), _json(plan.get("budget", {})), now, now,
                ),
            )
        return self.get_decision(item_id) or {}

    def get_decision(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM intelligence_decisions WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["route"] = _decode(item.pop("route_json"), [])
        item["budget"] = _decode(item.pop("budget_json"), {})
        return item

    def link_workflow(self, item_id: str, workflow_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE intelligence_decisions SET workflow_id = ?, status = 'queued', updated_at = ? WHERE id = ?",
                (workflow_id, time.time(), item_id),
            )

    def record_outcome(self, item_id: str, status: str, quality_score: float, latency_ms: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE intelligence_decisions SET status = ?, quality_score = ?, latency_ms = ?, updated_at = ?
                WHERE id = ?
                """,
                (status[:40], max(0.0, min(float(quality_score), 1.0)), max(0.0, float(latency_ms)), time.time(), item_id),
            )

    def record_workflow_outcome(self, workflow_id: str, status: str, quality_score: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE intelligence_decisions SET status = ?, quality_score = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (status[:40], max(0.0, min(float(quality_score), 1.0)), time.time(), workflow_id),
            )

    def list_decisions(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM intelligence_decisions WHERE session_id = ? ORDER BY updated_at DESC LIMIT ?",
                (session_id, max(1, min(int(limit), 100))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["route"] = _decode(item.pop("route_json"), [])
            item["budget"] = _decode(item.pop("budget_json"), {})
            result.append(item)
        return result

    def add_fact(
        self,
        *,
        session_id: str,
        project_name: str,
        subject: str,
        predicate: str,
        object_text: str,
        source_type: str = "user",
        source_ref: str = "",
        confidence: float = 0.7,
        expires_at: float = 0,
        verified: bool = False,
    ) -> Dict[str, Any]:
        item_id = str(uuid.uuid4())
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item_id, session_id, (project_name or "General")[:120], subject[:500], predicate[:240],
                    object_text[:12000], source_type[:80], source_ref[:1000],
                    max(0.0, min(float(confidence), 1.0)), max(0.0, float(expires_at)),
                    int(bool(verified)), now, now,
                ),
            )
        return self.get_fact(item_id) or {}

    def get_fact(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM knowledge_facts WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["verified"] = bool(item["verified"])
        return item

    def search_facts(self, session_id: str, query: str = "", project_name: str = "", limit: int = 30) -> List[Dict[str, Any]]:
        now = time.time()
        clauses = ["session_id = ?", "(expires_at = 0 OR expires_at > ?)"]
        params: List[Any] = [session_id, now]
        if project_name:
            clauses.append("project_name = ?")
            params.append(project_name)
        params.append(max(1, min(int(limit) * 8, 500)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM knowledge_facts WHERE {' AND '.join(clauses)} ORDER BY verified DESC, confidence DESC, updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        terms = set(_terms(query))
        scored = []
        for row in rows:
            item = dict(row)
            item["verified"] = bool(item["verified"])
            haystack = " ".join([item["subject"], item["predicate"], item["object_text"]]).lower()
            overlap = sum(1 for term in terms if term in haystack)
            item["score"] = round((overlap / max(1, len(terms))) * 0.65 + float(item["confidence"]) * 0.25 + (0.1 if item["verified"] else 0), 4)
            if not terms or overlap:
                scored.append(item)
        return sorted(scored, key=lambda item: (item["score"], item["updated_at"]), reverse=True)[:max(1, min(int(limit), 100))]

    def delete_fact(self, item_id: str, session_id: str) -> bool:
        with self._connect() as conn:
            return bool(conn.execute("DELETE FROM knowledge_facts WHERE id = ? AND session_id = ?", (item_id, session_id)).rowcount)

    @staticmethod
    def validate_artifact(artifact_type: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        kind = (artifact_type or "").strip().lower()
        if kind not in {"table", "chart", "checklist", "timeline", "comparison"}:
            raise ValueError("Tipo de resultado interactivo no permitido.")
        if not isinstance(spec, dict):
            raise ValueError("La especificación debe ser un objeto JSON.")
        clean: Dict[str, Any] = {"title": str(spec.get("title") or "")[:300]}
        if kind in {"table", "comparison"}:
            columns = [str(item)[:120] for item in spec.get("columns", [])][:20]
            rows = []
            for row in spec.get("rows", [])[:200]:
                if isinstance(row, list):
                    rows.append([str(value)[:1000] for value in row[:len(columns) or 20]])
                elif isinstance(row, dict):
                    rows.append({str(key)[:120]: str(value)[:1000] for key, value in list(row.items())[:20]})
            clean.update({"columns": columns, "rows": rows})
        elif kind == "chart":
            clean["labels"] = [str(item)[:120] for item in spec.get("labels", [])][:100]
            clean["values"] = [max(-1e12, min(float(item), 1e12)) for item in spec.get("values", [])[:100]]
            clean["unit"] = str(spec.get("unit") or "")[:40]
        else:
            clean["items"] = [str(item)[:1000] for item in spec.get("items", [])][:200]
        return clean

    def create_artifact(self, session_id: str, title: str, artifact_type: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        clean = self.validate_artifact(artifact_type, spec)
        item_id = str(uuid.uuid4())
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO interactive_artifacts VALUES(?,?,?,?,?,?,?)",
                (item_id, session_id, title[:300], artifact_type.lower(), _json(clean), now, now),
            )
        return self.get_artifact(item_id, session_id) or {}

    def get_artifact(self, item_id: str, session_id: str = "") -> Optional[Dict[str, Any]]:
        clauses, params = ["id = ?"], [item_id]
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        with self._connect() as conn:
            row = conn.execute(f"SELECT * FROM interactive_artifacts WHERE {' AND '.join(clauses)}", params).fetchone()
        if not row:
            return None
        item = dict(row)
        item["spec"] = _decode(item.pop("spec_json"), {})
        return item

    def list_artifacts(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM interactive_artifacts WHERE session_id = ? ORDER BY updated_at DESC LIMIT ?",
                (session_id, max(1, min(int(limit), 100))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["spec"] = _decode(item.pop("spec_json"), {})
            result.append(item)
        return result

    def status(self, session_id: str = "") -> Dict[str, Any]:
        self.init_schema()
        with self._connect() as conn:
            if session_id:
                decisions = conn.execute("SELECT status,COUNT(*) count FROM intelligence_decisions WHERE session_id = ? GROUP BY status", (session_id,)).fetchall()
                facts = conn.execute("SELECT COUNT(*) count FROM knowledge_facts WHERE session_id = ?", (session_id,)).fetchone()
                artifacts = conn.execute("SELECT COUNT(*) count FROM interactive_artifacts WHERE session_id = ?", (session_id,)).fetchone()
            else:
                decisions = conn.execute("SELECT status,COUNT(*) count FROM intelligence_decisions GROUP BY status").fetchall()
                facts = conn.execute("SELECT COUNT(*) count FROM knowledge_facts").fetchone()
                artifacts = conn.execute("SELECT COUNT(*) count FROM interactive_artifacts").fetchone()
        return {
            "decisions": {str(row["status"]): int(row["count"]) for row in decisions},
            "facts": int(facts["count"] or 0),
            "artifacts": int(artifacts["count"] or 0),
        }


class IntelligencePlanner:
    """Deterministic first-pass planner; providers may refine the returned plan later."""

    RISK_TERMS = {"elimina", "borra", "publica", "envía", "envia", "compra", "paga", "transfiere", "credencial"}

    @staticmethod
    def _complexity(objective: str) -> str:
        text = (objective or "").lower()
        words = len(text.split())
        signals = sum(term in text for term in ("investiga", "compara", "verifica", "archivo", "código", "codigo", "plan", "automatiza", "fuentes"))
        if words > 80 or signals >= 4:
            return "high"
        if words > 28 or signals >= 2:
            return "medium"
        return "low"

    def build(
        self,
        objective: str,
        *,
        intent: str,
        mode: str,
        provider_routes: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        objective = re.sub(r"\s+", " ", objective or "").strip()
        if not objective:
            raise ValueError("Escribe un objetivo concreto.")
        complexity = self._complexity(objective)
        budgets = {
            "low": {"time_seconds": 45, "max_provider_attempts": 2, "max_sources": 3, "max_steps": 3, "max_output_tokens": 900},
            "medium": {"time_seconds": 180, "max_provider_attempts": 4, "max_sources": 8, "max_steps": 6, "max_output_tokens": 1800},
            "high": {"time_seconds": 600, "max_provider_attempts": 6, "max_sources": 16, "max_steps": 8, "max_output_tokens": 3000},
        }
        route = []
        for item in provider_routes or []:
            if item.get("configured") and item.get("provider"):
                route.append({
                    "provider": str(item["provider"]),
                    "score": float(item.get("score", 0) or 0),
                    "model": str((item.get("models") or [{}])[0].get("model") or ""),
                })
            if len(route) >= budgets[complexity]["max_provider_attempts"]:
                break
        steps = [
            {"id": "understand", "label": "Comprender el objetivo", "tool": "local", "parallel_group": 0},
            {"id": "context", "label": "Recuperar memoria y documentos relevantes", "tool": "semantic_search", "parallel_group": 1},
        ]
        if intent == "research":
            steps.extend([
                {"id": "sources", "label": "Buscar y contrastar fuentes", "tool": "deep_research", "parallel_group": 2},
                {"id": "evidence", "label": "Verificar evidencia y contradicciones", "tool": "verifier", "parallel_group": 3},
            ])
        elif intent in {"coding", "code"}:
            steps.extend([
                {"id": "solution", "label": "Diseñar la solución", "tool": "model", "parallel_group": 2},
                {"id": "tests", "label": "Preparar y ejecutar pruebas aisladas", "tool": "code_lab", "parallel_group": 3},
            ])
        elif intent == "documents":
            steps.append({"id": "documents", "label": "Analizar y citar documentos", "tool": "document_search", "parallel_group": 2})
        else:
            steps.append({"id": "solve", "label": "Resolver con la mejor ruta disponible", "tool": "model_or_local", "parallel_group": 2})
        steps.append({"id": "verify", "label": "Verificar y entregar", "tool": "verifier", "parallel_group": 4})
        sensitive = any(term in objective.lower() for term in self.RISK_TERMS)
        return {
            "objective": objective,
            "intent": intent or "general",
            "mode": mode or "auto",
            "complexity": complexity,
            "budget": budgets[complexity],
            "route": route,
            "steps": steps[:budgets[complexity]["max_steps"]],
            "requires_approval": sensitive,
            "recovery": ["cache", "alternate_provider", "local_tools", "partial_result"],
        }


class IntegrationRegistry:
    """Capability and consent registry; secrets remain in backend environment variables."""

    CATALOG = {
        "telegram": {"label": "Telegram", "env": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET"], "actions": ["notify", "send_document", "approve"]},
        "google_calendar": {"label": "Google Calendar", "env": ["GOOGLE_CALENDAR_CREDENTIALS_JSON"], "actions": ["read_events", "create_draft"]},
        "gmail": {"label": "Gmail", "env": ["GMAIL_CREDENTIALS_JSON"], "actions": ["search", "draft"]},
        "google_drive": {"label": "Google Drive", "env": ["GOOGLE_DRIVE_CREDENTIALS_JSON"], "actions": ["search", "read", "create_draft"]},
        "github": {"label": "GitHub", "env": ["GITHUB_TOKEN"], "actions": ["read_repository", "prepare_change", "prepare_pull_request"]},
        "notion": {"label": "Notion", "env": ["NOTION_TOKEN"], "actions": ["search", "read", "create_draft"]},
        "mcp": {"label": "MCP", "env": ["JARVIS_MCP_SERVERS_JSON"], "actions": ["discover", "call_confirmed_tool"]},
    }

    def __init__(self, environment: Dict[str, str]) -> None:
        self.environment = environment

    def status(self) -> List[Dict[str, Any]]:
        result = []
        for name, definition in self.CATALOG.items():
            configured = all(bool((self.environment.get(key) or "").strip()) for key in definition["env"])
            result.append({
                "name": name,
                "label": definition["label"],
                "configured": configured,
                "actions": definition["actions"],
                "write_requires_confirmation": True,
            })
        return result

    def prepare(self, name: str, action: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        definition = self.CATALOG.get(name)
        if not definition:
            raise KeyError("Integración no disponible.")
        if action not in definition["actions"]:
            raise ValueError("Acción no permitida para esta integración.")
        configured = all(bool((self.environment.get(key) or "").strip()) for key in definition["env"])
        return {
            "integration": name,
            "action": action,
            "configured": configured,
            "arguments": {str(key)[:120]: str(value)[:2000] for key, value in list((arguments or {}).items())[:30]},
            "requires_confirmation": action not in {"search", "read", "read_events", "read_repository", "discover"},
            "status": "ready_for_confirmation" if configured else "configuration_required",
        }
