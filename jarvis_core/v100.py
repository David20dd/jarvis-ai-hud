from __future__ import annotations

import json
import re
import time
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional

from .v82 import DataFoundation


V100_VERSION = 100

V100_STAGES: List[Dict[str, Any]] = [
    {
        "version": 94,
        "name": "Conversation Workspace",
        "capabilities": ["streaming resiliente", "editar", "regenerar", "ramificar", "comandos"],
    },
    {
        "version": 95,
        "name": "Canvas & Artifacts",
        "capabilities": ["canvas persistente", "notas", "código", "tablas", "versiones"],
    },
    {
        "version": 96,
        "name": "Deep Research",
        "capabilities": ["plan de búsqueda", "fuentes", "citas", "verificación", "biblioteca"],
    },
    {
        "version": 97,
        "name": "Conversational Voice",
        "capabilities": ["dictado", "transcripción", "lectura", "fallback del navegador"],
    },
    {
        "version": 98,
        "name": "Telegram Pro",
        "capabilities": ["texto", "imágenes", "audio", "documentos", "misiones", "voz"],
    },
    {
        "version": 99,
        "name": "Automation Center",
        "capabilities": ["monitores", "tareas", "checkpoints", "aprobaciones", "notificaciones"],
    },
    {
        "version": 100,
        "name": "Unified Intelligence",
        "capabilities": ["router multimodelo", "memoria híbrida", "control de calidad", "modo degradado"],
    },
]


WORKSPACE_KINDS = {"document", "note", "code", "table", "checklist", "canvas"}


def _safe_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _clean_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


