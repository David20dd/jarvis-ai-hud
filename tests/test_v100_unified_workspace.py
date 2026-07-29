import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from jarvis_core import DataFoundation, EmbeddingService, UnifiedWorkspace, V100_STAGES


def test_v100_stages_are_complete_and_ordered():
    assert [stage["version"] for stage in V100_STAGES] == list(range(94, 101))
    assert V100_STAGES[-1]["name"] == "Unified Intelligence"


def test_v100_workspace_sqlite_crud_and_route_preview(tmp_path):
    foundation = DataFoundation(
        database_url="",
        sqlite_file=str(tmp_path / "v100.db"),
        embeddings=EmbeddingService("local"),
    )
    foundation.init_schema()
    workspace = UnifiedWorkspace(foundation)
    workspace.init_schema()

    created = workspace.create_item(
        "v100-unit",
        title="Informe de prueba",
        content="Hallazgos verificados.",
        kind="document",
        project_name="General",
        metadata={"source": "test"},
    )
    assert created["version"] == 1
    assert created["metadata"]["source"] == "test"

    updated = workspace.update_item(
        "v100-unit",
        created["id"],
        {"content": "Hallazgos verificados y próximos pasos.", "pinned": True},
    )
    assert updated["version"] == 2
    assert updated["pinned"] is True
    assert workspace.briefing("v100-unit")["workspace_items"] == 1

    research = workspace.route_preview("Investiga las noticias más recientes con fuentes", "auto")
    math = workspace.route_preview("2 + 2", "auto")
    assert research["strategy"] == "deep_research"
    assert research["web_required"] is True
    assert math["strategy"] == "local_math"
    assert workspace.delete_item("v100-unit", created["id"]) is True
    assert workspace.list_items("v100-unit") == []


def test_v100_api_workspace_status_and_crud():
    session_id = "v100-api-contract"
    with TestClient(main.app) as client:
        status = client.get("/api/v100/status", params={"session_id": session_id})
        route = client.post(
            "/api/v100/route",
            json={"message": "Analiza este documento", "mode": "auto", "has_files": True},
        )
        created = client.post(
            "/api/v100/workspace",
            json={
                "session_id": session_id,
                "title": "Canvas API",
                "content": "Contenido inicial",
                "kind": "canvas",
                "project_name": "General",
                "metadata": {"test": True},
            },
        )
        item_id = created.json()["item"]["id"]
        updated = client.put(
            f"/api/v100/workspace/{item_id}",
            json={
                "session_id": session_id,
                "title": "Canvas API actualizado",
                "content": "Contenido actualizado",
                "pinned": True,
            },
        )
        listed = client.get("/api/v100/workspace", params={"session_id": session_id})
        briefing = client.get("/api/v100/briefing", params={"session_id": session_id})
        deleted = client.delete(
            f"/api/v100/workspace/{item_id}",
            params={"session_id": session_id},
        )

    assert status.status_code == 200
    assert status.json()["version"] == "100.0.0"
    assert len(status.json()["stages"]) == 7
    assert route.json()["decision"]["strategy"] == "document_intelligence"
    assert created.status_code == 200
    assert updated.json()["item"]["version"] == 2
    assert any(item["id"] == item_id for item in listed.json()["items"])
    assert briefing.json()["briefing"]["workspace_items"] >= 1
    assert deleted.json()["status"] == "deleted"


def test_v100_chat_exposes_workspace_decision():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/jarvis",
            json={
                "message": "Calcula 18% de 45000",
                "session_id": "v100-direct-chat",
                "request_id": "v100-direct-chat-1",
                "mode": "math",
            },
        )
    payload = response.json()
    assert response.status_code == 200
    assert "8100" in payload["reply"].replace(",", "").replace(" ", "")
    assert payload["workspace_v100"]["strategy"] == "local_math"


def test_v100_frontend_contract_and_cache():
    html = Path("index.html").read_text(encoding="utf-8")
    app = Path("static/app.js").read_text(encoding="utf-8")
    v100_js = Path("static/v100.js").read_text(encoding="utf-8")
    css = Path("static/v100.css").read_text(encoding="utf-8")
    worker = Path("service-worker.js").read_text(encoding="utf-8")
    manifest = json.loads(Path("static/manifest.webmanifest").read_text(encoding="utf-8"))

    assert "Unified Intelligence · v100" in html
    assert 'id="v100SlashMenu"' in html
    assert 'id="v100WorkspaceDrawer"' in html
    assert "./static/v100.css?v=100.0" in html
    assert "./static/v100.js?v=100.0" in html
    assert "streamRequest" in app and "/api/jarvis/stream" in app
    assert "data-edit-message" in app and "data-branch-message" in app
    assert "jarvis:save-canvas" in app
    assert "/api/v100/workspace" in v100_js
    assert ".v100-workspace-drawer" in css
    assert "@media (max-width: 390px)" in css
    assert "jarvis-unified-workspace-v100-1" in worker
    assert "v100" in manifest["name"].lower()
