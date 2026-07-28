from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional


V76_STAGES: List[Dict[str, Any]] = [
    {
        "version": 67,
        "name": "Unified Experience",
        "capabilities": ["design_system", "responsive_layout", "command_palette", "focus_mode"],
    },
    {
        "version": 68,
        "name": "Interactive Workspace",
        "capabilities": ["context_drawer", "interactive_artifacts", "execution_timeline", "partial_results"],
    },
    {
        "version": 69,
        "name": "Verified Research",
        "capabilities": ["query_decomposition", "source_ranking", "inline_citations", "contradiction_signals"],
    },
    {
        "version": 70,
        "name": "Project Memory",
        "capabilities": ["semantic_memory", "project_facts", "document_library", "memory_controls"],
    },
    {
        "version": 71,
        "name": "Multimodal Conversation",
        "capabilities": ["images", "documents", "audio_transcription", "speech_output"],
    },
    {
        "version": 72,
        "name": "Telegram Workspace",
        "capabilities": ["telegram_text", "telegram_media", "telegram_voice", "telegram_controls"],
    },
    {
        "version": 73,
        "name": "Mission Autonomy",
        "capabilities": ["checkpoints", "pause_resume_cancel", "approval_inbox", "auditable_actions"],
    },
    {
        "version": 74,
        "name": "Safe Code Laboratory",
        "capabilities": ["isolated_execution", "timeouts", "test_results", "code_artifacts"],
    },
    {
        "version": 75,
        "name": "Reliability Center",
        "capabilities": ["deep_health", "circuit_breakers", "performance_metrics", "recovery_routes"],
    },
    {
        "version": 76,
        "name": "Supervised Improvement",
        "capabilities": ["quality_evaluation", "bounded_recommendations", "human_approval", "rollback_ready"],
    },
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


@dataclass(frozen=True)
class ExperiencePreferences:
    theme: str = "dark"
    density: str = "comfortable"
    context_panel: bool = True
    reduce_motion: bool = False
    focus_mode: bool = False

    @classmethod
    def clean(cls, payload: Dict[str, Any]) -> "ExperiencePreferences":
        theme = str(payload.get("theme") or "dark").strip().lower()
        density = str(payload.get("density") or "comfortable").strip().lower()
        return cls(
            theme=theme if theme in {"dark", "oled", "contrast"} else "dark",
            density=density if density in {"compact", "comfortable"} else "comfortable",
            context_panel=bool(payload.get("context_panel", True)),
            reduce_motion=bool(payload.get("reduce_motion", False)),
            focus_mode=bool(payload.get("focus_mode", False)),
        )


class UnifiedExperienceStore:
    """Small persistent layer for UI preferences, activity and bounded proposals."""

    def __init__(self, db_file: str) -> None:
        self.db_file = db_file

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS v76_experience_preferences (
                    session_id TEXT PRIMARY KEY,
                    preferences_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v76_experience_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'info',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_v76_experience_events_session
                    ON v76_experience_events(session_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS v76_improvement_proposals (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    actions_json TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_v76_improvement_proposals_session
                    ON v76_improvement_proposals(session_id, created_at DESC);
                """
            )

    def preferences(self, session_id: str) -> Dict[str, Any]:
        self.init_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT preferences_json, updated_at FROM v76_experience_preferences WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return {**asdict(ExperiencePreferences()), "updated_at": 0}
        return {
            **asdict(ExperiencePreferences.clean(_decode(row["preferences_json"], {}))),
            "updated_at": float(row["updated_at"] or 0),
        }

    def save_preferences(self, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = self.preferences(session_id)
        merged = {**current, **payload}
        clean = ExperiencePreferences.clean(merged)
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO v76_experience_preferences(session_id, preferences_json, updated_at)
                VALUES(?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                    preferences_json = excluded.preferences_json,
                    updated_at = excluded.updated_at
                """,
                (session_id, _json(asdict(clean)), now),
            )
        return {**asdict(clean), "updated_at": now}

    def record_event(
        self,
        session_id: str,
        event_type: str,
        title: str,
        detail: Optional[Dict[str, Any]] = None,
        status: str = "info",
    ) -> Dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "event_type": str(event_type or "system")[:80],
            "title": str(title or "Evento JARVIS")[:240],
            "detail": dict(detail or {}),
            "status": status if status in {"info", "working", "success", "warning", "failed"} else "info",
            "created_at": time.time(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO v76_experience_events VALUES(?,?,?,?,?,?,?)",
                (
                    item["id"],
                    session_id,
                    item["event_type"],
                    item["title"],
                    _json(item["detail"]),
                    item["status"],
                    item["created_at"],
                ),
            )
        return item

    def timeline(self, session_id: str, limit: int = 40) -> List[Dict[str, Any]]:
        self.init_schema()
        safe_limit = max(1, min(int(limit), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id,event_type,title,detail_json,status,created_at
                FROM v76_experience_events
                WHERE session_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (session_id, safe_limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "title": row["title"],
                "detail": _decode(row["detail_json"], {}),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def propose_improvement(
        self,
        session_id: str,
        title: str,
        evidence: Iterable[Dict[str, Any]],
        actions: Iterable[str],
        risk: str = "low",
    ) -> Dict[str, Any]:
        now = time.time()
        item = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "title": str(title or "Mejora propuesta")[:240],
            "evidence": list(evidence)[:20],
            "actions": [str(action)[:500] for action in list(actions)[:20]],
            "risk": risk if risk in {"low", "medium", "high"} else "medium",
            "status": "proposed",
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO v76_improvement_proposals VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    item["id"],
                    session_id,
                    item["title"],
                    _json(item["evidence"]),
                    _json(item["actions"]),
                    item["risk"],
                    item["status"],
                    now,
                    now,
                ),
            )
        return item

    def proposals(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self.init_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM v76_improvement_proposals
                WHERE session_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (session_id, max(1, min(int(limit), 100))),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["evidence"] = _decode(item.pop("evidence_json"), [])
            item["actions"] = _decode(item.pop("actions_json"), [])
            result.append(item)
        return result

    def status(self, session_id: str) -> Dict[str, Any]:
        self.init_schema()
        with self._connect() as conn:
            events = conn.execute(
                "SELECT status,COUNT(*) total FROM v76_experience_events WHERE session_id = ? GROUP BY status",
                (session_id,),
            ).fetchall()
            proposals = conn.execute(
                "SELECT status,COUNT(*) total FROM v76_improvement_proposals WHERE session_id = ? GROUP BY status",
                (session_id,),
            ).fetchall()
        return {
            "preferences": self.preferences(session_id),
            "events": {str(row["status"]): int(row["total"]) for row in events},
            "proposals": {str(row["status"]): int(row["total"]) for row in proposals},
        }


class CommandRouter:
    """Deterministic, zero-token router for the global command palette."""

    COMMANDS: List[Dict[str, str]] = [
        {"id": "new_chat", "label": "Nueva conversación", "category": "navigation", "shortcut": "Ctrl N"},
        {"id": "open_chat", "label": "Abrir Chat", "category": "navigation", "shortcut": ""},
        {"id": "open_knowledge", "label": "Abrir Conocimiento", "category": "navigation", "shortcut": ""},
        {"id": "open_missions", "label": "Abrir Misiones", "category": "navigation", "shortcut": ""},
        {"id": "open_nexus", "label": "Abrir Nexus", "category": "navigation", "shortcut": ""},
        {"id": "open_telegram", "label": "Abrir Telegram", "category": "navigation", "shortcut": ""},
        {"id": "toggle_context", "label": "Mostrar u ocultar contexto", "category": "workspace", "shortcut": "Ctrl ."},
        {"id": "toggle_focus", "label": "Activar modo enfoque", "category": "workspace", "shortcut": "Ctrl Shift F"},
        {"id": "start_research", "label": "Iniciar investigación verificada", "category": "action", "shortcut": ""},
        {"id": "start_mission", "label": "Crear misión autónoma", "category": "action", "shortcut": ""},
        {"id": "attach_file", "label": "Adjuntar un archivo", "category": "action", "shortcut": ""},
        {"id": "run_diagnostics", "label": "Ejecutar diagnóstico", "category": "system", "shortcut": ""},
    ]

    @staticmethod
    def suggest(query: str = "", limit: int = 12) -> List[Dict[str, str]]:
        normalized = str(query or "").strip().lower()
        items = CommandRouter.COMMANDS
        if normalized:
            terms = [part for part in normalized.split() if part]
            items = [
                item
                for item in items
                if all(term in f"{item['label']} {item['category']} {item['id']}".lower() for term in terms)
            ]
        return items[: max(1, min(int(limit), 20))]


class ImprovementAdvisor:
    """Produces conservative recommendations. It never edits code or deploys."""

    @staticmethod
    def analyze(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        recommendations: List[Dict[str, Any]] = []
        health = str(snapshot.get("health") or "unknown")
        errors = int(snapshot.get("errors_24h") or 0)
        cache_hits = int(snapshot.get("cached_responses") or 0)
        requests = int(snapshot.get("requests_24h") or 0)
        open_circuits = int(snapshot.get("open_circuits") or 0)

        if health not in {"ok", "ready"}:
            recommendations.append(
                {
                    "priority": "high",
                    "title": "Recuperar componentes degradados",
                    "reason": "El diagnóstico no está completamente operativo.",
                    "action": "Revisar health/deep y mantener las rutas locales mientras se recuperan proveedores.",
                }
            )
        if open_circuits:
            recommendations.append(
                {
                    "priority": "high",
                    "title": "Aislar rutas inestables",
                    "reason": f"Hay {open_circuits} circuitos abiertos.",
                    "action": "Mantener el fallback y revisar credenciales, cuota o latencia del proveedor afectado.",
                }
            )
        if errors >= 3:
            recommendations.append(
                {
                    "priority": "medium",
                    "title": "Analizar errores repetidos",
                    "reason": f"Se registraron {errors} errores en las últimas 24 horas.",
                    "action": "Agruparlos por operación y crear una prueba de regresión antes de cambiar producción.",
                }
            )
        if requests >= 10 and cache_hits / max(requests, 1) < 0.1:
            recommendations.append(
                {
                    "priority": "low",
                    "title": "Mejorar reutilización segura",
                    "reason": "La caché aporta poco frente al volumen reciente.",
                    "action": "Revisar TTL y similitud sin reutilizar respuestas que requieran datos actuales.",
                }
            )
        if not recommendations:
            recommendations.append(
                {
                    "priority": "low",
                    "title": "Mantener configuración estable",
                    "reason": "No se detectaron señales críticas en el resumen disponible.",
                    "action": "Continuar midiendo calidad, latencia y recuperación sin cambios automáticos de código.",
                }
            )
        return {
            "status": "ok",
            "recommendations": recommendations,
            "automatic_scope": ["bounded_routing_statistics", "cache_preferences", "source_limit_hint"],
            "approval_required": ["code", "deployment", "secrets", "permissions", "external_writes"],
        }
