from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from .v82 import DataFoundation


V93_VERSION = 93

V93_STAGES: List[Dict[str, Any]] = [
    {"version": 83, "name": "Durable Data", "capability": "PostgreSQL, exportación y recuperación"},
    {"version": 84, "name": "Context Intelligence", "capability": "Memoria híbrida y contexto por proyecto"},
    {"version": 85, "name": "Project Spaces", "capability": "Proyectos persistentes y aislados"},
    {"version": 86, "name": "Research Monitor", "capability": "Investigaciones y monitores programables"},
    {"version": 87, "name": "Durable Work", "capability": "Trabajos, checkpoints y reanudación"},
    {"version": 88, "name": "Secure Connections", "capability": "MCP e integraciones con aprobación"},
    {"version": 89, "name": "Telegram Studio", "capability": "Texto, imagen, voz, documentos y misiones"},
    {"version": 90, "name": "Document Studio", "capability": "Biblioteca y análisis documental"},
    {"version": 91, "name": "Safe Code Lab", "capability": "Ejecución aislada cuando el host la permite"},
    {"version": 92, "name": "Voice & Vision", "capability": "Dictado, lectura, transcripción y visión"},
    {"version": 93, "name": "Quality Intelligence", "capability": "Perfiles de respuesta y evaluación continua"},
]


PERSONAS: Dict[str, Dict[str, str]] = {
    "balanced": {
        "label": "Equilibrado",
        "description": "Claro, útil y natural para cualquier tarea.",
        "guidance": (
            "Responde de forma natural y útil. Empieza por la conclusión, ajusta la profundidad a la "
            "pregunta y evita tanto la vaguedad como el exceso de secciones."
        ),
    },
    "precise": {
        "label": "Preciso",
        "description": "Breve, verificable y orientado a hechos.",
        "guidance": (
            "Prioriza exactitud, datos comprobables y respuestas compactas. Señala supuestos y no "
            "añadas información que no ayude a resolver la solicitud."
        ),
    },
    "analytical": {
        "label": "Analítico",
        "description": "Contrasta opciones, riesgos y evidencia.",
        "guidance": (
            "Descompón problemas complejos, compara alternativas y explica riesgos, dependencias y "
            "criterios. Distingue hechos, inferencias y recomendaciones."
        ),
    },
    "teacher": {
        "label": "Tutor",
        "description": "Explica paso a paso sin asumir experiencia previa.",
        "guidance": (
            "Enseña con lenguaje sencillo, ejemplos breves y pasos progresivos. Define términos solo "
            "cuando sea necesario y comprueba que la explicación conduzca a una acción concreta."
        ),
    },
    "creative": {
        "label": "Creativo",
        "description": "Explora ideas manteniendo utilidad y coherencia.",
        "guidance": (
            "Propón ideas originales y variadas, pero conserva restricciones, viabilidad y una "
            "recomendación final clara."
        ),
    },
    "executive": {
        "label": "Ejecutivo",
        "description": "Decisiones, prioridades y próximos pasos.",
        "guidance": (
            "Entrega primero un resumen ejecutivo. Prioriza impacto, urgencia, responsables, riesgos "
            "y próximos pasos medibles."
        ),
    },
}


def _safe_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


