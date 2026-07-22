from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import sqlite3
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlsplit

import httpx


def _now() -> float:
    return time.time()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


class GoogleSearchClient:
    """Google Programmable Search adapter with explicit quota and timeout bounds."""

    endpoint = "https://customsearch.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str = "", engine_id: str = "", timeout_seconds: int = 20) -> None:
        self.api_key = (api_key or "").strip()
        self.engine_id = (engine_id or "").strip()
        self.timeout_seconds = max(5, min(int(timeout_seconds), 60))

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.engine_id)

    def status(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "provider": "google_programmable_search",
            "engine_id_set": bool(self.engine_id),
            "api_key_set": bool(self.api_key),
        }

    def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        if not self.configured:
            raise RuntimeError("Configura GOOGLE_SEARCH_API_KEY y GOOGLE_SEARCH_ENGINE_ID.")
        limit = max(1, min(int(limit), 10))
        started = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
            response = client.get(
                self.endpoint,
                params={
                    "key": self.api_key,
                    "cx": self.engine_id,
                    "q": re.sub(r"\s+", " ", query or "").strip()[:2048],
                    "num": limit,
                    "safe": "active",
                },
                headers={"User-Agent": "JARVIS-Unified-Intelligence/65"},
            )
        if not response.is_success:
            detail = ""
            try:
                detail = str((response.json().get("error") or {}).get("message") or "")
            except Exception:
                pass
            raise RuntimeError(f"Google Search HTTP {response.status_code}: {detail}".strip())
        payload = response.json() or {}
        rows = []
        for item in payload.get("items", []) or []:
            rows.append({
                "title": str(item.get("title") or "Fuente de Google").strip(),
                "snippet": str(item.get("snippet") or "").strip(),
                "url": str(item.get("link") or "").strip(),
                "provider": "google",
            })
        return {
            "query": query,
            "results": rows,
            "provider": "google",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }


