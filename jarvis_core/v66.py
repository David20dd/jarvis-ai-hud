from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _contains(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text))


class AdaptiveDecisionEngine:
    """Selects bounded retrieval routes without spending model tokens."""

    NO_WEB = (
        "sin internet", "sin buscar", "no busques", "no investigues", "solo con lo que sabes",
        "no uses internet", "sin navegación", "sin navegacion",
    )
    FORCE_WEB = (
        "busca", "buscar", "investiga", "investigar", "verifica en internet", "consulta internet",
        "fuentes", "en línea", "en linea", "google", "últimas noticias", "ultimas noticias",
    )
    VOLATILE = (
        "hoy", "ahora", "actual", "actualmente", "reciente", "último", "ultimo", "noticias",
        "precio", "cotización", "cotizacion", "clima", "pronóstico", "pronostico", "marcador",
        "partido", "elecciones", "presidente", "ministro", "ceo", "director ejecutivo",
        "ley", "reglamento", "normativa", "versión", "version", "lanzamiento", "horario", "agenda",
        "tasa de cambio", "tipo de cambio", "inflación", "inflacion", "bolsa de valores", "criptomoneda",
    )
    MEMORY = (
        "recuerdas", "recuerdo", "preferencia", "prefiero", "mi proyecto", "hablamos", "te dije",
        "mis datos", "sobre mí", "sobre mi", "mi nombre", "nuestra conversación", "nuestra conversacion",
    )
    DOCUMENTS = (
        "documento", "archivo", "pdf", "word", "excel", "powerpoint", "biblioteca", "adjunto",
        "contrato", "informe que subí", "informe que subi",
    )
    LOW_RETRIEVAL = (
        "hola", "gracias", "buenos días", "buenos dias", "buenas tardes", "buenas noches",
    )

    def decide(
        self,
        prompt: str,
        *,
        intent: str = "general",
        mode: str = "auto",
        learned_hint: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        text = _normalize(prompt)
        intent = _normalize(intent) or "general"
        mode = _normalize(mode) or "auto"
        no_web = any(_contains(text, term) for term in self.NO_WEB)
        explicit_web = any(_contains(text, term) for term in self.FORCE_WEB)
        volatile_terms = sorted({term for term in self.VOLATILE if _contains(text, term)})
        memory_terms = sorted({term for term in self.MEMORY if _contains(text, term)})
        document_terms = sorted({term for term in self.DOCUMENTS if _contains(text, term)})
        greeting = len(text.split()) <= 8 and any(text.startswith(term) for term in self.LOW_RETRIEVAL)

        web_required = bool(not no_web and (explicit_web or volatile_terms or mode == "research" or intent == "research"))
        memory_mode = "required" if memory_terms or intent == "memory" else "relevant"
        document_mode = "required" if document_terms or intent == "documents" else "off"
        if greeting:
            memory_mode = "off"
        web_mode = "disabled" if no_web else ("required" if web_required else "off")

        reasons: List[str] = []
        if no_web:
            reasons.append("El usuario pidió trabajar sin internet.")
        elif explicit_web:
            reasons.append("La consulta solicita búsqueda o verificación explícita.")
        elif volatile_terms:
            reasons.append("La respuesta puede haber cambiado recientemente.")
        elif mode == "research" or intent == "research":
            reasons.append("El modo de investigación exige evidencia externa.")
        else:
            reasons.append("La consulta puede resolverse sin navegación obligatoria.")
        if memory_mode != "off":
            reasons.append("Se consultará memoria relevante y limitada a esta sesión.")
        if document_mode == "required":
            reasons.append("Se consultará la biblioteca del usuario.")

        learned = dict(learned_hint or {})
        default_sources = int(learned.get("recommended_sources", 6) or 6)
        max_sources = max(4, min(default_sources, 10)) if web_required else 0
        freshness = "current" if volatile_terms else ("recent" if web_required else "stable")
        confidence = 0.96 if no_web or explicit_web or volatile_terms else 0.84
        return {
            "policy_version": "66.0",
            "intent": intent,
            "mode": mode,
            "memory": memory_mode,
            "documents": document_mode,
            "web": web_mode,
            "web_required": web_required,
            "citations_required": web_required,
            "freshness": freshness,
            "max_sources": max_sources,
            "confidence": confidence,
            "volatile_terms": volatile_terms,
            "reasons": reasons,
            "user_web_override": "disabled" if no_web else "default",
            "safe_self_improvement": True,
        }


class AdaptiveLearningStore:
    """Stores outcomes and learns bounded retrieval hints; it never edits code."""

    def __init__(self, db_file: str) -> None:
        self.db_file = str(db_file)

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_file)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_file, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS adaptive_decisions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    route TEXT NOT NULL DEFAULT '',
                    memory_hits INTEGER NOT NULL DEFAULT 0,
                    web_sources INTEGER NOT NULL DEFAULT 0,
                    verified INTEGER NOT NULL DEFAULT 0,
                    quality_score REAL NOT NULL DEFAULT 0,
                    latency_ms REAL NOT NULL DEFAULT 0,
                    user_rating INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'planned',
                    created_at REAL NOT NULL,
                    completed_at REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_adaptive_session
                    ON adaptive_decisions(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_adaptive_intent
                    ON adaptive_decisions(intent, created_at);
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(adaptive_decisions)").fetchall()}
            if "user_rating" not in columns:
                conn.execute("ALTER TABLE adaptive_decisions ADD COLUMN user_rating INTEGER NOT NULL DEFAULT 0")

    def start(self, session_id: str, prompt: str, decision: Dict[str, Any]) -> str:
        item_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO adaptive_decisions(id, session_id, prompt, intent, decision_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id, session_id, prompt[:30000], str(decision.get("intent") or "general")[:80],
                    json.dumps(decision, ensure_ascii=False), time.time(),
                ),
            )
        return item_id

    def finish(
        self,
        item_id: str,
        *,
        route: str,
        memory_hits: int,
        web_sources: int,
        verified: bool,
        quality_score: float,
        latency_ms: float,
        status: str = "completed",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE adaptive_decisions
                SET route = ?, memory_hits = ?, web_sources = ?, verified = ?, quality_score = ?,
                    latency_ms = ?, status = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    route[:100], max(0, int(memory_hits)), max(0, int(web_sources)), int(bool(verified)),
                    max(0.0, min(float(quality_score), 1.0)), max(0.0, float(latency_ms)), status[:40],
                    time.time(), item_id,
                ),
            )

    def learned_hint(self, intent: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS samples,
                       COALESCE(AVG(verified), 0) AS verification_rate,
                       COALESCE(AVG(quality_score), 0) AS quality,
                       COALESCE(AVG(web_sources), 0) AS web_sources
                FROM (
                    SELECT verified, quality_score, web_sources
                    FROM adaptive_decisions
                    WHERE intent = ? AND status IN ('completed','degraded')
                    ORDER BY created_at DESC LIMIT 50
                )
                """,
                (intent[:80],),
            ).fetchone()
        data = dict(row) if row else {"samples": 0, "verification_rate": 0, "quality": 0, "web_sources": 0}
        samples = int(data.get("samples") or 0)
        verification = float(data.get("verification_rate") or 0)
        recommended = 8 if samples >= 5 and verification < 0.72 else 6
        return {**data, "recommended_sources": recommended, "bounded": True}

    def record_feedback(self, session_id: str, rating: int) -> bool:
        normalized = max(-1, min(int(rating), 1))
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, quality_score FROM adaptive_decisions WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if not row:
                return False
            quality = float(row["quality_score"] or 0)
            if normalized < 0:
                quality = min(quality, 0.45)
            elif normalized > 0:
                quality = max(quality, 0.9)
            conn.execute(
                "UPDATE adaptive_decisions SET user_rating = ?, quality_score = ?, verified = CASE WHEN ? < 0 THEN 0 ELSE verified END WHERE id = ?",
                (normalized, quality, normalized, row["id"]),
            )
        return True

    def status(self, session_id: str = "", limit: int = 12) -> Dict[str, Any]:
        where = "WHERE session_id = ?" if session_id else ""
        params: List[Any] = [session_id] if session_id else []
        with self._connect() as conn:
            summary = conn.execute(
                f"""
                SELECT COUNT(*) AS decisions,
                       COALESCE(AVG(verified), 0) AS verification_rate,
                       COALESCE(AVG(quality_score), 0) AS average_quality,
                       COALESCE(AVG(latency_ms), 0) AS average_latency_ms,
                       COALESCE(SUM(web_sources), 0) AS web_sources,
                       COALESCE(SUM(memory_hits), 0) AS memory_hits
                FROM adaptive_decisions {where}
                """,
                params,
            ).fetchone()
            recent = conn.execute(
                f"""
                SELECT id, intent, route, memory_hits, web_sources, verified, quality_score,
                       latency_ms, status, created_at
                FROM adaptive_decisions {where}
                ORDER BY created_at DESC LIMIT ?
                """,
                [*params, max(1, min(int(limit), 50))],
            ).fetchall()
        return {
            "summary": dict(summary) if summary else {},
            "recent": [dict(row) for row in recent],
            "safety": {
                "edits_own_code": False,
                "deploys_automatically": False,
                "changes_secrets": False,
                "learns_routing_statistics": True,
            },
        }

    def recommendations(self, session_id: str = "") -> List[Dict[str, Any]]:
        status = self.status(session_id, 30)["summary"]
        samples = int(status.get("decisions") or 0)
        verification = float(status.get("verification_rate") or 0)
        latency = float(status.get("average_latency_ms") or 0)
        items: List[Dict[str, Any]] = []
        if samples < 5:
            items.append({"priority": "info", "title": "Reunir más evidencia", "detail": "El criterio adaptativo necesita al menos cinco resoluciones para detectar tendencias."})
        if samples >= 5 and verification < 0.75:
            items.append({"priority": "high", "title": "Reforzar verificación", "detail": "La tasa de respuestas verificadas es menor al 75%; conviene revisar proveedores y fuentes."})
        if latency > 25000:
            items.append({"priority": "medium", "title": "Reducir latencia", "detail": "La latencia media supera 25 segundos; prioriza caché y modelos rápidos para consultas estables."})
        if not items:
            items.append({"priority": "ok", "title": "Criterio estable", "detail": "No se detectaron degradaciones que requieran cambios de configuración."})
        return items


class AnswerQualityGate:
    ERROR_MARKERS = ("traceback", "internal server error", "error desconocido", "failed to fetch")

    def evaluate(
        self,
        prompt: str,
        reply: str,
        decision: Dict[str, Any],
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        del prompt
        text = (reply or "").strip()
        evidence = dict(evidence or {})
        reasons: List[str] = []
        if len(text) < 24:
            reasons.append("respuesta demasiado breve")
        if any(marker in text.lower() for marker in self.ERROR_MARKERS):
            reasons.append("la respuesta expone un error técnico")
        web_sources = int(evidence.get("web_sources") or 0)
        citation_count = len(re.findall(r"https?://", text))
        if decision.get("web_required") and web_sources <= 0:
            reasons.append("no se obtuvo evidencia web para una consulta cambiante")
        if decision.get("citations_required") and web_sources > 0 and citation_count <= 0:
            reasons.append("faltan fuentes visibles")
        score = max(0.0, min(1.0, 1.0 - 0.22 * len(reasons)))
        return {
            "passed": not reasons,
            "verified": not reasons,
            "score": round(score, 3),
            "reasons": reasons,
            "citation_count": citation_count,
            "web_sources": web_sources,
        }


def append_source_list(reply: str, sources: Iterable[Dict[str, Any]], *, limit: int = 6) -> str:
    text = (reply or "").strip()
    if re.search(r"https?://", text):
        return text
    selected: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in sources:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        selected.append(item)
        if len(selected) >= max(1, min(int(limit), 10)):
            break
    if not selected:
        return text
    lines = [text, "", "### Fuentes consultadas"]
    for item in selected:
        title = re.sub(r"[\[\]\n\r]+", " ", str(item.get("title") or "Fuente")).strip()[:180]
        lines.append(f"- [{title}]({item.get('url')})")
    return "\n".join(lines).strip()
