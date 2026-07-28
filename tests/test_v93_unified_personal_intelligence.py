import json
from pathlib import Path

from fastapi.testclient import TestClient

import main


def test_v93_status_personas_settings_and_projects():
    session_id = "v93-core-contract"
    with TestClient(main.app) as client:
        status = client.get("/api/v93/status", params={"session_id": session_id})
        personas = client.get("/api/v93/personas")
        settings = client.put(
            "/api/v93/settings",
            json={
                "session_id": session_id,
                "persona": "analytical",
                "voice_enabled": True,
                "auto_speak": True,
                "voice_name": "alloy",
                "voice_rate": 1.1,
                "locale": "es-HN",
            },
        )
        project = client.post(
            "/api/v93/projects",
            json={
                "session_id": session_id,
                "name": "Economía",
                "description": "Investigación económica",
                "instructions": "Distingue cifras oficiales de estimaciones.",
                "color": "cyan",
            },
        )
        projects = client.get("/api/v93/projects", params={"session_id": session_id})

    assert status.status_code == 200
    assert status.json()["version"] == 93
    assert status.json()["app_version"] == "93.0.0"
    assert len(personas.json()["personas"]) == 6
    assert settings.json()["settings"]["persona"] == "analytical"
    assert settings.json()["settings"]["auto_speak"] is True
    assert project.status_code == 200
    assert {item["name"] for item in projects.json()["projects"]} >= {"General", "Economía"}


def test_v93_monitors_quality_export_and_prompt_guidance():
    session_id = "v93-quality-contract"
    with TestClient(main.app) as client:
        monitor = client.post(
            "/api/v93/monitors",
            json={
                "session_id": session_id,
                "title": "IA semanal",
                "query": "Noticias verificadas sobre inteligencia artificial",
                "cadence": "weekly",
                "project_name": "General",
                "channel": "telegram",
            },
        )
        monitor_id = monitor.json()["monitor"]["id"]
        activated = client.put(
            f"/api/v93/monitors/{monitor_id}",
            json={"session_id": session_id, "status": "active"},
        )
        quality = main.personal_os.evaluate_response(
            session_id,
            "Explica la memoria semántica",
            "La memoria semántica recupera información relacionada por significado y la combina con coincidencias textuales.",
            {"verified": True},
        )
        summary = client.get("/api/v93/quality", params={"session_id": session_id})
        exported = client.get("/api/v93/export", params={"session_id": session_id})

    assert monitor.status_code == 200
    assert activated.json()["monitor"]["status"] == "active"
    with main.data_foundation.connection() as conn:
        placeholder = "%s" if main.data_foundation.driver == "postgresql" else "?"
        conn.execute(
            f"UPDATE v93_monitors SET next_run_at=0 WHERE id={placeholder}",
            (monitor_id,),
        )
    claimed = main.personal_os.claim_due_monitors(10)
    assert any(item["id"] == monitor_id for item in claimed)
    assert not any(item["id"] == monitor_id for item in main.personal_os.claim_due_monitors(10))
    assert quality["score"] >= 0.8
    assert summary.json()["quality"]["evaluations"] >= 1
    assert exported.status_code == 200
    assert exported.json()["format"] == "jarvis-personal-os"
    assert "attachment;" in exported.headers["content-disposition"]

    prompt = main.construir_prompt_sistema(session_id, "General", "auto", "general")
    assert "Perfil de respuesta" in prompt
    assert "asistente conversacional de máxima utilidad" in prompt


def test_v93_frontend_contract_and_assets():
    html = Path("index.html").read_text(encoding="utf-8")
    app = Path("static/app.js").read_text(encoding="utf-8")
    css = Path("static/v93.css").read_text(encoding="utf-8")
    worker = Path("service-worker.js").read_text(encoding="utf-8")
    manifest = json.loads(Path("static/manifest.webmanifest").read_text(encoding="utf-8"))

    assert "Unified Personal Intelligence · v93" in html
    assert 'id="projectSelect"' in html
    assert 'id="personaSelect"' in html
    assert "./static/v93.css?v=93.0" in html
    assert "browserSpeech" in app and "speechSynthesis" in app
    assert "project_name:state.activeProject" in app
    assert "persona:state.settings.persona" in app
    assert "/api/v93/settings" in app and "/api/v93/projects" in app
    assert ".project-switcher" in css
    assert "@media (max-width: 390px)" in css
    assert "jarvis-unified-intelligence-v93-1" in worker
    assert "v93" in manifest["name"].lower()


def test_telegram_style_command_and_voice_status():
    session_id = "telegram:v93-style"
    changed = main._telegram_command("v93-chat", session_id, "/style teacher")
    current = main._telegram_command("v93-chat", session_id, "/style")
    assert "Tutor" in changed["text"]
    assert "Tutor" in current["text"]
    assert {"speech", "transcription", "vision"} <= set(main.telegram_media_ai.status())
