from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import main
from jarvis_core.v66 import (
    AdaptiveDecisionEngine,
    AdaptiveLearningStore,
    AnswerQualityGate,
    append_source_list,
)


def test_stable_question_avoids_unnecessary_web_search():
    decision = AdaptiveDecisionEngine().decide("Explícame qué es una función pura", intent="general")
    assert decision["web"] == "off"
    assert decision["memory"] == "relevant"
    assert decision["citations_required"] is False
    assert AdaptiveDecisionEngine().decide("Actualiza este código", intent="code")["web_required"] is False


def test_current_information_requires_web_and_citations():
    decision = AdaptiveDecisionEngine().decide("¿Quién es el presidente actual y cuáles son las últimas noticias?", intent="general")
    assert decision["web"] == "required"
    assert decision["web_required"] is True
    assert decision["citations_required"] is True
    assert decision["freshness"] == "current"


def test_explicit_no_web_instruction_is_respected():
    decision = AdaptiveDecisionEngine().decide("Sin buscar en internet, explícame el clima como concepto", intent="general")
    assert decision["web"] == "disabled"
    assert decision["web_required"] is False
    assert decision["user_web_override"] == "disabled"


def test_memory_and_documents_are_selected_by_meaning():
    engine = AdaptiveDecisionEngine()
    memory = engine.decide("¿Qué recuerdas de mi proyecto?", intent="general")
    document = engine.decide("Resume el PDF que subí", intent="documents")
    assert memory["memory"] == "required"
    assert document["documents"] == "required"


def test_source_list_is_added_once():
    sources = [{"title": "Fuente oficial", "url": "https://example.org/fuente"}]
    answer = append_source_list("Respuesta verificada.", sources)
    assert "### Fuentes consultadas" in answer
    assert "https://example.org/fuente" in answer
    assert append_source_list(answer, sources) == answer


def test_quality_gate_rejects_current_claim_without_evidence():
    gate = AnswerQualityGate()
    decision = AdaptiveDecisionEngine().decide("precio actual del producto", intent="research")
    failed = gate.evaluate("precio", "El precio actual es 100.", decision, {"web_sources": 0})
    passed = gate.evaluate(
        "precio", "El precio verificado aparece en https://example.org/precio", decision, {"web_sources": 1},
    )
    assert failed["passed"] is False
    assert passed["passed"] is True


def test_learning_store_persists_bounded_outcomes():
    db_file = str(Path(tempfile.mkdtemp()) / "adaptive.db")
    store = AdaptiveLearningStore(db_file)
    store.init_schema()
    decision = AdaptiveDecisionEngine().decide("noticias recientes", intent="research")
    item_id = store.start("session", "noticias recientes", decision)
    store.finish(
        item_id, route="provider_research", memory_hits=1, web_sources=5,
        verified=True, quality_score=0.91, latency_ms=1200,
    )
    status = store.status("session")
    assert status["summary"]["decisions"] == 1
    assert status["summary"]["web_sources"] == 5
    assert status["safety"]["edits_own_code"] is False
    assert store.learned_hint("research")["recommended_sources"] in {6, 8}
    assert store.record_feedback("session", -1) is True
    assert store.status("session")["summary"]["verification_rate"] == 0


def test_adaptive_preview_does_not_execute_search():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/adaptive/decision-preview",
            json={"session_id": "preview", "message": "Busca noticias actuales", "mode": "auto"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision"]["web_required"] is True
        assert "no ejecuta búsquedas" in payload["note"]


def test_adaptive_status_exposes_safety_boundaries():
    with TestClient(main.app) as client:
        payload = client.get("/api/adaptive/status", params={"session_id": "adaptive-status"}).json()
        assert payload["version"] == "66.0.0"
        assert payload["policy"]["evaluates_every_request"] is True
        assert payload["safety"]["deploys_automatically"] is False


def test_retrieval_prepares_memory_and_web_context(monkeypatch):
    monkeypatch.setattr(main, "semantic_search", lambda *args, **kwargs: {
        "matches": [{"title": "Preferencia", "excerpt": "El usuario prefiere respuestas completas."}]
    })
    monkeypatch.setattr(main, "web_search", lambda *args, **kwargs: {
        "results": [{"title": "Fuente oficial", "snippet": "Dato reciente confirmado", "url": "https://example.org/oficial"}],
        "attempts": [{"provider": "test", "status": "completed"}],
        "providers_used": ["test"],
    })
    prepared = main.prepare_adaptive_retrieval(
        "session", "Busca la versión actual y recuerda mis preferencias",
        project_name="General", intent="research", mode="auto",
    )
    assert prepared["summary"]["memory_hits"] == 1
    assert prepared["summary"]["web_sources"] == 1
    assert "MEMORIA RELEVANTE" in prepared["context"]
    assert "https://example.org/oficial" in prepared["context"]


def test_required_web_failure_is_explicitly_injected(monkeypatch):
    monkeypatch.setattr(main, "semantic_search", lambda *args, **kwargs: {"matches": []})
    monkeypatch.setattr(main, "web_search", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    prepared = main.prepare_adaptive_retrieval(
        "session", "¿Cuál es el precio actual?", project_name="General", intent="research", mode="auto",
    )
    assert prepared["decision"]["web_required"] is True
    assert prepared["summary"]["web_sources"] == 0
    assert "VERIFICACIÓN WEB NO DISPONIBLE" in prepared["context"]
    assert prepared["errors"]


def test_no_web_override_is_honored_by_last_resort(monkeypatch):
    called = {"web": 0}
    def forbidden_search(*args, **kwargs):
        called["web"] += 1
        raise AssertionError("web search must not run")
    monkeypatch.setattr(main, "web_search", forbidden_search)
    result = main._local_last_resort("session", "Sin internet, explícame esto", "research", allow_web=False)
    assert called["web"] == 0
    assert result["mode"] == "resilient_local"


def test_current_answer_is_not_returned_as_fact_without_sources(monkeypatch):
    monkeypatch.setattr(main, "VERIFY_RESULTS", False)
    monkeypatch.setattr(main, "direct_route", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "cache_get", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "run_agent", lambda *args, **kwargs: {
        "reply": "El precio actual es 999.", "tools": [], "mode": "test", "model": None, "usage": {"total_tokens": 0},
    })
    decision = AdaptiveDecisionEngine().decide("precio actual", intent="research")
    with TestClient(main.app):
        result = main.resilient_resolve(
            "source-gate", "precio actual", project_name="General", mode="auto",
            intent_info={"intent": "research", "confidence": 1.0},
            adaptive={
                "decision": decision, "context": "VERIFICACIÓN WEB NO DISPONIBLE", "web_results": [],
                "errors": ["offline"], "summary": {"memory_hits": 0, "document_hits": 0, "web_sources": 0},
            },
        )
    assert result["degraded"] is True
    assert "No pude verificar información actual" in result["reply"]
    assert "999" not in result["reply"]


def test_direct_chat_includes_adaptive_trace():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/jarvis",
            json={"message": "Calcula 2+2", "session_id": "adaptive-direct", "request_id": "adaptive-direct-1"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert "4" in payload["reply"]
        assert payload["adaptive"]["policy_version"] == "66.0"
        assert payload["adaptive"]["web_required"] is False


def test_frontend_exposes_adaptive_evidence_without_new_primary_navigation():
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    html = Path("index.html").read_text(encoding="utf-8")
    assert "Criterio y evidencia" in app_js
    assert "/api/adaptive/status" in app_js
    assert "Adaptive Intelligence · v66" in html