class PersonalIntelligenceOS:
    """Persistent v83-v93 capabilities built on the v82 Data Foundation."""

    def __init__(self, foundation: DataFoundation):
        self.foundation = foundation
        self._schema_ready = False

    @property
    def driver(self) -> str:
        return self.foundation.driver

    def _p(self) -> str:
        return "%s" if self.driver == "postgresql" else "?"

    def _json_value(self, value: Any) -> Any:
        return self.foundation._json_value(value)  # Shared JSONB/SQLite adapter.

    def init_schema(self) -> None:
        if self.driver == "postgresql":
            statements = [
                """CREATE TABLE IF NOT EXISTS v93_projects (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '', instructions TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT 'cyan', status TEXT NOT NULL DEFAULT 'active',
                    created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL,
                    UNIQUE(session_id, name))""",
                """CREATE INDEX IF NOT EXISTS idx_v93_projects_session
                    ON v93_projects(session_id, updated_at DESC)""",
                """CREATE TABLE IF NOT EXISTS v93_settings (
                    session_id TEXT PRIMARY KEY, persona TEXT NOT NULL DEFAULT 'balanced',
                    voice_enabled BOOLEAN NOT NULL DEFAULT TRUE, auto_speak BOOLEAN NOT NULL DEFAULT FALSE,
                    voice_name TEXT NOT NULL DEFAULT 'alloy', voice_rate DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                    locale TEXT NOT NULL DEFAULT 'es-HN', updated_at DOUBLE PRECISION NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS v93_monitors (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, project_name TEXT NOT NULL DEFAULT 'General',
                    title TEXT NOT NULL, query TEXT NOT NULL, cadence TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'telegram', status TEXT NOT NULL DEFAULT 'paused',
                    last_run_at DOUBLE PRECISION NOT NULL DEFAULT 0,
                    next_run_at DOUBLE PRECISION NOT NULL DEFAULT 0,
                    created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
                """CREATE INDEX IF NOT EXISTS idx_v93_monitors_due
                    ON v93_monitors(status, next_run_at)""",
                """CREATE TABLE IF NOT EXISTS v93_quality (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, prompt TEXT NOT NULL,
                    response_excerpt TEXT NOT NULL, score DOUBLE PRECISION NOT NULL,
                    checks_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at DOUBLE PRECISION NOT NULL)""",
                """CREATE INDEX IF NOT EXISTS idx_v93_quality_session
                    ON v93_quality(session_id, created_at DESC)""",
                """CREATE TABLE IF NOT EXISTS v93_backup_log (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, item_counts_json JSONB NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL)""",
                """INSERT INTO v82_schema_migrations(version, applied_at)
                    VALUES (93, EXTRACT(EPOCH FROM NOW())) ON CONFLICT(version) DO NOTHING""",
            ]
            with self.foundation.connection() as conn:
                for statement in statements:
                    conn.execute(statement)
        else:
            with self.foundation.connection() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS v93_projects (
                        id TEXT PRIMARY KEY, session_id TEXT NOT NULL, name TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '', instructions TEXT NOT NULL DEFAULT '',
                        color TEXT NOT NULL DEFAULT 'cyan', status TEXT NOT NULL DEFAULT 'active',
                        created_at REAL NOT NULL, updated_at REAL NOT NULL,
                        UNIQUE(session_id, name)
                    );
                    CREATE INDEX IF NOT EXISTS idx_v93_projects_session
                        ON v93_projects(session_id, updated_at DESC);
                    CREATE TABLE IF NOT EXISTS v93_settings (
                        session_id TEXT PRIMARY KEY, persona TEXT NOT NULL DEFAULT 'balanced',
                        voice_enabled INTEGER NOT NULL DEFAULT 1, auto_speak INTEGER NOT NULL DEFAULT 0,
                        voice_name TEXT NOT NULL DEFAULT 'alloy', voice_rate REAL NOT NULL DEFAULT 1.0,
                        locale TEXT NOT NULL DEFAULT 'es-HN', updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS v93_monitors (
                        id TEXT PRIMARY KEY, session_id TEXT NOT NULL, project_name TEXT NOT NULL DEFAULT 'General',
                        title TEXT NOT NULL, query TEXT NOT NULL, cadence TEXT NOT NULL,
                        channel TEXT NOT NULL DEFAULT 'telegram', status TEXT NOT NULL DEFAULT 'paused',
                        last_run_at REAL NOT NULL DEFAULT 0, next_run_at REAL NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL, updated_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_v93_monitors_due
                        ON v93_monitors(status, next_run_at);
                    CREATE TABLE IF NOT EXISTS v93_quality (
                        id TEXT PRIMARY KEY, session_id TEXT NOT NULL, prompt TEXT NOT NULL,
                        response_excerpt TEXT NOT NULL, score REAL NOT NULL,
                        checks_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_v93_quality_session
                        ON v93_quality(session_id, created_at DESC);
                    CREATE TABLE IF NOT EXISTS v93_backup_log (
                        id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                        item_counts_json TEXT NOT NULL, created_at REAL NOT NULL
                    );
                    INSERT OR IGNORE INTO v82_schema_migrations(version, applied_at)
                    VALUES (93, strftime('%s','now'));
                    """
                )
        self._schema_ready = True

    def _ensure_schema(self) -> None:
        if not self._schema_ready:
            self.init_schema()

    def personas(self) -> List[Dict[str, str]]:
        return [{"id": key, **value} for key, value in PERSONAS.items()]

    def settings(self, session_id: str) -> Dict[str, Any]:
        self._ensure_schema()
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(f"SELECT * FROM v93_settings WHERE session_id={p}", (session_id,))
            )
        if not rows:
            return {
                "session_id": session_id,
                "persona": "balanced",
                "voice_enabled": True,
                "auto_speak": False,
                "voice_name": "alloy",
                "voice_rate": 1.0,
                "locale": "es-HN",
                "updated_at": 0,
            }
        row = rows[0]
        row["voice_enabled"] = bool(row.get("voice_enabled"))
        row["auto_speak"] = bool(row.get("auto_speak"))
        return row

    def save_settings(self, session_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_schema()
        current = self.settings(session_id)
        persona = str(values.get("persona", current["persona"])).strip().lower()
        if persona not in PERSONAS:
            raise ValueError("Perfil de respuesta no permitido.")
        voice_name = re.sub(r"[^a-zA-Z0-9_-]", "", str(values.get("voice_name", current["voice_name"])))[:40] or "alloy"
        voice_rate = max(0.7, min(float(values.get("voice_rate", current["voice_rate"])), 1.4))
        locale = re.sub(r"[^a-zA-Z-]", "", str(values.get("locale", current["locale"])))[:20] or "es-HN"
        payload = {
            "session_id": session_id,
            "persona": persona,
            "voice_enabled": bool(values.get("voice_enabled", current["voice_enabled"])),
            "auto_speak": bool(values.get("auto_speak", current["auto_speak"])),
            "voice_name": voice_name,
            "voice_rate": voice_rate,
            "locale": locale,
            "updated_at": time.time(),
        }
        with self.foundation.connection() as conn:
            if self.driver == "postgresql":
                conn.execute(
                    """INSERT INTO v93_settings(
                        session_id,persona,voice_enabled,auto_speak,voice_name,voice_rate,locale,updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(session_id) DO UPDATE SET
                        persona=EXCLUDED.persona,voice_enabled=EXCLUDED.voice_enabled,
                        auto_speak=EXCLUDED.auto_speak,voice_name=EXCLUDED.voice_name,
                        voice_rate=EXCLUDED.voice_rate,locale=EXCLUDED.locale,updated_at=EXCLUDED.updated_at""",
                    tuple(payload.values()),
                )
            else:
                conn.execute(
                    """INSERT INTO v93_settings(
                        session_id,persona,voice_enabled,auto_speak,voice_name,voice_rate,locale,updated_at)
                        VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(session_id) DO UPDATE SET
                        persona=excluded.persona,voice_enabled=excluded.voice_enabled,
                        auto_speak=excluded.auto_speak,voice_name=excluded.voice_name,
                        voice_rate=excluded.voice_rate,locale=excluded.locale,updated_at=excluded.updated_at""",
                    (
                        session_id, persona, int(payload["voice_enabled"]), int(payload["auto_speak"]),
                        voice_name, voice_rate, locale, payload["updated_at"],
                    ),
                )
        return self.settings(session_id)

    def response_guidance(self, session_id: str, override: str = "") -> str:
        persona = str(override or self.settings(session_id)["persona"]).strip().lower()
        profile = PERSONAS.get(persona, PERSONAS["balanced"])
        return f"Perfil de respuesta: {profile['label']}. {profile['guidance']}"

    def list_projects(self, session_id: str) -> List[Dict[str, Any]]:
        self._ensure_schema()
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT * FROM v93_projects WHERE session_id={p} AND status!='deleted'
                        ORDER BY CASE WHEN name='General' THEN 0 ELSE 1 END, updated_at DESC""",
                    (session_id,),
                )
            )
        if not any(row.get("name") == "General" for row in rows):
            self.create_project(session_id, "General", "Espacio principal de JARVIS")
            return self.list_projects(session_id)
        return rows

    def create_project(
        self,
        session_id: str,
        name: str,
        description: str = "",
        instructions: str = "",
        color: str = "cyan",
    ) -> Dict[str, Any]:
        self._ensure_schema()
        clean_name = re.sub(r"\s+", " ", str(name or "")).strip()[:120]
        if not clean_name:
            raise ValueError("El proyecto necesita un nombre.")
        now = time.time()
        project_id = str(uuid.uuid4())
        with self.foundation.connection() as conn:
            if self.driver == "postgresql":
                conn.execute(
                    """INSERT INTO v93_projects(
                        id,session_id,name,description,instructions,color,status,created_at,updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,'active',%s,%s)
                        ON CONFLICT(session_id,name) DO UPDATE SET
                        description=EXCLUDED.description,instructions=EXCLUDED.instructions,
                        color=EXCLUDED.color,status='active',updated_at=EXCLUDED.updated_at""",
                    (project_id, session_id, clean_name, description[:2000], instructions[:8000], color[:30], now, now),
                )
            else:
                conn.execute(
                    """INSERT INTO v93_projects(
                        id,session_id,name,description,instructions,color,status,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,'active',?,?)
                        ON CONFLICT(session_id,name) DO UPDATE SET
                        description=excluded.description,instructions=excluded.instructions,
                        color=excluded.color,status='active',updated_at=excluded.updated_at""",
                    (project_id, session_id, clean_name, description[:2000], instructions[:8000], color[:30], now, now),
                )
        return next(project for project in self.list_projects(session_id) if project["name"] == clean_name)

    def delete_project(self, session_id: str, project_id: str) -> bool:
        self._ensure_schema()
        p = self._p()
        with self.foundation.connection() as conn:
            cursor = conn.execute(
                f"""UPDATE v93_projects SET status='deleted',updated_at={p}
                    WHERE id={p} AND session_id={p} AND name!='General'""",
                (time.time(), project_id, session_id),
            )
        return bool(cursor.rowcount)

    def project_context(self, session_id: str, project_name: str, query: str) -> Dict[str, Any]:
        projects = self.list_projects(session_id)
        project = next((item for item in projects if item["name"] == project_name), None)
        memories = self.foundation.search_memory(
            session_id,
            query,
            project_name="" if project_name == "General" else project_name,
            limit=6,
        )
        return {"project": project, "memories": memories}

    def create_monitor(
        self,
        session_id: str,
        title: str,
        query: str,
        cadence: str,
        *,
        project_name: str = "General",
        channel: str = "telegram",
    ) -> Dict[str, Any]:
        self._ensure_schema()
        cadence = str(cadence or "").strip().lower()
        if not re.fullmatch(r"(daily|weekly|every_[1-9][0-9]*_hours)", cadence):
            raise ValueError("Cadencia no permitida. Usa daily, weekly o every_N_hours.")
        now = time.time()
        seconds = 86400 if cadence == "daily" else 604800 if cadence == "weekly" else int(cadence.split("_")[1]) * 3600
        monitor_id = str(uuid.uuid4())
        p = self._p()
        with self.foundation.connection() as conn:
            conn.execute(
                f"""INSERT INTO v93_monitors(
                    id,session_id,project_name,title,query,cadence,channel,status,last_run_at,next_run_at,
                    created_at,updated_at) VALUES ({','.join([p] * 12)})""",
                (
                    monitor_id, session_id, project_name[:120], title[:300], query[:12000],
                    cadence, channel[:40], "paused", 0, now + seconds, now, now,
                ),
            )
        return self.get_monitor(session_id, monitor_id) or {}

    def get_monitor(self, session_id: str, monitor_id: str) -> Optional[Dict[str, Any]]:
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(f"SELECT * FROM v93_monitors WHERE id={p} AND session_id={p}", (monitor_id, session_id))
            )
        return rows[0] if rows else None

    def list_monitors(self, session_id: str) -> List[Dict[str, Any]]:
        self._ensure_schema()
        p = self._p()
        with self.foundation.connection() as conn:
            return self.foundation._dict_rows(
                conn.execute(
                    f"SELECT * FROM v93_monitors WHERE session_id={p} ORDER BY created_at DESC",
                    (session_id,),
                )
            )

    def set_monitor_status(self, session_id: str, monitor_id: str, status: str) -> Optional[Dict[str, Any]]:
        if status not in {"active", "paused", "cancelled"}:
            raise ValueError("Estado de monitor no permitido.")
        p = self._p()
        with self.foundation.connection() as conn:
            conn.execute(
                f"UPDATE v93_monitors SET status={p},updated_at={p} WHERE id={p} AND session_id={p}",
                (status, time.time(), monitor_id, session_id),
            )
        return self.get_monitor(session_id, monitor_id)

    @staticmethod
    def _cadence_seconds(cadence: str) -> int:
        if cadence == "daily":
            return 86400
        if cadence == "weekly":
            return 604800
        match = re.fullmatch(r"every_([1-9][0-9]*)_hours", str(cadence or ""))
        return int(match.group(1)) * 3600 if match else 86400

    def claim_due_monitors(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Claim due monitors by advancing their schedule before execution.

        Advancing first makes dispatch idempotent across overlapping maintenance
        cycles. A failed execution is still recorded by the durable job/workflow
        layer and the monitor will run again on its next cadence.
        """
        self._ensure_schema()
        now = time.time()
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT * FROM v93_monitors
                        WHERE status='active' AND next_run_at<={p}
                        ORDER BY next_run_at ASC LIMIT {p}""",
                    (now, max(1, min(int(limit), 100))),
                )
            )
            for row in rows:
                next_run = now + self._cadence_seconds(str(row.get("cadence") or "daily"))
                conn.execute(
                    f"""UPDATE v93_monitors SET last_run_at={p},next_run_at={p},updated_at={p}
                        WHERE id={p} AND status='active'""",
                    (now, next_run, now, row["id"]),
                )
                row["last_run_at"] = now
                row["next_run_at"] = next_run
        return rows

    def evaluate_response(self, session_id: str, prompt: str, response: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._ensure_schema()
        clean = str(response or "").strip()
        checks = {
            "visible": bool(clean),
            "substantive": len(clean) >= 32,
            "no_internal_error": not any(marker in clean.lower() for marker in ("traceback", "internal server error", "api key")),
            "answers_question": bool(set(re.findall(r"\w{4,}", prompt.lower())) & set(re.findall(r"\w{4,}", clean.lower()))),
            "metadata_verified": bool((metadata or {}).get("verified")),
        }
        weights = {"visible": .3, "substantive": .2, "no_internal_error": .2, "answers_question": .15, "metadata_verified": .15}
        score = round(sum(weights[key] for key, passed in checks.items() if passed), 3)
        evaluation = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "score": score,
            "checks": checks,
            "created_at": time.time(),
        }
        p = self._p()
        with self.foundation.connection() as conn:
            conn.execute(
                f"""INSERT INTO v93_quality(
                    id,session_id,prompt,response_excerpt,score,checks_json,created_at)
                    VALUES ({','.join([p] * 7)})""",
                (
                    evaluation["id"], session_id, prompt[:12000], clean[:4000], score,
                    self._json_value(checks), evaluation["created_at"],
                ),
            )
        return evaluation

    def quality_summary(self, session_id: str, limit: int = 100) -> Dict[str, Any]:
        self._ensure_schema()
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT score,checks_json,created_at FROM v93_quality
                        WHERE session_id={p} ORDER BY created_at DESC LIMIT {p}""",
                    (session_id, max(1, min(int(limit), 500))),
                )
            )
        scores = [float(row.get("score") or 0) for row in rows]
        return {
            "evaluations": len(rows),
            "average_score": round(sum(scores) / len(scores), 3) if scores else 0,
            "latest_score": scores[0] if scores else 0,
        }

    def export_snapshot(self, session_id: str) -> Dict[str, Any]:
        self._ensure_schema()
        projects = self.list_projects(session_id)
        settings = self.settings(session_id)
        memories = self.foundation.list_memories(session_id, limit=1000)
        tasks = self.foundation.list_tasks(session_id, limit=500)
        monitors = self.list_monitors(session_id)
        snapshot = {
            "format": "jarvis-personal-os",
            "version": V93_VERSION,
            "created_at": time.time(),
            "session_id": session_id,
            "projects": projects,
            "settings": settings,
            "memories": memories,
            "tasks": tasks,
            "monitors": monitors,
        }
        counts = {key: len(snapshot[key]) for key in ("projects", "memories", "tasks", "monitors")}
        p = self._p()
        with self.foundation.connection() as conn:
            conn.execute(
                f"INSERT INTO v93_backup_log(id,session_id,item_counts_json,created_at) VALUES ({','.join([p] * 4)})",
                (str(uuid.uuid4()), session_id, self._json_value(counts), snapshot["created_at"]),
            )
        return snapshot

    def status(self, session_id: str) -> Dict[str, Any]:
        self._ensure_schema()
        projects = self.list_projects(session_id)
        settings = self.settings(session_id)
        monitors = self.list_monitors(session_id)
        quality = self.quality_summary(session_id)
        foundation = self.foundation.status()
        return {
            "version": V93_VERSION,
            "edition": "Personal Intelligence OS",
            "foundation": foundation,
            "projects": {"total": len(projects), "active": sum(item.get("status") == "active" for item in projects)},
            "monitors": {"total": len(monitors), "active": sum(item.get("status") == "active" for item in monitors)},
            "settings": settings,
            "quality": quality,
            "stages": V93_STAGES,
            "personas": self.personas(),
        }