class GeminiGroundedSearchClient:
    """Gemini Google Search grounding adapter with explicit opt-in and citations."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        api_version: str = "v1beta",
        timeout_seconds: int = 35,
        enabled: bool = False,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.api_version = (api_version or "v1beta").strip().strip("/")
        self.timeout_seconds = max(10, min(int(timeout_seconds), 90))
        self.enabled = bool(enabled)

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key and self.model)

    def status(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "enabled": self.enabled,
            "provider": "gemini_google_search_grounding",
            "model": self.model,
            "api_key_set": bool(self.api_key),
        }

    def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        if not self.configured:
            raise RuntimeError("Configura GEMINI_API_KEY, JARVIS_GEMINI_SEARCH_MODEL y habilita JARVIS_GOOGLE_GROUNDING_ENABLED.")
        clean_query = re.sub(r"\s+", " ", query or "").strip()[:4000]
        if not clean_query:
            raise ValueError("La consulta de Google Search está vacía.")
        limit = max(1, min(int(limit), 10))
        endpoint = f"https://generativelanguage.googleapis.com/{self.api_version}/models/{self.model}:generateContent"
        started = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
            response = client.post(
                endpoint,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": clean_query}]}],
                    "tools": [{"google_search": {}}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1200},
                },
            )
        if not response.is_success:
            detail = ""
            try:
                detail = str((response.json().get("error") or {}).get("message") or "")
            except Exception:
                pass
            raise RuntimeError(f"Gemini Google Search HTTP {response.status_code}: {detail}".strip())
        payload = response.json() or {}
        candidates = payload.get("candidates") or []
        candidate = candidates[0] if candidates else {}
        parts = ((candidate.get("content") or {}).get("parts") or [])
        answer = "\n".join(str(part.get("text") or "").strip() for part in parts if part.get("text")).strip()
        metadata = candidate.get("groundingMetadata") or candidate.get("grounding_metadata") or {}
        chunks = metadata.get("groundingChunks") or metadata.get("grounding_chunks") or []
        rows: List[Dict[str, str]] = []
        seen = set()
        for chunk in chunks:
            web = chunk.get("web") or {}
            url = str(web.get("uri") or web.get("url") or "").strip()
            title = str(web.get("title") or "Fuente de Google").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append({
                "title": title,
                "snippet": answer[:2400],
                "url": url,
                "provider": "gemini_google",
            })
            if len(rows) >= limit:
                break
        return {
            "query": clean_query,
            "results": rows,
            "provider": "gemini_google",
            "grounded_answer": answer,
            "search_queries": metadata.get("webSearchQueries") or metadata.get("web_search_queries") or [],
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }


class _ReadableHTML(HTMLParser):
    BLOCKED = {"script", "style", "noscript", "svg", "canvas", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocked = 0
        self.title = ""
        self._in_title = False
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        lowered = tag.lower()
        if lowered in self.BLOCKED:
            self.blocked += 1
        if lowered == "title":
            self._in_title = True
        if lowered in {"p", "br", "li", "h1", "h2", "h3", "h4", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self.BLOCKED and self.blocked:
            self.blocked -= 1
        if lowered == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self.blocked or not data.strip():
            return
        clean = re.sub(r"\s+", " ", data).strip()
        if self._in_title:
            self.title = f"{self.title} {clean}".strip()
        else:
            self.parts.append(clean)

    def text(self) -> str:
        return re.sub(r"\n\s*\n+", "\n\n", " ".join(self.parts).replace(" \n ", "\n")).strip()


class PublicPageFetcher:
    """Fetches public textual pages while rejecting local/private network targets."""

    TEXT_TYPES = ("text/html", "text/plain", "application/json", "application/xml", "text/xml")

    def __init__(self, timeout_seconds: int = 15, max_bytes: int = 1_500_000) -> None:
        self.timeout_seconds = max(4, min(int(timeout_seconds), 45))
        self.max_bytes = max(100_000, min(int(max_bytes), 4_000_000))

    @staticmethod
    def _validate_url(url: str) -> str:
        parsed = urlsplit((url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Solo se permiten direcciones públicas HTTP o HTTPS.")
        if parsed.username or parsed.password:
            raise ValueError("No se permiten credenciales dentro de la URL.")
        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            raise ValueError("La dirección local no está permitida.")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))}
        except OSError as exc:
            raise ValueError("No se pudo resolver el dominio público.") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError("La dirección resuelve a una red privada o reservada.")
        return parsed.geturl()

    def fetch(self, url: str) -> Dict[str, Any]:
        current = self._validate_url(url)
        started = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
            for _ in range(4):
                response = client.get(
                    current,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; JARVIS-Research/65; +https://example.invalid)",
                        "Accept": "text/html,text/plain,application/json,application/xml;q=0.8",
                    },
                )
                if response.status_code in {301, 302, 303, 307, 308}:
                    target = response.headers.get("location", "")
                    if not target:
                        raise RuntimeError("Redirección web sin destino.")
                    current = self._validate_url(urljoin(current, target))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if not any(content_type.startswith(value) for value in self.TEXT_TYPES):
                    raise ValueError(f"Tipo de contenido no indexable: {content_type or 'desconocido'}")
                raw = response.content
                if len(raw) > self.max_bytes:
                    raw = raw[: self.max_bytes]
                encoding = response.encoding or "utf-8"
                decoded = raw.decode(encoding, errors="replace")
                title = ""
                if content_type == "text/html":
                    parser = _ReadableHTML()
                    parser.feed(decoded)
                    text = parser.text()
                    title = parser.title
                else:
                    text = decoded
                text = re.sub(r"[ \t]+", " ", text)
                text = re.sub(r"\n{3,}", "\n\n", text).strip()
                return {
                    "url": current,
                    "title": title[:500],
                    "text": text[:500_000],
                    "characters": min(len(text), 500_000),
                    "content_type": content_type,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
        raise RuntimeError("La página excedió el máximo de redirecciones.")


class ResearchLibrary:
    """Persistent, traceable evidence library for bounded web research."""

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
                CREATE TABLE IF NOT EXISTS research_runs_v65 (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_count INTEGER NOT NULL,
                    official_count INTEGER NOT NULL,
                    providers_json TEXT NOT NULL,
                    attempts_json TEXT NOT NULL,
                    limitations_json TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_sources_v65 (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    full_text TEXT NOT NULL,
                    quality REAL NOT NULL,
                    provider TEXT NOT NULL,
                    retrieved_at REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES research_runs_v65(id)
                );
                CREATE INDEX IF NOT EXISTS idx_research_runs_v65_session
                    ON research_runs_v65(session_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_research_sources_v65_run
                    ON research_sources_v65(run_id, quality DESC);
                """
            )

    def save(self, session_id: str, project_name: str, pack: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        created = _now()
        evidence = list(pack.get("evidence") or [])
        providers = sorted({str(item.get("provider") or "web") for item in evidence})
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO research_runs_v65 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id, session_id, project_name or "General", str(pack.get("query") or "")[:12000],
                    "completed" if evidence else "failed", len(evidence), int(pack.get("official_or_primary_count") or 0),
                    _json(providers), _json(pack.get("attempts") or []), _json(pack.get("limitations") or []),
                    float(pack.get("duration_ms") or 0), created,
                ),
            )
            for item in evidence:
                url = str(item.get("url") or "")[:4000]
                domain = (urlsplit(url).hostname or "").lower()
                source_key = str(item.get("id") or hashlib.sha256(url.encode()).hexdigest()[:20])
                source_id = hashlib.sha256(f"{run_id}:{source_key}".encode()).hexdigest()[:24]
                conn.execute(
                    "INSERT OR REPLACE INTO research_sources_v65 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        source_id, run_id, session_id, project_name or "General",
                        str(item.get("title") or "Fuente")[:500], url, domain,
                        str(item.get("snippet") or "")[:12000], str(item.get("full_text") or "")[:500000],
                        float(item.get("quality") or 0), str(item.get("provider") or "web")[:80],
                        float(item.get("retrieved_at") or created), _json(item.get("metadata") or {}),
                    ),
                )
        return {"run_id": run_id, "source_count": len(evidence), "providers": providers, "created_at": created}

    def list(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_runs_v65 WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, max(1, min(int(limit), 100))),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["providers"] = _load(item.pop("providers_json"), [])
            item["attempts"] = _load(item.pop("attempts_json"), [])
            item["limitations"] = _load(item.pop("limitations_json"), [])
            output.append(item)
        return output

    def get(self, run_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            run = conn.execute("SELECT * FROM research_runs_v65 WHERE id=? AND session_id=?", (run_id, session_id)).fetchone()
            if not run:
                return None
            sources = conn.execute(
                "SELECT * FROM research_sources_v65 WHERE run_id=? ORDER BY quality DESC, retrieved_at DESC", (run_id,)
            ).fetchall()
        item = dict(run)
        item["providers"] = _load(item.pop("providers_json"), [])
        item["attempts"] = _load(item.pop("attempts_json"), [])
        item["limitations"] = _load(item.pop("limitations_json"), [])
        item["sources"] = [{**dict(row), "metadata": _load(row["metadata_json"], {})} for row in sources]
        for source in item["sources"]:
            source.pop("metadata_json", None)
        return item

    def status(self, session_id: str = "") -> Dict[str, Any]:
        clauses, params = "", []
        if session_id:
            clauses, params = " WHERE session_id=?", [session_id]
        with self._connect() as conn:
            run = conn.execute(
                f"SELECT COUNT(*) runs, COALESCE(SUM(source_count),0) sources, COALESCE(SUM(official_count),0) official FROM research_runs_v65{clauses}",
                params,
            ).fetchone()
            domains = conn.execute(
                f"SELECT domain,COUNT(*) count FROM research_sources_v65{clauses} GROUP BY domain ORDER BY count DESC LIMIT 8",
                params,
            ).fetchall()
        return {
            "runs": int(run["runs"] or 0), "sources": int(run["sources"] or 0),
            "official_sources": int(run["official"] or 0), "top_domains": [dict(row) for row in domains],
        }


class ActionCenter:
    """Auditable approval queue. It stores decisions but delegates execution to an allowlisted dispatcher."""

    CATALOG: Dict[str, Dict[str, Any]] = {
        "memory.save": {"label": "Guardar memoria", "risk": "medium", "approval": True},
        "reminder.create": {"label": "Crear recordatorio", "risk": "medium", "approval": True},
        "automation.create": {"label": "Crear automatización", "risk": "medium", "approval": True},
        "telegram.notify": {"label": "Enviar mensaje por Telegram", "risk": "high", "approval": True},
    }

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
                CREATE TABLE IF NOT EXISTS actions_v65 (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    executed_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_actions_v65_session ON actions_v65(session_id,status,created_at DESC);
                """
            )

    def catalog(self) -> List[Dict[str, Any]]:
        return [{"type": key, **value} for key, value in self.CATALOG.items()]

    def create(self, session_id: str, action_type: str, title: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        definition = self.CATALOG.get(action_type)
        if not definition:
            raise ValueError("Acción no permitida por el Centro de acciones.")
        item_id, now = str(uuid.uuid4()), _now()
        status = "pending_approval" if definition["approval"] else "ready"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO actions_v65 VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)",
                (item_id, session_id, action_type, (title or definition["label"])[:300], definition["risk"], status,
                 _json(arguments or {}), "{}", "", now, now),
            )
        return self.get(item_id, session_id) or {}

    def get(self, item_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM actions_v65 WHERE id=? AND session_id=?", (item_id, session_id)).fetchone()
        return self._decode(row) if row else None

    @staticmethod
    def _decode(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["arguments"] = _load(item.pop("arguments_json"), {})
        item["result"] = _load(item.pop("result_json"), {})
        return item

    def list(self, session_id: str, status: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        query, params = "SELECT * FROM actions_v65 WHERE session_id=?", [session_id]
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode(row) for row in rows]

    def decide(self, item_id: str, session_id: str, decision: str, note: str = "") -> Dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise ValueError("La decisión debe ser approved o rejected.")
        now = _now()
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM actions_v65 WHERE id=? AND session_id=?", (item_id, session_id)).fetchone()
            if not row:
                raise KeyError("Acción no encontrada.")
            if row["status"] != "pending_approval":
                raise ValueError("La acción ya fue decidida o ejecutada.")
            conn.execute(
                "UPDATE actions_v65 SET status=?,note=?,updated_at=? WHERE id=? AND session_id=?",
                (decision, (note or "")[:2000], now, item_id, session_id),
            )
        return self.get(item_id, session_id) or {}

    def execute(self, item_id: str, session_id: str, dispatcher: Callable[[str, Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        item = self.get(item_id, session_id)
        if not item:
            raise KeyError("Acción no encontrada.")
        if item["status"] != "approved":
            raise PermissionError("Aprueba la acción antes de ejecutarla.")
        with self._connect() as conn:
            conn.execute("UPDATE actions_v65 SET status='running',updated_at=? WHERE id=?", (_now(), item_id))
        try:
            result = dispatcher(item["action_type"], item["arguments"])
            status = "completed"
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"[:1000]}
            status = "failed"
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE actions_v65 SET status=?,result_json=?,updated_at=?,executed_at=? WHERE id=?",
                (status, _json(result), now, now, item_id),
            )
        return self.get(item_id, session_id) or {}

    def status(self, session_id: str = "") -> Dict[str, int]:
        query, params = "SELECT status,COUNT(*) count FROM actions_v65", []
        if session_id:
            query += " WHERE session_id=?"
            params.append(session_id)
        query += " GROUP BY status"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {"total": sum(counts.values()), **counts}


class OperationsLedger:
    """Persistent health snapshots and bounded incident history."""

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
                CREATE TABLE IF NOT EXISTS operations_snapshots_v65 (
                    id TEXT PRIMARY KEY, score REAL NOT NULL, status TEXT NOT NULL,
                    components_json TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS incidents_v65 (
                    id TEXT PRIMARY KEY, severity TEXT NOT NULL, title TEXT NOT NULL,
                    detail TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, resolved_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_operations_snapshots_v65_time ON operations_snapshots_v65(created_at DESC);
                """
            )

    def snapshot(self, components: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        values = []
        for item in components.values():
            values.append(1.0 if item.get("ok") else (0.5 if item.get("optional") else 0.0))
        score = round(sum(values) / (len(values) or 1), 3)
        status = "healthy" if score >= 0.85 else "degraded" if score >= 0.55 else "critical"
        item = {"id": str(uuid.uuid4()), "score": score, "status": status, "components": components, "created_at": _now()}
        with self._connect() as conn:
            conn.execute("INSERT INTO operations_snapshots_v65 VALUES(?,?,?,?,?)", (item["id"], score, status, _json(components), item["created_at"]))
            conn.execute("DELETE FROM operations_snapshots_v65 WHERE created_at < ?", (_now() - 90 * 86400,))
        return item

    def history(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM operations_snapshots_v65 ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
        return [{**dict(row), "components": _load(row["components_json"], {})} for row in rows]

    def incident(self, severity: str, title: str, detail: str) -> Dict[str, Any]:
        item = {"id": str(uuid.uuid4()), "severity": severity[:20], "title": title[:300], "detail": detail[:4000], "status": "open", "created_at": _now()}
        with self._connect() as conn:
            conn.execute("INSERT INTO incidents_v65 VALUES(?,?,?,?,?,?,NULL)", (item["id"], item["severity"], item["title"], item["detail"], item["status"], item["created_at"]))
        return item

    def incidents(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM incidents_v65 ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()]


class QualitySuite:
    """Runs deterministic checks and returns an auditable score; it never edits production."""

    @staticmethod
    def run(checks: Iterable[tuple[str, Callable[[], Any]]]) -> Dict[str, Any]:
        results = []
        started = time.perf_counter()
        for name, callback in checks:
            check_started = time.perf_counter()
            try:
                value = callback()
                ok = bool(value is not False)
                detail = value if isinstance(value, (str, int, float, bool, dict, list)) else "ok"
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"[:500]
            results.append({
                "name": name, "ok": ok, "detail": detail,
                "duration_ms": round((time.perf_counter() - check_started) * 1000, 2),
            })
        passed = sum(1 for item in results if item["ok"])
        total = len(results)
        score = round(passed / (total or 1), 3)
        return {
            "status": "passed" if score == 1 else "attention",
            "score": score, "passed": passed, "total": total, "checks": results,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "automatic_production_changes": False,
        }
