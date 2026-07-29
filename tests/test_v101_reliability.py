from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import main
from jarvis_core import DataFoundation, EmbeddingService, ReliabilityCore, V101_STAGES


def build_core(tmp_path) -> ReliabilityCore:
    foundation = DataFoundation(
        database_url="",
        sqlite_file=str(tmp_path / "v101.db"),
        embeddings=EmbeddingService("local", dimensions=128),
        persistent_declared=True,
    )
    foundation.init_schema()
    core = ReliabilityCore(foundation)
    core.init_schema()
    return core


def test_v101_stages_are_complete_and_guarded():
    assert [stage["version"] for stage in V101_STAGES] == list(range(94, 102))
    assert V101_STAGES[-1]["name"] == "Reliability & Self-Improvement"


def test_issue_fingerprints_aggregate_and_reopen_monitoring(tmp_path):
    core = build_core(tmp_path)
    first = core.record_issue(
        "unit",
        category="provider",
        title="Timeout del modelo",
        detail="Falló después de 30 segundos",
        severity="high",
    )
    repeated = core.record_issue(
        "unit",
        category="provider",
        title="Timeout del modelo",
        detail="Falló después de 42 segundos",
        severity="high",
    )
    assert repeated["id"] == first["id"]
    assert repeated["occurrences"] == 2
    core.update_issue("unit", first["id"], "resolved")
    reopened = core.record_issue(
        "unit",
        category="provider",
        title="Timeout del modelo",
        detail="Falló después de 58 segundos",
        severity="high",
    )
    assert reopened["status"] == "monitoring"
    assert reopened["occurrences"] == 3


def test_quality_run_creates_supervised_proposal(tmp_path):
    core = build_core(tmp_path)
    run = core.record_quality_run(
        "quality",
        {
            "database": {"ok": True, "detail": "operativa"},
            "provider": {"ok": False, "detail": "timeout controlado"},
        },
    )
    assert run["score"] == 0.5
    assert run["status"] == "critical"
    issues = core.list_issues("quality")
    analysis = core.analyze("quality", operations=[], recent=[])
    proposal = core.create_proposal("quality", issues[0])
    assert analysis["guardrails"]["can_modify_source"] is False
    assert analysis["guardrails"]["can_deploy"] is False
    assert proposal["status"] == "proposed"
    assert proposal["change_plan"]
    approved = core.review_proposal("quality", proposal["id"], "approved")
    assert approved["status"] == "approved"


def test_v101_api_report_diagnose_and_review():
    session_id = "v101-api-contract"
    with TestClient(main.app) as client:
        status = client.get("/api/v101/status", params={"session_id": session_id})
        reported = client.post(
            "/api/v101/issues/report",
            json={
                "session_id": session_id,
                "category": "frontend",
                "severity": "medium",
                "title": "Excepción visible de prueba",
                "detail": "El estado de error se mostró correctamente.",
                "context": {"viewport": "390x844"},
            },
        )
        issue_id = reported.json()["issue"]["id"]
        updated = client.put(
            f"/api/v101/issues/{issue_id}",
            json={"session_id": session_id, "status": "monitoring"},
        )
        diagnostics = client.post(
            "/api/v101/diagnostics/run",
            json={"session_id": session_id, "hours": 24},
        )
        proposals = client.get(
            "/api/v101/improvements/proposals",
            params={"session_id": session_id},
        )

    assert status.status_code == 200
    assert status.json()["version"] == "101.0.0"
    assert status.json()["guardrails"]["modify_source"] is False
    assert status.json()["guardrails"]["human_approval_required"] is True
    assert reported.status_code == 200
    assert updated.json()["issue"]["status"] == "monitoring"
    assert diagnostics.status_code == 200
    assert 0 <= diagnostics.json()["quality"]["score"] <= 1
    assert proposals.status_code == 200


def test_v101_rejects_invalid_mutation_states():
    with TestClient(main.app) as client:
        invalid_issue = client.put(
            "/api/v101/issues/not-real",
            json={"session_id": "v101-invalid", "status": "deleted"},
        )
        invalid_proposal = client.post(
            "/api/v101/improvements/proposals/not-real/decision",
            json={"session_id": "v101-invalid", "decision": "applied"},
        )
    assert invalid_issue.status_code == 422
    assert invalid_proposal.status_code == 422


def test_v101_frontend_contract_and_assets():
    html = Path("index.html").read_text(encoding="utf-8")
    css = Path("static/v101.css").read_text(encoding="utf-8")
    js = Path("static/v101.js").read_text(encoding="utf-8")
    worker = Path("service-worker.js").read_text(encoding="utf-8")

    assert "Reliable Intelligence · v101" in html
    assert "./static/v101.css?v=101.0" in html
    assert "./static/v101.js?v=101.0" in html
    assert "Segoe UI Variable Text" in css
    assert "Cascadia Code" in css
    assert "RELIABILITY & SELF-IMPROVEMENT" in js
    assert "unhandledrejection" in js
    assert "modify" not in js.lower() or "no se aplicó" in js.lower()
    assert "jarvis-reliable-intelligence-v101-1" in worker


def test_self_check_exposes_reliability_component():
    with TestClient(main.app) as client:
        payload = client.get("/api/self-check").json()
    assert "reliability_core_v101" in payload["checks"]
    assert payload["checks"]["reliability_core_v101"]["ok"] is True
