from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

import main
from jarvis_core.v82 import DataFoundation, EmbeddingService


def test_v82_sqlite_fallback_memory_and_tasks(tmp_path):
    foundation = DataFoundation(
        database_url="",
        sqlite_file=str(tmp_path / "v82.db"),
        embeddings=EmbeddingService("local", dimensions=128),
        persistent_declared=True,
    )
    foundation.init_schema()
    foundation.append_message("v82-unit", "user", "Hola", project_name="Pruebas")
    saved = foundation.save_memory(
        "v82-unit",
        "Prefiero respuestas claras con pasos concretos",
        project_name="Pruebas",
        memory_type="preference",
    )
    results = foundation.search_memory("v82-unit", "cómo prefiero las respuestas", limit=5)
    task = foundation.enqueue_task("v82-unit", "memory_consolidation", "Consolidar memoria")
    completed = foundation.run_maintenance_task("v82-unit", task["id"])

    status = foundation.status()
    assert status["driver"] == "sqlite"
    assert status["connected"] is True
    assert status["counts"]["messages"] == 1
    assert results and results[0]["id"] == saved["id"]
    assert results[0]["score"] > 0
    assert completed["status"] == "completed"


def test_v82_legacy_migration_is_idempotent(tmp_path):
    legacy_file = tmp_path / "legacy.db"
    with sqlite3.connect(legacy_file) as legacy:
        legacy.executescript(
            """
            CREATE TABLE historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL
            );
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                importance INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        legacy.execute(
            "INSERT INTO historial(session_id,role,content,timestamp) VALUES (?,?,?,?)",
            ("legacy-user", "user", "Mensaje heredado", time.time()),
        )
        legacy.execute(
            "INSERT INTO memories(id,session_id,category,content,importance,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            ("memory-1", "legacy-user", "preference", "Prefiero respuestas breves", 4, time.time(), time.time()),
        )

    foundation = DataFoundation(
        database_url="",
        sqlite_file=str(tmp_path / "target.db"),
        embeddings=EmbeddingService("local", dimensions=128),
        persistent_declared=True,
    )
    foundation.init_schema()
    preview = foundation.migrate_from_legacy(str(legacy_file), dry_run=True)
    first = foundation.migrate_from_legacy(str(legacy_file), dry_run=False)
    second = foundation.migrate_from_legacy(str(legacy_file), dry_run=False)

    assert preview["importable"] == 2
    assert first["imported"] == {"messages": 1, "memories": 1}
    assert second["importable"] == 0
    assert second["imported"] == {"messages": 0, "memories": 0}
    assert foundation.status()["counts"]["messages"] == 1
    assert foundation.status()["counts"]["memories"] == 1


def test_v82_api_contract():
    session_id = "v82-api-contract"
    with TestClient(main.app) as client:
        status = client.get(f"/api/v82/status?session_id={session_id}")
        saved = client.post(
            "/api/v82/memory",
            json={
                "session_id": session_id,
                "content": "JARVIS debe entregar siempre un resultado visible",
                "memory_type": "instruction",
                "importance": 5,
            },
        )
        search = client.post(
            "/api/v82/memory/search",
            json={"session_id": session_id, "query": "resultado visible", "limit": 5},
        )
        migration = client.post("/api/v82/migrate", json={"dry_run": True})

    assert status.status_code == 200
    assert status.json()["version"] == "100.0.0"
    assert status.json()["foundation"]["connected"] is True
    assert saved.status_code == 200
    assert search.status_code == 200
    assert search.json()["strategy"] == "hybrid_semantic_lexical"
    assert search.json()["results"]
    assert migration.status_code == 200
    assert migration.json()["status"] == "preview"


def test_v82_frontend_contract():
    html = Path("index.html").read_text(encoding="utf-8")
    app = Path("static/app.js").read_text(encoding="utf-8")
    css = Path("static/v82.css").read_text(encoding="utf-8")
    worker = Path("service-worker.js").read_text(encoding="utf-8")

    assert "Unified Intelligence · v100" in html
    assert "./static/v82.css?v=100.0" in html
    assert "/api/v82/status" in app
    assert "/api/v82/memory/search" in app
    assert ".v82-foundation-grid" in css
    assert "@media (max-width: 720px)" in css
    assert "jarvis-unified-workspace-v100-1" in worker

