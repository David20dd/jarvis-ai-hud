from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

import httpx

try:
    from psycopg_pool import ConnectionPool
    from psycopg.types.json import Jsonb
except ImportError:  # PostgreSQL is optional; SQLite remains a complete fallback.
    ConnectionPool = None  # type: ignore
    Jsonb = None  # type: ignore


SCHEMA_VERSION = 82


def _now() -> float:
    return time.time()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _safe_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-záéíóúüñ0-9]{2,}", str(text or "").lower())


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    lnorm = math.sqrt(sum(value * value for value in left))
    rnorm = math.sqrt(sum(value * value for value in right))
    return dot / (lnorm * rnorm) if lnorm and rnorm else 0.0


class EmbeddingService:
    """Embeddings with a private local fallback.

    The local projection is deterministic and useful for similarity/caching.  When
    OpenAI is explicitly configured it uses a real semantic embedding model.
    """

    def __init__(
        self,
        provider: str = "local",
        *,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
        dimensions: int = 256,
        timeout_seconds: float = 20,
    ):
        requested = str(provider or "local").strip().lower()
        self.provider = "openai" if requested == "openai" and api_key else "local"
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model.strip() or "text-embedding-3-small"
        self.dimensions = max(64, min(int(dimensions or 256), 3072))
        self.timeout_seconds = max(5.0, min(float(timeout_seconds or 20), 90.0))

    @property
    def signature(self) -> str:
        return f"{self.provider}:{self.model if self.provider == 'openai' else 'projection'}:{self.dimensions}"

    def _local_embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        words = _tokens(text)
        features = words + [f"{words[index]}_{words[index + 1]}" for index in range(max(0, len(words) - 1))]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * (1.25 if "_" in feature else 1.0)
        norm = math.sqrt(sum(value * value for value in vector))
        return [round(value / norm, 8) for value in vector] if norm else vector

    def embed(self, text: str) -> List[float]:
        content = str(text or "").strip()
        if not content:
            return [0.0] * self.dimensions
        if self.provider != "openai":
            return self._local_embed(content)
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": content, "dimensions": self.dimensions},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        vector = list((payload.get("data") or [{}])[0].get("embedding") or [])
        if not vector:
            raise RuntimeError("El proveedor de embeddings no devolvió un vector.")
        return [float(value) for value in vector]

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model if self.provider == "openai" else "private-local-projection",
            "dimensions": self.dimensions,
            "external": self.provider == "openai",
            "configured": True,
        }


