from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import main
from jarvis_core import V104_STAGES, compact_snippet, explain_memory, lexical_score


def test_v104_helpers_are_deterministic_and_explainable():
    assert V104_STAGES[-1]["version"] == 104
    assert V104_STAGES[-1]["name"] == "Adaptive Intelligence Workspace"
    assert lexical_score("proyecto jarvis", "El proyecto JARVIS está activo") == 1.0
    assert compact_snippet("a " * 300, "a", 80).endswith("…")
    explanation = explain_memory(
        {
            "id": "m1",
            "content": "Prefiero respuestas claras",
            "importance": 5,
            "confidence": 0.9,
            "source": "usuario",
            "project_name": "General",
            "score": 0.8,
            "lexical_score": 0.5,
            "semantic_score": 0.6,
        },
        query="respuestas claras",
    )
    assert explanation["controls"]["session_isolated"] is True
    assert explanation["reasons"]


def test_v104_status_search_and_memory_explanation():
    session_id = "v104-adaptive-test"
    with TestClient(main.app) as client:
        memory = main.data_foundation.save_memory(
            session_id,
            "JARVIS debe priorizar fuentes oficiales para la investigación lunar",
            project_name="General",
            memory_type="preference",
            source="user",
            importance=5,
            confidence=0.95,
        )
        main.unified_workspace.create_item(
            session_id,
            title="Informe lunar",
            content="Comparación de fuentes oficiales sobre exploración lunar.",
            kind="document",
            project_name="General",
        )
        status = client.get("/api/v104/status", params={"session_id": session_id})
        search = client.get(
            "/api/v104/search",
            params={"session_id": session_id, "q": "investigación lunar", "limit": 20},
        )
        explain = client.get(
            f"/api/v104/memory/{memory['id']}/explain",
            params={"session_id": session_id, "q": "investigación lunar"},
        )
    assert status.status_code == 200
    assert status.json()["version"] == 104
    assert status.json()["workspace"]["global_search"] is True
    assert status.json()["guardrails"]["autonomous_production_changes"] is False
    assert search.status_code == 200
    assert {item["type"] for item in search.json()["results"]} >= {"memory", "artifact"}
    assert explain.status_code == 200
    assert explain.json()["explanation"]["id"] == memory["id"]
    assert "api_key" not in str(status.json()).lower()


def test_v104_frontend_contract_and_cache():
    html = Path("index.html").read_text(encoding="utf-8")
    static_html = Path("static/index.html").read_text(encoding="utf-8")
    css = Path("static/v104-adaptive.css").read_text(encoding="utf-8")
    js = Path("static/v104.js").read_text(encoding="utf-8")
    worker = Path("service-worker.js").read_text(encoding="utf-8")
    assert html == static_html
    for identifier in (
        "v104SidebarBtn", "v104GlobalSearchBtn", "v104SearchDialog",
        "v104SplitCanvas", "v104Progress",
    ):
        assert f'id="{identifier}"' in html
    assert "v104-adaptive.css?v=104.0" in html
    assert "v104.js?v=104.0" in html
    assert "/api/v104/search" in js
    assert "/api/v104/status" in js
    assert "v104-split-canvas" in css
    assert "@media (max-width: 620px)" in css
    assert "prefers-reduced-motion" in css
    assert "jarvis-adaptive-workspace-v104-1" in worker
    assert "v104-adaptive.css?v=104.0" in worker
    assert "v104.js?v=104.0" in worker


def test_v104_search_rejects_too_short_queries():
    with TestClient(main.app) as client:
        response = client.get("/api/v104/search", params={"session_id": "short-query", "q": "x"})
    assert response.status_code == 400

