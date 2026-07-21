from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TOKEN_RE = re.compile(r"[\wáéíóúüñÁÉÍÓÚÜÑ]+", re.UNICODE)
SYNONYMS = {
    "codigo": "programacion",
    "código": "programacion",
    "programar": "programacion",
    "falla": "error",
    "fallo": "error",
    "averia": "error",
    "recordar": "memoria",
    "recuerdo": "memoria",
    "preferencia": "memoria",
    "archivo": "documento",
    "pdf": "documento",
    "docx": "documento",
    "investigar": "investigacion",
    "busqueda": "investigacion",
    "búsqueda": "investigacion",
    "noticia": "actualidad",
    "noticias": "actualidad",
    "rapido": "velocidad",
    "rápido": "velocidad",
    "lento": "latencia",
    "lentitud": "latencia",
}


def _tokens(text: str) -> List[str]:
    values = []
    for raw in TOKEN_RE.findall((text or "").lower()):
        token = SYNONYMS.get(raw, raw)
        if len(token) > 2 or token.isdigit():
            values.append(token)
    return values


def _local_embedding(text: str, dimensions: int = 256) -> List[float]:
    """Deterministic, dependency-free semantic-ish fallback.

    It combines normalized terms and character trigrams. It is not presented as
    a neural embedding; it guarantees useful local retrieval when external
    embedding APIs are unavailable.
    """

    vector = [0.0] * dimensions
    terms = _tokens(text)
    features: Counter[str] = Counter(terms)
    normalized = " ".join(terms)
    for index in range(max(0, len(normalized) - 2)):
        features[f"#{normalized[index:index + 3]}"] += 0.22
    for feature, weight in features.items():
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += float(weight) * sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))


def _lexical_score(query: str, content: str) -> float:
    q = Counter(_tokens(query))
    d = Counter(_tokens(content))
    if not q or not d:
        return 0.0
    overlap = sum(min(count, d.get(token, 0)) for token, count in q.items())
    coverage = overlap / max(1, sum(q.values()))
    phrase_bonus = 0.18 if query.strip().lower() in content.lower() else 0.0
    return min(1.0, coverage + phrase_bonus)


