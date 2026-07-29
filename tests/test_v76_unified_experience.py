from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import main
from jarvis_core.v76 import CommandRouter, ImprovementAdvisor, UnifiedExperienceStore, V76_STAGES


def test_v76_stage_registry_is_complete_and_ordered():
    assert [item["version"] for item in V76_STAGES] == list(range(67, 77))
    assert all(item["capabilities"] for item in V76_STAGES)
    assert V76_STAGES[-1]["name"] == "Supervised Improvement"


def test_preferences_and_timeline_persist_safely():
    db_file = str(Path(tempfile.mkdtemp()) / "experience.db")
    store = UnifiedExperienceStore(db_file)
    store.init_schema()
    preferences = store.save_preferences(
        "session",
        {"theme": "oled", "density": "compact", "context_panel": True, "focus_mode": True},
    )
    assert preferences["theme"] == "oled"
    assert preferences["density"] == "compact"
    assert preferences["focus_mode"] is True
    event = store.record_event("session", "test", "Prueba completada", {"value": 1}, "success")
    timeline = store.timeline("session")
    assert timeline[0]["id"] == event["id"]
    assert timeline[0]["detail"]["value"] == 1


def test_preferences_reject_unknown_visual_values():
    db_file = str(Path(tempfile.mkdtemp()) / "experience.db")
    store = UnifiedExperienceStore(db_file)
    preferences = store.save_preferences("session", {"theme": "unsafe", "density": "giant"})
    assert preferences["theme"] == "dark"
    assert preferences["density"] == "comfortable"


def test_command_router_is_zero_token_and_searchable():
    results = CommandRouter.suggest("telegram")
    assert results and results[0]["id"] == "open_telegram"
    assert all("label" in item for item in CommandRouter.suggest())


def test_improvement_advisor_never_self_deploys():
    result = ImprovementAdvisor.analyze(
        {"health": "degraded", "open_circuits": 2, "errors_24h": 5, "requests_24h": 20}
    )
    assert result["recommendations"][0]["priority"] == "high"
    assert "deployment" in result["approval_required"]
    assert "code" in result["approval_required"]


def test_v76_status_and_compatibility_routes():
    with TestClient(main.app) as client:
        status = client.get("/api/v76/status", params={"session_id": "v76-status"})
        assert status.status_code == 200
        payload = status.json()
        assert payload["version"] == "100.0.0"
        assert payload["total_stages"] == 10
        assert payload["safety"]["self_deployment"] is False
        for version in (67, 70, 72, 75):
            response = client.get(f"/api/v{version}/status", params={"session_id": "compat"})
            assert response.status_code == 200
            assert response.json()["version"] == "100.0.0"


def test_v76_preferences_api_round_trip():
    with TestClient(main.app) as client:
        saved = client.put(
            "/api/v76/preferences",
            json={
                "session_id": "v76-preferences",
                "theme": "contrast",
                "density": "compact",
                "context_panel": True,
                "reduce_motion": True,
                "focus_mode": False,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["preferences"]["theme"] == "contrast"
        loaded = client.get("/api/v76/preferences", params={"session_id": "v76-preferences"})
        assert loaded.json()["preferences"]["reduce_motion"] is True


def test_v76_context_returns_real_collections():
    with TestClient(main.app) as client:
        response = client.get("/api/v76/context", params={"session_id": "v76-context"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["version"] == "100.0.0"
        assert isinstance(payload["artifacts"], list)
        assert isinstance(payload["research"], list)
        assert isinstance(payload["jobs"], list)
        assert "status" in payload["health"]


def test_v76_improvement_is_bounded_and_optionally_persistent():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/v76/improvement/analyze",
            json={"session_id": "v76-improvement", "persist": True},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["proposal"]
        assert "no modifica código" in payload["note"]
        proposals = client.get(
            "/api/v76/improvement/proposals",
            params={"session_id": "v76-improvement"},
        ).json()["proposals"]
        assert proposals and proposals[0]["status"] == "proposed"


def test_v76_frontend_contract_is_present():
    html = Path("index.html").read_text(encoding="utf-8")
    script = Path("static/v76.js").read_text(encoding="utf-8")
    css = Path("static/v76.css").read_text(encoding="utf-8")
    worker = Path("service-worker.js").read_text(encoding="utf-8")
    assert "Unified Intelligence · v100" in html
    assert 'id="v76CommandPalette"' in html
    assert 'id="v76ContextDrawer"' in html
    assert "/api/v76/context" in script
    assert "v76-context-drawer" in css
    assert "jarvis-unified-workspace-v100-1" in worker