class UnifiedWorkspace:
    """Persistent v94-v100 workspace layered on top of the durable data foundation."""

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
                """CREATE TABLE IF NOT EXISTS v100_workspace_items (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_name TEXT NOT NULL DEFAULT 'General',
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    version INTEGER NOT NULL DEFAULT 1,
                    pinned BOOLEAN NOT NULL DEFAULT FALSE,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                )""",
                """CREATE INDEX IF NOT EXISTS idx_v100_workspace_session
                    ON v100_workspace_items(session_id, project_name, updated_at DESC)""",
                """CREATE INDEX IF NOT EXISTS idx_v100_workspace_status
                    ON v100_workspace_items(session_id, status, kind)""",
                """INSERT INTO v82_schema_migrations(version, applied_at)
                    VALUES (100, EXTRACT(EPOCH FROM NOW())) ON CONFLICT(version) DO NOTHING""",
            ]
            with self.foundation.connection() as conn:
                for statement in statements:
                    conn.execute(statement)
        else:
            with self.foundation.connection() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS v100_workspace_items (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        project_name TEXT NOT NULL DEFAULT 'General',
                        kind TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL DEFAULT '',
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        version INTEGER NOT NULL DEFAULT 1,
                        pinned INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_v100_workspace_session
                        ON v100_workspace_items(session_id, project_name, updated_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_v100_workspace_status
                        ON v100_workspace_items(session_id, status, kind);
                    INSERT OR IGNORE INTO v82_schema_migrations(version, applied_at)
                        VALUES (100, strftime('%s','now'));
                    """
                )
        self._schema_ready = True

    def _ensure_schema(self) -> None:
        if not self._schema_ready:
            self.init_schema()

    def _normalize_item(self, row: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(row)
        item["metadata"] = _safe_json(item.pop("metadata_json", {}), {})
        item["pinned"] = bool(item.get("pinned"))
        item["version"] = int(item.get("version") or 1)
        return item

    def list_items(
        self,
        session_id: str,
        *,
        project_name: str = "",
        kind: str = "",
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        self._ensure_schema()
        p = self._p()
        clauses = [f"session_id={p}", "status='active'"]
        values: List[Any] = [session_id]
        if project_name:
            clauses.append(f"project_name={p}")
            values.append(_clean_text(project_name, 120))
        if kind:
            clean_kind = str(kind).strip().lower()
            if clean_kind not in WORKSPACE_KINDS:
                raise ValueError("Tipo de elemento no permitido.")
            clauses.append(f"kind={p}")
            values.append(clean_kind)
        values.append(max(1, min(int(limit), 200)))
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT * FROM v100_workspace_items
                        WHERE {' AND '.join(clauses)}
                        ORDER BY pinned DESC, updated_at DESC LIMIT {p}""",
                    tuple(values),
                )
            )
        return [self._normalize_item(row) for row in rows]

    def get_item(self, session_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_schema()
        p = self._p()
        with self.foundation.connection() as conn:
            rows = self.foundation._dict_rows(
                conn.execute(
                    f"""SELECT * FROM v100_workspace_items
                        WHERE id={p} AND session_id={p} AND status='active'""",
                    (item_id, session_id),
                )
            )
        return self._normalize_item(rows[0]) if rows else None

    def create_item(
        self,
        session_id: str,
        *,
        title: str,
        content: str,
        kind: str = "document",
        project_name: str = "General",
        metadata: Optional[Dict[str, Any]] = None,
        pinned: bool = False,
    ) -> Dict[str, Any]:
        self._ensure_schema()
        clean_kind = str(kind or "document").strip().lower()
        if clean_kind not in WORKSPACE_KINDS:
            raise ValueError("Tipo de elemento no permitido.")
        clean_title = _clean_text(title, 300)
        if not clean_title:
            raise ValueError("El elemento necesita un título.")
        clean_content = str(content or "")[:200_000]
        if not clean_content:
            raise ValueError("El elemento necesita contenido.")
        now = time.time()
        item_id = str(uuid.uuid4())
        p = self._p()
        payload = (
            item_id,
            session_id,
            _clean_text(project_name, 120) or "General",
            clean_kind,
            clean_title,
            clean_content,
            self.foundation._json_value(metadata or {}),
            1,
            bool(pinned) if self.driver == "postgresql" else int(bool(pinned)),
            "active",
            now,
            now,
        )
        with self.foundation.connection() as conn:
            conn.execute(
                f"""INSERT INTO v100_workspace_items(
                    id,session_id,project_name,kind,title,content,metadata_json,
                    version,pinned,status,created_at,updated_at)
                    VALUES ({','.join([p] * 12)})""",
                payload,
            )
        return self.get_item(session_id, item_id) or {}

    def update_item(
        self,
        session_id: str,
        item_id: str,
        values: Dict[str, Any],
    ) -> Dict[str, Any]:
        current = self.get_item(session_id, item_id)
        if not current:
            raise KeyError("Elemento no encontrado.")
        kind = str(values.get("kind", current["kind"])).strip().lower()
        if kind not in WORKSPACE_KINDS:
            raise ValueError("Tipo de elemento no permitido.")
        title = _clean_text(values.get("title", current["title"]), 300)
        content = str(values.get("content", current["content"]))[:200_000]
        project_name = _clean_text(values.get("project_name", current["project_name"]), 120) or "General"
        metadata = values.get("metadata", current.get("metadata") or {})
        pinned = bool(values.get("pinned", current.get("pinned")))
        if not title or not content:
            raise ValueError("Título y contenido son obligatorios.")
        p = self._p()
        with self.foundation.connection() as conn:
            conn.execute(
                f"""UPDATE v100_workspace_items SET
                    project_name={p},kind={p},title={p},content={p},metadata_json={p},
                    version=version+1,pinned={p},updated_at={p}
                    WHERE id={p} AND session_id={p} AND status='active'""",
                (
                    project_name,
                    kind,
                    title,
                    content,
                    self.foundation._json_value(metadata if isinstance(metadata, dict) else {}),
                    pinned if self.driver == "postgresql" else int(pinned),
                    time.time(),
                    item_id,
                    session_id,
                ),
            )
        return self.get_item(session_id, item_id) or {}

    def delete_item(self, session_id: str, item_id: str) -> bool:
        self._ensure_schema()
        p = self._p()
        with self.foundation.connection() as conn:
            cursor = conn.execute(
                f"""UPDATE v100_workspace_items SET status='deleted',updated_at={p}
                    WHERE id={p} AND session_id={p} AND status='active'""",
                (time.time(), item_id, session_id),
            )
        return bool(cursor.rowcount)

    @staticmethod
    def route_preview(message: str, mode: str = "auto", has_files: bool = False) -> Dict[str, Any]:
        text = str(message or "").strip().lower()
        requested_mode = str(mode or "auto").strip().lower()
        current_terms = (
            "hoy", "actual", "últim", "reciente", "noticia", "precio", "clima",
            "presidente", "ley", "versión", "horario", "resultado",
        )
        research_terms = ("investiga", "fuentes", "compara", "verifica", "informe", "mercado")
        coding_terms = ("código", "programa", "función", "bug", "error", "api", "python", "javascript")
        mission_terms = ("planifica", "misión", "objetivo", "automatiza", "monitorea", "cada día")
        math_only = bool(re.fullmatch(r"[\d\s()+\-*/.,%^=x²³]+", text)) and bool(re.search(r"\d", text))
        web_required = requested_mode == "research" or any(term in text for term in current_terms)
        if math_only or requested_mode == "math":
            strategy, tools = "local_math", ["calculator", "sympy_solver"]
        elif has_files:
            strategy, tools = "document_intelligence", ["document_reader", "semantic_search"]
        elif requested_mode == "research" or any(term in text for term in research_terms):
            strategy, tools = "deep_research", ["web_search", "public_page_reader", "quality_gate"]
        elif any(term in text for term in coding_terms):
            strategy, tools = "code_solution", ["model_router", "code_lab", "quality_gate"]
        elif any(term in text for term in mission_terms):
            strategy, tools = "autonomous_mission", ["planner", "jobs", "approvals"]
        else:
            strategy, tools = "conversation", ["memory_search", "model_router"]
        return {
            "strategy": strategy,
            "tools": tools,
            "web_required": web_required,
            "mode": requested_mode if requested_mode in {"auto", "fast", "research", "math", "professional"} else "auto",
            "budget": {
                "max_provider_attempts": 3 if strategy == "deep_research" else 2,
                "max_sources": 10 if strategy == "deep_research" else 0,
                "background_recommended": strategy in {"deep_research", "autonomous_mission"},
            },
        }

    def briefing(self, session_id: str, project_name: str = "General") -> Dict[str, Any]:
        items = self.list_items(session_id, project_name=project_name, limit=200)
        kinds = Counter(item["kind"] for item in items)
        recent = items[:6]
        return {
            "project_name": project_name or "General",
            "workspace_items": len(items),
            "by_kind": dict(kinds),
            "recent": recent,
            "suggested_actions": [
                {"id": "continue", "label": "Continuar el trabajo reciente"},
                {"id": "research", "label": "Iniciar investigación con fuentes"},
                {"id": "mission", "label": "Convertir un objetivo en misión"},
                {"id": "review", "label": "Revisar memoria y tareas pendientes"},
            ],
        }

    def status(self, session_id: str = "default_session") -> Dict[str, Any]:
        try:
            self._ensure_schema()
            items = self.list_items(session_id, limit=200)
            connected = True
            detail = ""
        except Exception as exc:
            items = []
            connected = False
            detail = f"{type(exc).__name__}: {str(exc)[:180]}"
        return {
            "version": V100_VERSION,
            "connected": connected,
            "driver": self.driver,
            "workspace_items": len(items),
            "stages": V100_STAGES,
            "detail": detail,
            "safety": {
                "external_writes_require_approval": True,
                "self_deployment": False,
                "bounded_retries": True,
            },
        }