def chunk_text(text: str, *, size: int = 1800, overlap: int = 240) -> List[str]:
    text = re.sub(r"\r\n?", "\n", text or "").strip()
    if not text:
        return []
    size = max(400, min(int(size), 6000))
    overlap = max(0, min(int(overlap), size // 3))
    chunks: List[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(len(text), cursor + size)
        if end < len(text):
            candidates = [text.rfind("\n\n", cursor, end), text.rfind(". ", cursor, end), text.rfind("\n", cursor, end)]
            split_at = max(candidates)
            if split_at > cursor + size // 2:
                end = split_at + (2 if text[split_at:split_at + 2] == ". " else 0)
        chunk = text[cursor:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        cursor = max(cursor + 1, end - overlap)
    return chunks


class SemanticIndex:
    def __init__(self, db_file: str, *, dimensions: int = 256) -> None:
        self.db_file = str(db_file)
        self.dimensions = max(64, min(int(dimensions), 1024))

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
                CREATE TABLE IF NOT EXISTS semantic_chunks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_name TEXT NOT NULL DEFAULT 'General',
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(session_id, source_type, source_id, chunk_index)
                );
                CREATE INDEX IF NOT EXISTS idx_semantic_chunks_scope
                    ON semantic_chunks(session_id, project_name, source_type, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_semantic_chunks_source
                    ON semantic_chunks(source_type, source_id);
                """
            )

    def index_source(
        self,
        *,
        session_id: str,
        project_name: str,
        source_type: str,
        source_id: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pieces = chunk_text(content)
        now = time.time()
        created = 0
        skipped = 0
        with self._connect() as conn:
            for index, piece in enumerate(pieces):
                content_hash = hashlib.sha256(piece.encode("utf-8")).hexdigest()
                existing = conn.execute(
                    """
                    SELECT id, content_hash FROM semantic_chunks
                    WHERE session_id = ? AND source_type = ? AND source_id = ? AND chunk_index = ?
                    """,
                    (session_id, source_type, source_id, index),
                ).fetchone()
                if existing and existing["content_hash"] == content_hash:
                    skipped += 1
                    continue
                embedding = _local_embedding(piece, self.dimensions)
                row_id = existing["id"] if existing else str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO semantic_chunks(
                        id, session_id, project_name, source_type, source_id, chunk_index,
                        title, content, content_hash, embedding_json, embedding_model,
                        metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'local-hybrid-v1', ?, ?, ?)
                    ON CONFLICT(session_id, source_type, source_id, chunk_index) DO UPDATE SET
                        project_name = excluded.project_name,
                        title = excluded.title,
                        content = excluded.content,
                        content_hash = excluded.content_hash,
                        embedding_json = excluded.embedding_json,
                        embedding_model = excluded.embedding_model,
                        metadata_json = excluded.metadata_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        row_id, session_id, project_name or "General", source_type, source_id,
                        index, title[:500], piece, content_hash, json.dumps(embedding),
                        json.dumps(metadata or {}, ensure_ascii=False), now, now,
                    ),
                )
                created += 1
            conn.execute(
                """
                DELETE FROM semantic_chunks
                WHERE session_id = ? AND source_type = ? AND source_id = ? AND chunk_index >= ?
                """,
                (session_id, source_type, source_id, len(pieces)),
            )
        return {"indexed": created, "unchanged": skipped, "chunks": len(pieces), "model": "local-hybrid-v1"}

    def delete_source(self, session_id: str, source_type: str, source_id: str) -> int:
        with self._connect() as conn:
            return int(conn.execute(
                "DELETE FROM semantic_chunks WHERE session_id = ? AND source_type = ? AND source_id = ?",
                (session_id, source_type, source_id),
            ).rowcount)

    def search(
        self,
        *,
        session_id: str,
        query: str,
        project_name: str = "",
        source_types: Optional[Iterable[str]] = None,
        limit: int = 8,
        candidate_limit: int = 600,
    ) -> Dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return {"query": query, "matches": [], "model": "local-hybrid-v1"}
        limit = max(1, min(int(limit), 30))
        clauses = ["session_id = ?"]
        params: List[Any] = [session_id]
        if project_name:
            clauses.append("project_name = ?")
            params.append(project_name)
        normalized_types = [str(item).strip() for item in (source_types or []) if str(item).strip()]
        if normalized_types:
            placeholders = ",".join("?" for _ in normalized_types)
            clauses.append(f"source_type IN ({placeholders})")
            params.extend(normalized_types)
        params.append(max(20, min(int(candidate_limit), 3000)))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM semantic_chunks
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC LIMIT ?
                """,
                params,
            ).fetchall()
        query_vector = _local_embedding(query, self.dimensions)
        results: List[Dict[str, Any]] = []
        for raw in rows:
            item = dict(raw)
            vector = json.loads(item.pop("embedding_json", "[]") or "[]")
            metadata = json.loads(item.pop("metadata_json", "{}") or "{}")
            cosine = (_cosine(query_vector, vector) + 1.0) / 2.0
            lexical = _lexical_score(query, item["content"])
            recency = max(0.0, 1.0 - ((time.time() - float(item["updated_at"])) / (365 * 86400)))
            score = 0.56 * cosine + 0.38 * lexical + 0.06 * recency
            if lexical <= 0 and cosine < 0.54:
                continue
            item.update({
                "metadata": metadata,
                "score": round(score, 4),
                "semantic_score": round(cosine, 4),
                "lexical_score": round(lexical, 4),
                "excerpt": item.pop("content")[:2400],
            })
            results.append(item)
        results.sort(key=lambda row: row["score"], reverse=True)
        return {
            "query": query,
            "matches": results[:limit],
            "candidates": len(rows),
            "model": "local-hybrid-v1",
            "dimensions": self.dimensions,
        }

    def status(self, session_id: str = "") -> Dict[str, Any]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT source_type, COUNT(*) AS chunks, COUNT(DISTINCT source_id) AS sources FROM semantic_chunks WHERE session_id = ? GROUP BY source_type",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT source_type, COUNT(*) AS chunks, COUNT(DISTINCT source_id) AS sources FROM semantic_chunks GROUP BY source_type"
                ).fetchall()
        by_type = {row["source_type"]: {"chunks": int(row["chunks"]), "sources": int(row["sources"])} for row in rows}
        return {
            "backend": "sqlite-local-hybrid",
            "embedding_model": "local-hybrid-v1",
            "dimensions": self.dimensions,
            "by_type": by_type,
            "chunks": sum(item["chunks"] for item in by_type.values()),
            "sources": sum(item["sources"] for item in by_type.values()),
        }