class DataFoundation:
    """v82 persistence layer.

    It uses PostgreSQL/pgvector when DATABASE_URL is present and otherwise creates
    the same v82 tables in SQLite.  Legacy SQLite tables remain untouched.
    """

    def __init__(
        self,
        *,
        database_url: str,
        sqlite_file: str,
        embeddings: EmbeddingService,
        persistent_declared: bool = False,
    ):
        self.database_url = str(database_url or "").strip()
        self.sqlite_file = str(sqlite_file or "jarvis_memory.db")
        self.embeddings = embeddings
        self.persistent_declared = bool(persistent_declared)
        self.driver = "postgresql" if self.database_url else "sqlite"
        self._pool: Any = None
        self._schema_ready = False
        self._vector_available = False
        self._lock = threading.RLock()

    def _ensure_pool(self) -> None:
        if self.driver != "postgresql":
            return
        if ConnectionPool is None:
            raise RuntimeError("DATABASE_URL está configurada, pero falta psycopg[binary,pool].")
        if self._pool is None:
            self._pool = ConnectionPool(
                conninfo=self.database_url,
                min_size=1,
                max_size=6,
                timeout=10,
                kwargs={"autocommit": False},
                open=True,
            )

    @contextmanager
    def connection(self) -> Iterator[Any]:
        if self.driver == "postgresql":
            self._ensure_pool()
            with self._pool.connection() as conn:
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            return
        path = Path(self.sqlite_file).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _dict_rows(cursor: Any) -> List[Dict[str, Any]]:
        rows = cursor.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], sqlite3.Row):
            return [dict(row) for row in rows]
        columns = [getattr(item, "name", item[0]) for item in (cursor.description or [])]
        return [dict(zip(columns, row)) for row in rows]

    def _execute_script(self, statements: Iterable[str]) -> None:
        with self.connection() as conn:
            for statement in statements:
                cleaned = statement.strip()
                if cleaned:
                    conn.execute(cleaned)

    def init_schema(self) -> None:
        with self._lock:
            if self.driver == "postgresql":
                self._init_postgres()
            else:
                self._init_sqlite()
            self._schema_ready = True

    def _init_sqlite(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS v82_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v82_conversations (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL UNIQUE,
                    project_name TEXT NOT NULL DEFAULT 'General',
                    title TEXT NOT NULL DEFAULT 'Nueva conversación',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v82_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES v82_conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_v82_messages_session
                    ON v82_messages(session_id, created_at);
                CREATE TABLE IF NOT EXISTS v82_memory (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_name TEXT NOT NULL DEFAULT 'General',
                    memory_type TEXT NOT NULL DEFAULT 'fact',
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'user',
                    importance INTEGER NOT NULL DEFAULT 3,
                    confidence REAL NOT NULL DEFAULT 0.7,
                    expires_at REAL NOT NULL DEFAULT 0,
                    embedding_json TEXT NOT NULL DEFAULT '[]',
                    embedding_signature TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_v82_memory_session
                    ON v82_memory(session_id, project_name, updated_at);
                CREATE TABLE IF NOT EXISTS v82_tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 5,
                    progress INTEGER NOT NULL DEFAULT 0,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_run_at REAL NOT NULL DEFAULT 0,
                    lease_until REAL NOT NULL DEFAULT 0,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_v82_tasks_queue
                    ON v82_tasks(status, next_run_at, priority, created_at);
                CREATE TABLE IF NOT EXISTS v82_preferences (
                    session_id TEXT PRIMARY KEY,
                    preferences_json TEXT NOT NULL DEFAULT '{}',
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v82_research (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v82_import_ledger (
                    source_key TEXT PRIMARY KEY,
                    imported_at REAL NOT NULL
                );
                INSERT OR IGNORE INTO v82_schema_migrations(version, applied_at)
                VALUES (82, strftime('%s','now'));
                """
            )

    def _init_postgres(self) -> None:
        self._ensure_pool()
        with self.connection() as conn:
            try:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                self._vector_available = True
            except Exception:
                conn.rollback()
                self._vector_available = False
            statements = [
                """CREATE TABLE IF NOT EXISTS v82_schema_migrations (
                    version INTEGER PRIMARY KEY, applied_at DOUBLE PRECISION NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS v82_conversations (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL UNIQUE, project_name TEXT NOT NULL DEFAULT 'General',
                    title TEXT NOT NULL DEFAULT 'Nueva conversación',
                    created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS v82_messages (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES v82_conversations(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at DOUBLE PRECISION NOT NULL)""",
                "CREATE INDEX IF NOT EXISTS idx_v82_messages_session ON v82_messages(session_id, created_at)",
                """CREATE TABLE IF NOT EXISTS v82_memory (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, project_name TEXT NOT NULL DEFAULT 'General',
                    memory_type TEXT NOT NULL DEFAULT 'fact', content TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'user',
                    importance INTEGER NOT NULL DEFAULT 3, confidence DOUBLE PRECISION NOT NULL DEFAULT 0.7,
                    expires_at DOUBLE PRECISION NOT NULL DEFAULT 0, embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    embedding_signature TEXT NOT NULL DEFAULT '', created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL)""",
                "CREATE INDEX IF NOT EXISTS idx_v82_memory_session ON v82_memory(session_id, project_name, updated_at)",
                """CREATE INDEX IF NOT EXISTS idx_v82_memory_text ON v82_memory
                    USING GIN (to_tsvector('simple', content))""",
                """CREATE TABLE IF NOT EXISTS v82_tasks (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, task_type TEXT NOT NULL, title TEXT NOT NULL,
                    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb, status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 5, progress INTEGER NOT NULL DEFAULT 0,
                    attempt INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_run_at DOUBLE PRECISION NOT NULL DEFAULT 0, lease_until DOUBLE PRECISION NOT NULL DEFAULT 0,
                    result_json JSONB NOT NULL DEFAULT '{}'::jsonb, error TEXT NOT NULL DEFAULT '',
                    created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
                "CREATE INDEX IF NOT EXISTS idx_v82_tasks_queue ON v82_tasks(status, next_run_at, priority, created_at)",
                """CREATE TABLE IF NOT EXISTS v82_preferences (
                    session_id TEXT PRIMARY KEY, preferences_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at DOUBLE PRECISION NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS v82_research (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, query TEXT NOT NULL, status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '', sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS v82_import_ledger (
                    source_key TEXT PRIMARY KEY, imported_at DOUBLE PRECISION NOT NULL)""",
                """INSERT INTO v82_schema_migrations(version, applied_at) VALUES (82, EXTRACT(EPOCH FROM NOW()))
                    ON CONFLICT(version) DO NOTHING""",
            ]
            for statement in statements:
                conn.execute(statement)
            if self._vector_available:
                dimensions = max(1, int(self.embeddings.dimensions))
                conn.execute(
                    f"ALTER TABLE v82_memory ADD COLUMN IF NOT EXISTS embedding_vector vector({dimensions})"
                )
                conn.execute(
                    """CREATE INDEX IF NOT EXISTS idx_v82_memory_embedding_hnsw
                    ON v82_memory USING hnsw (embedding_vector vector_cosine_ops)"""
                )

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def _placeholder(self) -> str:
        return "%s" if self.driver == "postgresql" else "?"

    def _json_value(self, value: Any) -> Any:
        if self.driver == "postgresql":
            if Jsonb is None:
                raise RuntimeError("Falta el adaptador JSONB de psycopg.")
            return Jsonb(value)
        return _json(value)

    def status(self) -> Dict[str, Any]:
        connected = False
        detail = ""
        counts = {"conversations": 0, "messages": 0, "memories": 0, "tasks": 0}
        try:
            if not self._schema_ready:
                self.init_schema()
            with self.connection() as conn:
                conn.execute("SELECT 1").fetchone()
                for label, table in (
                    ("conversations", "v82_conversations"),
                    ("messages", "v82_messages"),
                    ("memories", "v82_memory"),
                    ("tasks", "v82_tasks"),
                ):
                    counts[label] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            connected = True
        except Exception as exc:
            detail = f"{type(exc).__name__}: {str(exc)[:180]}"
        return {
            "version": SCHEMA_VERSION,
            "driver": self.driver,
            "configured": bool(self.database_url) if self.driver == "postgresql" else True,
            "connected": connected,
            "durable": self.driver == "postgresql" or self.persistent_declared,
            "vector_extension": self._vector_available,
            "vector_index": bool(self.driver == "postgresql" and self._vector_available),
            "schema_ready": self._schema_ready,
            "counts": counts,
            "embedding": self.embeddings.status(),
            "detail": detail,
        }

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        project_name: str = "General",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _now()
        conversation_id = hashlib.sha256(f"v82:{session_id}".encode("utf-8")).hexdigest()[:32]
        message_id = str(uuid.uuid4())
        owner_id = session_id.split(":", 2)[1] if session_id.startswith("web:") and session_id.count(":") >= 2 else ""
        suggested_title = re.sub(r"\s+", " ", content or "").strip()[:80] if role == "user" else ""
        p = self._placeholder()
        with self.connection() as conn:
            if self.driver == "postgresql":
                conn.execute(
                    """INSERT INTO v82_conversations(id, owner_id, session_id, project_name, title, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(session_id) DO UPDATE SET
                        owner_id=CASE WHEN v82_conversations.owner_id='' THEN EXCLUDED.owner_id ELSE v82_conversations.owner_id END,
                        project_name=EXCLUDED.project_name,
                        title=CASE WHEN v82_conversations.title='Nueva conversación' AND EXCLUDED.title<>'Nueva conversación'
                            THEN EXCLUDED.title ELSE v82_conversations.title END,
                        updated_at=EXCLUDED.updated_at""",
                    (conversation_id, owner_id, session_id, project_name, suggested_title or "Nueva conversación", now, now),
                )
            else:
                conn.execute(
                    """INSERT INTO v82_conversations(id, owner_id, session_id, project_name, title, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        owner_id=CASE WHEN v82_conversations.owner_id='' THEN excluded.owner_id ELSE v82_conversations.owner_id END,
                        project_name=excluded.project_name,
                        title=CASE WHEN v82_conversations.title='Nueva conversación' AND excluded.title<>'Nueva conversación'
                            THEN excluded.title ELSE v82_conversations.title END,
                        updated_at=excluded.updated_at""",
                    (conversation_id, owner_id, session_id, project_name, suggested_title or "Nueva conversación", now, now),
                )
            metadata_value = self._json_value(metadata or {})
            conn.execute(
                f"""INSERT INTO v82_messages(id, conversation_id, session_id, role, content, metadata_json, created_at)
                VALUES ({','.join([p] * 7)})""",
                (message_id, conversation_id, session_id, role, content, metadata_value, now),
            )
        return {"id": message_id, "conversation_id": conversation_id}

    def list_conversations(self, owner_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        """Return server-synchronised conversations without exposing other owners."""
        p = self._placeholder()
        owner = str(owner_id or "").strip()[:160]
        with self.connection() as conn:
            rows = self._dict_rows(
                conn.execute(
                    f"""SELECT c.id,c.owner_id,c.session_id,c.project_name,c.title,c.created_at,c.updated_at,
                        COUNT(m.id) AS message_count
                    FROM v82_conversations c LEFT JOIN v82_messages m ON m.conversation_id=c.id
                    WHERE c.owner_id={p} OR (c.owner_id='' AND c.session_id LIKE {p})
                    GROUP BY c.id,c.owner_id,c.session_id,c.project_name,c.title,c.created_at,c.updated_at
                    ORDER BY c.updated_at DESC LIMIT {p}""",
                    (owner, f"web:{owner}:%", max(1, min(int(limit), 250))),
                )
            )
        return rows

    def conversation_messages(self, owner_id: str, conversation_id: str, *, limit: int = 500) -> List[Dict[str, Any]]:
        p = self._placeholder()
        owner = str(owner_id or "").strip()[:160]
        with self.connection() as conn:
            allowed = conn.execute(
                f"""SELECT id FROM v82_conversations
                WHERE id={p} AND (owner_id={p} OR (owner_id='' AND session_id LIKE {p}))""",
                (conversation_id, owner, f"web:{owner}:%"),
            ).fetchone()
            if not allowed:
                return []
            rows = self._dict_rows(
                conn.execute(
                    f"""SELECT id,role,content,metadata_json,created_at FROM v82_messages
                    WHERE conversation_id={p} ORDER BY created_at ASC LIMIT {p}""",
                    (conversation_id, max(1, min(int(limit), 2000))),
                )
            )
        for row in rows:
            row["metadata"] = _safe_json(row.pop("metadata_json", {}), {})
        return rows

    def update_conversation(self, owner_id: str, conversation_id: str, *, title: str = "", project_name: str = "") -> bool:
        p = self._placeholder()
        values: List[Any] = []
        updates: List[str] = []
        if title:
            updates.append(f"title={p}")
            values.append(re.sub(r"\s+", " ", title).strip()[:120])
        if project_name:
            updates.append(f"project_name={p}")
            values.append(re.sub(r"\s+", " ", project_name).strip()[:120])
        if not updates:
            return False
        updates.append(f"updated_at={p}")
        values.append(_now())
        values.extend([conversation_id, owner_id, f"web:{owner_id}:%"])
        with self.connection() as conn:
            cursor = conn.execute(
                f"""UPDATE v82_conversations SET {','.join(updates)}
                WHERE id={p} AND (owner_id={p} OR (owner_id='' AND session_id LIKE {p}))""",
                tuple(values),
            )
            return bool(cursor.rowcount)

    def delete_conversation(self, owner_id: str, conversation_id: str) -> bool:
        p = self._placeholder()
        with self.connection() as conn:
            cursor = conn.execute(
                f"""DELETE FROM v82_conversations
                WHERE id={p} AND (owner_id={p} OR (owner_id='' AND session_id LIKE {p}))""",
                (conversation_id, owner_id, f"web:{owner_id}:%"),
            )
            return bool(cursor.rowcount)

    def save_memory(
        self,
        session_id: str,
        content: str,
        *,
        project_name: str = "General",
        memory_type: str = "fact",
        source: str = "user",
        importance: int = 3,
        confidence: float = 0.7,
        expires_at: float = 0,
    ) -> Dict[str, Any]:
        clean = re.sub(r"\s+", " ", str(content or "")).strip()
        if not clean:
            raise ValueError("La memoria no puede estar vacía.")
        vector = self.embeddings.embed(clean)
        memory_id = str(uuid.uuid4())
        now = _now()
        p = self._placeholder()
        embedding_value = self._json_value(vector)
        with self.connection() as conn:
            values = (
                memory_id, session_id, project_name[:120], memory_type[:60], clean, source[:120],
                max(1, min(int(importance), 5)), max(0.0, min(float(confidence), 1.0)),
                max(0.0, float(expires_at or 0)), embedding_value, self.embeddings.signature, now, now,
            )
            if self.driver == "postgresql" and self._vector_available:
                vector_literal = "[" + ",".join(f"{float(item):.10g}" for item in vector) + "]"
                conn.execute(
                    """INSERT INTO v82_memory(
                    id,session_id,project_name,memory_type,content,source,importance,confidence,
                    expires_at,embedding_json,embedding_signature,created_at,updated_at,embedding_vector)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)""",
                    (*values, vector_literal),
                )
            else:
                conn.execute(
                    f"""INSERT INTO v82_memory(
                        id,session_id,project_name,memory_type,content,source,importance,confidence,
                        expires_at,embedding_json,embedding_signature,created_at,updated_at)
                        VALUES ({','.join([p] * 13)})""",
                    values,
                )
        return {
            "id": memory_id,
            "content": clean,
            "project_name": project_name,
            "memory_type": memory_type,
            "embedding": self.embeddings.signature,
        }

    def list_memories(self, session_id: str, *, project_name: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        p = self._placeholder()
        now = _now()
        query = f"""SELECT id,session_id,project_name,memory_type,content,source,importance,confidence,
            expires_at,embedding_signature,created_at,updated_at FROM v82_memory
            WHERE session_id={p} AND (expires_at=0 OR expires_at>{p})"""
        params: List[Any] = [session_id, now]
        if project_name:
            query += f" AND project_name={p}"
            params.append(project_name)
        query += f" ORDER BY importance DESC, updated_at DESC LIMIT {p}"
        params.append(max(1, min(int(limit), 200)))
        with self.connection() as conn:
            return self._dict_rows(conn.execute(query, tuple(params)))

    def search_memory(
        self,
        session_id: str,
        query: str,
        *,
        project_name: str = "",
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        wanted = set(_tokens(query))
        vector = self.embeddings.embed(query)
        p = self._placeholder()
        if self.driver == "postgresql" and self._vector_available:
            vector_literal = "[" + ",".join(f"{float(item):.10g}" for item in vector) + "]"
            filters = "session_id=%s AND (expires_at=0 OR expires_at>%s) AND embedding_vector IS NOT NULL AND embedding_signature=%s"
            params: List[Any] = [vector_literal, query, session_id, _now(), self.embeddings.signature]
            if project_name:
                filters += " AND project_name=%s"
                params.append(project_name)
            params.append(max(1, min(int(limit), 50)))
            sql = f"""SELECT id,project_name,memory_type,content,source,importance,confidence,updated_at,
                GREATEST(0, 1 - (embedding_vector <=> %s::vector)) AS semantic_score,
                ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', %s)) AS lexical_score,
                (GREATEST(0, 1 - (embedding_vector <=> %s::vector)) * 0.62 +
                 LEAST(1, ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', %s)) * 4) * 0.28 +
                 (importance::double precision / 5.0) * 0.10) AS score
                FROM v82_memory WHERE {filters}
                ORDER BY score DESC, updated_at DESC LIMIT %s"""
            pg_params = [vector_literal, query, vector_literal, query, *params[2:]]
            with self.connection() as conn:
                rows = self._dict_rows(conn.execute(sql, tuple(pg_params)))
            for row in rows:
                row["score"] = round(float(row.get("score") or 0), 5)
                row["lexical_score"] = round(float(row.get("lexical_score") or 0), 5)
                row["semantic_score"] = round(float(row.get("semantic_score") or 0), 5)
            return rows
        sql = f"""SELECT id,project_name,memory_type,content,source,importance,confidence,
            embedding_json,embedding_signature,updated_at FROM v82_memory
            WHERE session_id={p} AND (expires_at=0 OR expires_at>{p})"""
        params: List[Any] = [session_id, _now()]
        if project_name:
            sql += f" AND project_name={p}"
            params.append(project_name)
        sql += " ORDER BY importance DESC, updated_at DESC"
        with self.connection() as conn:
            rows = self._dict_rows(conn.execute(sql, tuple(params)))
        ranked: List[Dict[str, Any]] = []
        for row in rows:
            existing = _safe_json(row.pop("embedding_json", []), [])
            content_tokens = set(_tokens(row.get("content", "")))
            lexical = len(wanted & content_tokens) / max(1, len(wanted))
            semantic = _cosine(vector, [float(value) for value in existing]) if row.get("embedding_signature") == self.embeddings.signature else 0.0
            importance = max(0.0, min(float(row.get("importance", 3)) / 5.0, 1.0))
            score = lexical * 0.47 + max(0.0, semantic) * 0.43 + importance * 0.10
            if score > 0 or not wanted:
                row["score"] = round(score, 5)
                row["lexical_score"] = round(lexical, 5)
                row["semantic_score"] = round(semantic, 5)
                ranked.append(row)
        ranked.sort(key=lambda item: (item["score"], item.get("updated_at", 0)), reverse=True)
        return ranked[: max(1, min(int(limit), 50))]

    def delete_memory(self, session_id: str, memory_id: str) -> bool:
        p = self._placeholder()
        with self.connection() as conn:
            cursor = conn.execute(f"DELETE FROM v82_memory WHERE id={p} AND session_id={p}", (memory_id, session_id))
            return bool(cursor.rowcount)

    def enqueue_task(
        self,
        session_id: str,
        task_type: str,
        title: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 5,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())
        now = _now()
        p = self._placeholder()
        payload_value = self._json_value(payload or {})
        result_value = self._json_value({})
        with self.connection() as conn:
            conn.execute(
                f"""INSERT INTO v82_tasks(
                    id,session_id,task_type,title,payload_json,status,priority,progress,attempt,max_attempts,
                    next_run_at,lease_until,result_json,error,created_at,updated_at)
                    VALUES ({','.join([p] * 16)})""",
                (
                    task_id, session_id, task_type[:80], title[:300], payload_value, "queued",
                    max(1, min(int(priority), 10)), 0, 0, max(1, min(int(max_attempts), 10)),
                    now, 0, result_value, "", now, now,
                ),
            )
        return self.get_task(session_id, task_id) or {"id": task_id, "status": "queued"}

    def get_task(self, session_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        p = self._placeholder()
        with self.connection() as conn:
            rows = self._dict_rows(conn.execute(f"SELECT * FROM v82_tasks WHERE id={p} AND session_id={p}", (task_id, session_id)))
        if not rows:
            return None
        row = rows[0]
        row["payload"] = _safe_json(row.pop("payload_json", {}), {})
        row["result"] = _safe_json(row.pop("result_json", {}), {})
        return row

    def list_tasks(self, session_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        p = self._placeholder()
        with self.connection() as conn:
            rows = self._dict_rows(
                conn.execute(
                    f"SELECT * FROM v82_tasks WHERE session_id={p} ORDER BY created_at DESC LIMIT {p}",
                    (session_id, max(1, min(int(limit), 200))),
                )
            )
        for row in rows:
            row["payload"] = _safe_json(row.pop("payload_json", {}), {})
            row["result"] = _safe_json(row.pop("result_json", {}), {})
        return rows

    def cancel_task(self, session_id: str, task_id: str) -> bool:
        p = self._placeholder()
        with self.connection() as conn:
            cursor = conn.execute(
                f"""UPDATE v82_tasks SET status='cancelled', updated_at={p}
                    WHERE id={p} AND session_id={p} AND status IN ('queued','retrying','paused')""",
                (_now(), task_id, session_id),
            )
            return bool(cursor.rowcount)

    def claim_next_task(self, worker_id: str, *, lease_seconds: int = 90) -> Optional[Dict[str, Any]]:
        """Lease one due task so multiple workers cannot execute it twice."""
        now = _now()
        lease_until = now + max(15, int(lease_seconds))
        with self.connection() as conn:
            if self.driver == "postgresql":
                row = conn.execute(
                    """SELECT id,session_id FROM v82_tasks
                    WHERE status IN ('queued','retrying') AND next_run_at<=%s AND lease_until<=%s
                    ORDER BY priority DESC, created_at ASC
                    FOR UPDATE SKIP LOCKED LIMIT 1""",
                    (now, now),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT id,session_id FROM v82_tasks
                    WHERE status IN ('queued','retrying') AND next_run_at<=? AND lease_until<=?
                    ORDER BY priority DESC, created_at ASC LIMIT 1""",
                    (now, now),
                ).fetchone()
            if not row:
                return None
            task_id = row["id"] if isinstance(row, (dict, sqlite3.Row)) else row[0]
            session_id = row["session_id"] if isinstance(row, (dict, sqlite3.Row)) else row[1]
            p = self._placeholder()
            changed = conn.execute(
                f"""UPDATE v82_tasks SET status='running',lease_until={p},attempt=attempt+1,
                error='',updated_at={p} WHERE id={p} AND status IN ('queued','retrying')""",
                (lease_until, now, task_id),
            ).rowcount
            if not changed:
                return None
        task = self.get_task(str(session_id), str(task_id))
        if task is not None:
            task["worker_id"] = str(worker_id)[:120]
        return task

    def fail_task(self, session_id: str, task_id: str, error: str, *, retry_delay: int = 15) -> Dict[str, Any]:
        task = self.get_task(session_id, task_id)
        if not task:
            raise KeyError("Tarea no encontrada.")
        retry = int(task.get("attempt") or 0) < int(task.get("max_attempts") or 1)
        p = self._placeholder()
        with self.connection() as conn:
            conn.execute(
                f"""UPDATE v82_tasks SET status={p},error={p},next_run_at={p},lease_until=0,updated_at={p}
                WHERE id={p} AND session_id={p}""",
                (
                    "retrying" if retry else "failed", str(error or "")[:2000],
                    _now() + max(1, int(retry_delay)) if retry else 0, _now(), task_id, session_id,
                ),
            )
        return self.get_task(session_id, task_id) or {}

    def run_maintenance_task(self, session_id: str, task_id: str) -> Dict[str, Any]:
        task = self.get_task(session_id, task_id)
        if not task:
            raise KeyError("Tarea no encontrada.")
        if task["status"] not in {"queued", "retrying", "running"}:
            return task
        task_type = str(task.get("task_type") or "")
        p = self._placeholder()
        now = _now()
        if task["status"] != "running":
            with self.connection() as conn:
                conn.execute(
                    f"UPDATE v82_tasks SET status='running',progress=15,attempt=attempt+1,updated_at={p} WHERE id={p}",
                    (now, task_id),
                )
        result: Dict[str, Any]
        if task_type == "memory_consolidation":
            result = self.consolidate_memories(session_id)
        elif task_type == "health_snapshot":
            result = self.status()
        else:
            raise ValueError("Tipo de tarea v82 no permitido.")
        with self.connection() as conn:
            stored = self._json_value(result)
            conn.execute(
                f"""UPDATE v82_tasks SET status='completed',progress=100,result_json={p},error='',lease_until=0,updated_at={p}
                    WHERE id={p}""",
                (stored, _now(), task_id),
            )
        return self.get_task(session_id, task_id) or {}

    def consolidate_memories(self, session_id: str) -> Dict[str, Any]:
        memories = self.list_memories(session_id, limit=500)
        seen: Dict[str, str] = {}
        removed = 0
        for memory in memories:
            key = re.sub(r"\W+", " ", str(memory.get("content") or "").lower()).strip()
            if key and key in seen:
                if self.delete_memory(session_id, str(memory["id"])):
                    removed += 1
            else:
                seen[key] = str(memory["id"])
        return {"examined": len(memories), "duplicates_removed": removed, "remaining": len(memories) - removed}

    def migration_preview(self, legacy_file: str) -> Dict[str, Any]:
        path = Path(legacy_file).expanduser().resolve()
        if not path.exists():
            return {"available": False, "path": str(path), "tables": {}, "message": "No existe una base SQLite heredada."}
        tables: Dict[str, int] = {}
        source_keys: List[str] = []
        conn = sqlite3.connect(str(path), timeout=10)
        try:
            existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in ("historial", "memories", "documents", "jobs", "reminders"):
                tables[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if table in existing else 0
            if "historial" in existing:
                source_keys.extend(f"historial:{row[0]}" for row in conn.execute("SELECT id FROM historial").fetchall())
            if "memories" in existing:
                source_keys.extend(f"memories:{row[0]}" for row in conn.execute("SELECT id FROM memories").fetchall())
        finally:
            conn.close()
        pending = sum(1 for source_key in source_keys if not self._was_imported(source_key))
        return {
            "available": True,
            "path": str(path),
            "tables": tables,
            "importable": pending,
            "importable_total": len(source_keys),
            "already_imported": len(source_keys) - pending,
            "target": self.driver,
        }

    def _was_imported(self, source_key: str) -> bool:
        p = self._placeholder()
        with self.connection() as conn:
            return bool(conn.execute(f"SELECT 1 FROM v82_import_ledger WHERE source_key={p}", (source_key,)).fetchone())

    def _mark_imported(self, source_key: str) -> None:
        with self.connection() as conn:
            if self.driver == "postgresql":
                conn.execute(
                    "INSERT INTO v82_import_ledger(source_key,imported_at) VALUES (%s,%s) ON CONFLICT(source_key) DO NOTHING",
                    (source_key, _now()),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO v82_import_ledger(source_key,imported_at) VALUES (?,?)",
                    (source_key, _now()),
                )

    def migrate_from_legacy(self, legacy_file: str, *, dry_run: bool = True) -> Dict[str, Any]:
        preview = self.migration_preview(legacy_file)
        if dry_run or not preview.get("available"):
            return {**preview, "dry_run": True, "imported": {"messages": 0, "memories": 0}}
        path = Path(legacy_file).expanduser().resolve()
        conn = sqlite3.connect(str(path), timeout=30)
        conn.row_factory = sqlite3.Row
        imported_messages = 0
        imported_memories = 0
        history_rows: List[sqlite3.Row] = []
        memory_rows: List[sqlite3.Row] = []
        try:
            existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "historial" in existing:
                history_rows = conn.execute("SELECT id,session_id,role,content FROM historial ORDER BY id").fetchall()
            if "memories" in existing:
                memory_rows = conn.execute(
                    "SELECT id,session_id,category,content,importance FROM memories ORDER BY created_at"
                ).fetchall()
        finally:
            conn.close()
        for row in history_rows:
            source_key = f"historial:{row['id']}"
            if self._was_imported(source_key):
                continue
            self.append_message(row["session_id"], row["role"], row["content"], metadata={"migrated_from": "historial"})
            self._mark_imported(source_key)
            imported_messages += 1
        for row in memory_rows:
            source_key = f"memories:{row['id']}"
            if self._was_imported(source_key):
                continue
            self.save_memory(
                row["session_id"], row["content"], memory_type=row["category"],
                importance=int(row["importance"] or 3), source="legacy_sqlite", confidence=0.85,
            )
            self._mark_imported(source_key)
            imported_memories += 1
        return {
            **preview,
            "dry_run": False,
            "imported": {"messages": imported_messages, "memories": imported_memories},
        }
