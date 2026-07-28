from pathlib import Path

from fastapi.testclient import TestClient

import main
from jarvis_core.identity import IdentityStore


def test_owner_bootstrap_is_idempotent_and_login_works(tmp_path):
    store = IdentityStore(str(tmp_path / "owner.db"), session_days=7)
    store.init_schema()

    first = store.ensure_owner("owner@example.com", "OwnerPassword2027", "Owner")
    second = store.ensure_owner("other@example.com", "OtherPassword2027", "Other")

    assert first["created"] is True
    assert first["user"]["role"] == "admin"
    assert second == {"created": False, "reason": "identity_store_not_empty"}
    assert store.user_count() == 1
    session = store.login("owner@example.com", "OwnerPassword2027")
    assert session["user"]["email"] == "owner@example.com"


def test_persistence_status_is_public_and_secret_free():
    with TestClient(main.app) as client:
        response = client.get("/api/persistence/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "93.0.0"
    assert payload["engine"] == "sqlite"
    assert payload["storage_mode"] in {"persistent", "ephemeral_or_unverified"}
    assert "password" not in str(payload).lower()


def test_v77_frontend_contract_and_cache():
    html = Path("index.html").read_text(encoding="utf-8")
    css = Path("static/v77.css").read_text(encoding="utf-8")
    worker = Path("service-worker.js").read_text(encoding="utf-8")

    assert "Unified Personal Intelligence · v93" in html
    assert "./static/v77.css?v=93.0" in html
    assert ".conversation" in css and "max-width: none !important" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css
    assert "jarvis-unified-intelligence-v93-1" in worker


def test_health_reports_persistence_state():
    with TestClient(main.app) as client:
        ready = client.get("/api/health/ready")
        health = client.get("/api/health")

    assert ready.status_code == 200
    assert "persistence" in ready.json()
    assert "persistence" in health.json()
