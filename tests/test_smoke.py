from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("JARVIS_DB_FILE", str(Path(tempfile.mkdtemp()) / "jarvis_test.db"))
os.environ.setdefault("JARVIS_PUBLIC_MODE", "true")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JARVIS_JOB_WORKERS", "1")
os.environ.setdefault("JARVIS_JOB_RETRY_BASE_SECONDS", "1")

from fastapi.testclient import TestClient

import main
from jarvis_core import compact_messages


def test_runtime_cache_round_trip():
    main.runtime.cache_set("unit:key", {"value": 42}, 60)
    value, layer = main.runtime.cache_get("unit:key")
    assert value == {"value": 42}
    assert layer == "memory"


def test_circuit_breaker_opens_and_recovers():
    name = "test:circuit"
    for _ in range(main.CIRCUIT_FAILURE_THRESHOLD):
        main.runtime.circuits.failure(name, "failure")
    assert main.runtime.circuits.snapshot()[name]["state"] == "open"
    assert main.runtime.circuits.allow(name) is False
    main.runtime.circuits.success(name)
    assert main.runtime.circuits.snapshot()[name]["state"] == "closed"


def test_context_compaction_preserves_recent_content():
    messages = [
        {"role": "system", "content": "system" * 1000},
        {"role": "user", "content": "old" * 5000},
        {"role": "assistant", "content": "recent-answer"},
        {"role": "user", "content": "recent-question"},
    ]
    result = compact_messages(messages, 5000, 4)
    joined = " ".join(item["content"] for item in result)
    assert "recent-question" in joined
    assert sum(len(item["content"]) for item in result) <= 5000


def test_calculator_and_sympy_local_routes():
    assert main.calculator("test", "2+2")["result"] == 4
    solved = main.sympy_solve("test", "x^2-5*x+6=0", "x")
    assert set(solved["solutions"]) == {"2", "3"}


def test_http_health_and_headers():
    with TestClient(main.app) as client:
        live = client.get("/api/health/live")
        assert live.status_code == 200
        assert live.json()["version"] == "18.0.0"
        assert live.headers["x-jarvis-version"] == "18.0.0"
        assert live.headers.get("x-request-id")

        ready = client.get("/api/health/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        deep = client.get("/api/health/deep")
        assert deep.status_code == 200
        payload = deep.json()
        assert payload["database"]["ok"] is True
        assert payload["jobs"]["ok"] is True


def test_capabilities_include_stability_features():
    with TestClient(main.app) as client:
        data = client.get("/api/capabilities").json()
        assert data["version"] == "18.0.0"
        features = set(data["features"])
        assert "singleflight_deduplication" in features
        assert "persistent_job_recovery" in features
        assert "deep_health_checks" in features


def test_direct_chat_returns_without_provider():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/jarvis",
            json={
                "message": "Calcula 12% de 85000",
                "session_id": "direct-test",
                "request_id": "direct-test-1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in {"success", "degraded"}
        assert "10200" in data["reply"].replace(",", "").replace(" ", "")
        assert data["request_id"] == "direct-test-1"


def test_idempotent_request_replay():
    with TestClient(main.app) as client:
        body = {"message": "2+2", "session_id": "replay", "request_id": "same-request"}
        first = client.post("/api/jarvis", json=body).json()
        second = client.post("/api/jarvis", json=body).json()
        assert first["reply"] == second["reply"]
        assert second.get("idempotent_replay") is True


def test_persistent_job_completes_and_exposes_checkpoint():
    with TestClient(main.app) as client:
        created = client.post(
            "/api/jobs",
            json={"session_id": "job-test", "title": "Cálculo", "prompt": "Calcula 5+7"},
        )
        assert created.status_code == 200
        job_id = created.json()["job_id"]
        final = None
        for _ in range(60):
            response = client.get(f"/api/jobs/{job_id}?session_id=job-test")
            assert response.status_code == 200
            final = response.json()["job"]
            if final["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        assert final is not None
        assert final["status"] == "completed"
        assert final["progress"] == 100
        assert final["checkpoint"]
        assert "12" in final["result"]


def test_performance_endpoint_records_operations():
    with TestClient(main.app) as client:
        client.get("/api/health/live")
        data = client.get("/api/performance?session_id=performance-test").json()
        assert data["status"] == "ok"
        assert data["runtime"]["cache"]["memory"]["max_items"] >= 64
        assert data["configuration"]["job_workers"] >= 1


def test_static_assets_exist_and_root_loads():
    required = [
        Path("index.html"),
        Path("static/index.html"),
        Path("static/styles.css"),
        Path("static/app.js"),
        Path("static/config.js"),
        Path("static/jarvis-reactor-v10.png"),
        Path("static/favicon-32.png"),
        Path("service-worker.js"),
    ]
    assert all(path.exists() for path in required)
    with TestClient(main.app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "J.A.R.V.I.S." in response.text


def test_streaming_chat_sends_progress_and_final_event():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/jarvis/stream",
            json={
                "message": "Calcula 9+6",
                "session_id": "stream-test",
                "request_id": "stream-request-1",
            },
        )
        assert response.status_code == 200
        assert "application/x-ndjson" in response.headers.get("content-type", "")
        lines = [line for line in response.text.splitlines() if line.strip()]
        assert any('"type": "progress"' in line for line in lines)
        final_lines = [line for line in lines if '"type": "final"' in line]
        assert final_lines
        assert "15" in final_lines[-1]
