from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("JARVIS_DB_FILE", str(Path(tempfile.mkdtemp()) / "jarvis_test.db"))
os.environ.setdefault("JARVIS_PUBLIC_MODE", "true")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JARVIS_JOB_WORKERS", "1")
os.environ.setdefault("JARVIS_JOB_RETRY_BASE_SECONDS", "1")
os.environ.setdefault("JARVIS_REQUESTS_PER_MINUTE", "120")

from fastapi.testclient import TestClient

import main
from jarvis_core import (
    ChannelStore,
    IdentityStore,
    TelegramMediaAI,
    TelegramPreferenceStore,
    TelegramChannel,
    compact_messages,
)


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
        assert live.json()["version"] == "55.0.0"
        assert live.headers["x-jarvis-version"] == "55.0.0"
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
        assert data["version"] == "55.0.0"
        features = set(data["features"])
        assert "singleflight_deduplication" in features
        assert "persistent_job_recovery" in features
        assert "deep_health_checks" in features
        assert "telegram_multimodal" in features
        assert "telegram_voice_replies" in features
        assert "telegram_interactive_menu" in features


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
        Path("static/jarvis-reactor-v46.svg"),
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


def test_provider_gateway_endpoints_and_route_preview():
    with TestClient(main.app) as client:
        status = client.get("/api/providers")
        assert status.status_code == 200
        payload = status.json()
        assert payload["version"] == "55.0.0"
        assert "gateway" in payload
        assert "providers" in payload["gateway"]

        preview = client.post(
            "/api/providers/route-preview",
            json={"message": "Investiga tendencias recientes de inteligencia artificial", "mode": "research"},
        )
        assert preview.status_code == 200
        data = preview.json()
        assert data["intent"] == "research"
        assert isinstance(data["routes"], list)
        names = {item["provider"] for item in data["routes"]}
        assert {"groq", "openai", "anthropic", "gemini", "compatible", "ollama"}.issubset(names)


def test_gateway_provider_modules_import():
    from jarvis_core.providers import MultiProviderGateway, ProviderRequest

    assert isinstance(main.provider_gateway, MultiProviderGateway)
    request = ProviderRequest(messages=[{"role": "user", "content": "Hola"}], intent="general", mode="fast")
    preview = main.provider_gateway.route_preview(request)
    assert isinstance(preview, list)


def test_openai_adapter_parses_responses_payload():
    import httpx
    from jarvis_core.providers import OpenAIProvider, ProviderModel, ProviderRequest

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith('/responses')
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": "Respuesta OpenAI"}]}],
                "usage": {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17},
            },
        )

    provider = OpenAIProvider(
        api_key="test-key",
        models=[ProviderModel(id="test-openai", capabilities={"text"})],
        runtime=main.runtime,
        timeout_seconds=10,
    )
    provider.http.close()
    provider.http = httpx.Client(transport=httpx.MockTransport(handler))
    result = provider.generate(ProviderRequest(messages=[{"role": "user", "content": "Hola"}]), provider.models[0])
    assert result.text == "Respuesta OpenAI"
    assert result.usage["total_tokens"] == 17
    provider.close()


def test_gemini_adapter_parses_generate_content_payload():
    import httpx
    from jarvis_core.providers import GeminiProvider, ProviderModel, ProviderRequest

    def handler(request: httpx.Request) -> httpx.Response:
        assert ':generateContent' in request.url.path
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Respuesta Gemini"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 4, "totalTokenCount": 12},
            },
        )

    provider = GeminiProvider(
        api_key="test-key",
        models=[ProviderModel(id="test-gemini", capabilities={"text"})],
        runtime=main.runtime,
        timeout_seconds=10,
    )
    provider.http.close()
    provider.http = httpx.Client(transport=httpx.MockTransport(handler))
    result = provider.generate(ProviderRequest(messages=[{"role": "user", "content": "Hola"}]), provider.models[0])
    assert result.text == "Respuesta Gemini"
    assert result.usage["total_tokens"] == 12
    provider.close()


def test_gateway_falls_back_to_second_provider():
    from jarvis_core.providers.base import BaseProvider, ProviderError, ProviderModel, ProviderRequest, ProviderResult
    from jarvis_core.providers.gateway import MultiProviderGateway

    class FailingProvider(BaseProvider):
        name = "first"
        label = "First"

        def generate(self, request, model):
            raise ProviderError("falló", provider=self.name, model=model.id, category="temporary")

    class WorkingProvider(BaseProvider):
        name = "second"
        label = "Second"

        def generate(self, request, model):
            return ProviderResult(provider=self.name, model=model.id, text="resuelto", latency_ms=1.0)

    first = FailingProvider(models=[ProviderModel(id="one")], runtime=main.runtime)
    second = WorkingProvider(models=[ProviderModel(id="two")], runtime=main.runtime)
    gateway = MultiProviderGateway([first, second], order=["first", "second"])
    result, attempts = gateway.generate(ProviderRequest(messages=[{"role": "user", "content": "prueba"}]), max_attempts=2)
    assert result.text == "resuelto"
    assert [item["status"] for item in attempts] == ["failed", "completed"]
    gateway.close()


def test_agent_plan_and_execute_endpoints():
    with TestClient(main.app) as client:
        plan = client.post('/api/agents/plan', json={
            'session_id': 'agent-test',
            'objective': 'Investiga la inflación, compara fuentes y prepara un resumen ejecutivo.',
            'mode': 'research',
            'project_name': 'Economía',
        })
        assert plan.status_code == 200
        payload = plan.json()
        assert payload['status'] == 'planned'
        assert payload['steps']
        assert payload['budget']['checkpoint_each_step'] is True

        execution = client.post('/api/agents/execute', json={
            'session_id': 'agent-test',
            'title': 'Informe de inflación',
            'objective': 'Investiga la inflación y crea un informe breve.',
            'mode': 'research',
            'project_name': 'Economía',
        })
        assert execution.status_code == 200
        data = execution.json()
        assert data['status'] == 'queued'
        assert data['agent_mode'] is True
        assert data['plan']['steps']

        status = client.get('/api/agents/status', params={'session_id': 'agent-test'})
        assert status.status_code == 200
        assert status.json()['version'] == '55.0.0'



def test_anthropic_adapter_parses_messages_payload_and_cache():
    import httpx
    from jarvis_core.providers import AnthropicProvider, ProviderModel, ProviderRequest

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith('/v1/messages')
        assert request.headers.get('x-api-key') == 'test-key'
        assert request.headers.get('anthropic-version') == '2023-06-01'
        payload = json.loads(request.content.decode('utf-8'))
        assert payload['model'] == 'test-claude'
        assert payload['system'][0]['cache_control']['type'] == 'ephemeral'
        return httpx.Response(
            200,
            json={
                'id': 'msg_test',
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'text', 'text': 'Respuesta Claude'}],
                'stop_reason': 'end_turn',
                'usage': {
                    'input_tokens': 14,
                    'output_tokens': 6,
                    'cache_creation_input_tokens': 8,
                    'cache_read_input_tokens': 2,
                },
            },
        )

    provider = AnthropicProvider(
        api_key='test-key',
        models=[ProviderModel(id='test-claude', capabilities={'text'})],
        runtime=main.runtime,
        timeout_seconds=10,
        prompt_cache=True,
    )
    provider.http.close()
    provider.http = httpx.Client(transport=httpx.MockTransport(handler))
    result = provider.generate(
        ProviderRequest(messages=[
            {'role': 'system', 'content': 'Eres JARVIS.'},
            {'role': 'user', 'content': 'Hola'},
        ]),
        provider.models[0],
    )
    assert result.text == 'Respuesta Claude'
    assert result.usage['total_tokens'] == 20
    assert result.usage['cache_read_input_tokens'] == 2
    assert result.metadata['prompt_cache_enabled'] is True
    provider.close()


def test_provider_capability_matrix_and_tool_registry_endpoints():
    with TestClient(main.app) as client:
        capabilities = client.get('/api/providers/capabilities')
        assert capabilities.status_code == 200
        payload = capabilities.json()
        assert payload['version'] == '55.0.0'
        assert 'anthropic' in payload['matrix']['providers']
        assert 'coding' in payload['matrix']['task_preferences']
        assert payload['quality_council']['max_providers'] >= 2

        registry = client.get('/api/tools/registry')
        assert registry.status_code == 200
        tools = registry.json()
        assert tools['version'] == '55.0.0'
        assert tools['available_count'] >= 10
        names = {item['name'] for item in tools['tools'] if item['available']}
        assert {'web_search', 'calculator', 'document_search'}.issubset(names)


def test_gateway_can_exclude_primary_provider_for_quality_review():
    from jarvis_core.providers.base import BaseProvider, ProviderModel, ProviderRequest, ProviderResult
    from jarvis_core.providers.gateway import MultiProviderGateway

    class PrimaryProvider(BaseProvider):
        name = 'primary'
        label = 'Primary'
        def generate(self, request, model):
            return ProviderResult(provider=self.name, model=model.id, text='primario', latency_ms=1.0)

    class ReviewProvider(BaseProvider):
        name = 'review'
        label = 'Review'
        def generate(self, request, model):
            return ProviderResult(provider=self.name, model=model.id, text='revisado', latency_ms=1.0)

    primary = PrimaryProvider(models=[ProviderModel(id='p')], runtime=main.runtime)
    review = ReviewProvider(models=[ProviderModel(id='r')], runtime=main.runtime)
    gateway = MultiProviderGateway([primary, review], order=['primary', 'review'])
    request = ProviderRequest(
        messages=[{'role': 'user', 'content': 'revisa'}],
        metadata={'exclude_providers': ['primary']},
    )
    result, attempts = gateway.generate(request, max_attempts=2)
    assert result.provider == 'review'
    assert result.text == 'revisado'
    assert attempts[0]['provider'] == 'review'
    gateway.close()



def test_professional_plan_builds_specialist_team_and_quality_gates():
    from jarvis_core.professional import build_professional_plan

    plan = build_professional_plan(
        objective="Investiga la inflación en Honduras, analiza los datos y prepara un informe ejecutivo con fuentes.",
        intent="research",
        mode="professional",
        project_name="Economía",
        confidence=0.92,
        max_roles=6,
    )
    role_ids = {item["id"] for item in plan["team"]}
    assert {"director", "researcher", "auditor"}.issubset(role_ids)
    assert plan["milestones"]
    assert all(item.get("quality_gate") for item in plan["milestones"])
    assert plan["budget"]["independent_verification"] is True


def test_professional_endpoints_expose_profiles_and_plan():
    with TestClient(main.app) as client:
        profiles = client.get("/api/professional/profiles")
        assert profiles.status_code == 200
        payload = profiles.json()
        assert payload["version"] == "55.0.0"
        assert len(payload["profiles"]) >= 6

        planned = client.post(
            "/api/professional/plan",
            json={
                "session_id": "professional-test",
                "objective": "Diseña una solución técnica completa y verifica los riesgos.",
                "mode": "professional",
                "project_name": "JARVIS",
                "max_roles": 5,
            },
        )
        assert planned.status_code == 200
        data = planned.json()
        assert data["edition"] == "professional"
        assert data["team"]
        assert data["milestones"]
        assert data["success_criteria"]

        status = client.get("/api/professional/status?session_id=professional-test")
        assert status.status_code == 200
        assert status.json()["version"] == "55.0.0"


def test_responsive_frontend_contract():
    html = Path("index.html").read_text(encoding="utf-8")
    css = Path("static/styles.css").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    manifest = json.loads(Path("static/manifest.webmanifest").read_text(encoding="utf-8"))

    assert "viewport-fit=cover" in html
    assert "?v=55" in html
    assert "jarvis-reactor-v46.svg" in html
    assert 'class="mobile-nav"' in html
    assert 'id="composer"' in html
    assert 'id="authModal"' in html
    assert 'id="connectionModal"' in html
    assert "@media (max-width: 640px)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert ".welcome-reactor img" in css and "animation: none !important" in css
    assert "jarvis_v55_chats" in js
    assert manifest["display"] == "standalone"


def test_frontend_response_recovery_contract():
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "class ApiError extends Error" in js
    assert "function localRecovery" in js
    assert "const safeStorage" in js
    assert "timeoutMs:65000" in js
    assert "local_recovery" in js
    assert "error?.status === 401" in js
    assert "request('/api/jarvis'" in js
    assert "/api/jarvis/stream" not in js


def test_stream_has_emergency_final_fallback():
    source = Path("main.py").read_text(encoding="utf-8")
    assert "stream_emergency_fallback" in source
    assert '"version": APP_VERSION' in source


def test_v38_semantic_memory_finds_related_content():
    memory = main.memory_save("semantic-test", "Prefiero recibir siempre el código completo", "preference", 4)
    result = main.semantic_search("semantic-test", "programación completa", limit=5)
    assert result["model"] == "local-hybrid-v1"
    assert any(item["source_id"] == memory["id"] for item in result["matches"])


def test_v38_autonomy_workflow_executes_real_steps():
    with TestClient(main.app) as client:
        created = client.post(
            "/api/autonomy/workflows",
            json={
                "session_id": "workflow-test",
                "objective": "Calcula 2+2 y explica el resultado de forma breve.",
                "mode": "math",
                "project_name": "Pruebas",
                "start": True,
            },
        )
        assert created.status_code == 200
        workflow_id = created.json()["workflow"]["id"]
        final = None
        for _ in range(300):
            response = client.get(f"/api/autonomy/workflows/{workflow_id}?session_id=workflow-test")
            assert response.status_code == 200
            final = response.json()["workflow"]
            if final["status"] in {"completed", "failed", "cancelled", "awaiting_approval"}:
                break
            time.sleep(0.05)
        assert final is not None
        assert final["status"] == "completed"
        assert all(step["status"] == "completed" for step in final["steps"])
        assert "4" in final["result"]
        assert final["verification"]


def test_v38_sensitive_workflow_requires_explicit_approval():
    plan = main.autonomy_planner.build(
        "Redacta y enviar un correo al equipo con el informe.",
        intent="writing",
        mode="auto",
        project_name="Seguridad",
    )
    assert plan.requires_approval is True
    workflow = main.autonomy_store.create_workflow("approval-test", plan)
    approval_step = next(step for step in workflow["steps"] if step["requires_approval"])
    approval = main.autonomy_store.create_approval(workflow["id"], approval_step)
    assert approval["status"] == "pending"
    decided = main.autonomy_store.decide_approval(approval["id"], "rejected", "No autorizado")
    assert decided["status"] == "rejected"


def test_v38_automation_and_optional_integrations_status():
    with TestClient(main.app) as client:
        created = client.post(
            "/api/automations",
            json={
                "session_id": "automation-test",
                "title": "Prueba futura",
                "prompt": "Calcula 3+3",
                "schedule_type": "once",
                "schedule_value": "2099-01-01T00:00:00+00:00",
            },
        )
        assert created.status_code == 200
        assert created.json()["automation"]["status"] == "active"
        status = client.get("/api/autonomy/status?session_id=automation-test")
        assert status.status_code == 200
        payload = status.json()
        assert payload["version"] == "55.0.0"
        assert "mcp" in payload and "code_lab" in payload and "semantic" in payload


def test_v38_frontend_exposes_clean_autonomy_center():
    html = Path("index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    css = Path("static/styles.css").read_text(encoding="utf-8")
    assert 'data-view="missions"' in html
    assert "function renderMissions" in js
    assert "/api/autonomy/workflows" in js
    assert ".job-progress" in css


def test_v38_failed_workflow_retries_from_failed_checkpoint():
    plan = main.autonomy_planner.build(
        "Calcula 8+8 y presenta el resultado.", intent="math", mode="math", project_name="Retry"
    )
    workflow = main.autonomy_store.create_workflow("retry-test", plan)
    failed_step = workflow["steps"][0]
    main.autonomy_store.update_step(failed_step["id"], status="failed", error="fallo simulado")
    main.autonomy_store.update_workflow(workflow["id"], status="failed", error="fallo simulado")
    assert main.autonomy_store.prepare_retry(workflow["id"]) is True
    refreshed = main.autonomy_store.get_workflow(workflow["id"])
    assert refreshed["status"] == "planned"
    assert refreshed["steps"][0]["status"] == "pending"
    assert refreshed["steps"][0]["error"] == ""


def test_v38_idle_workflow_pause_and_cancel_finish_immediately():
    with TestClient(main.app) as client:
        paused = client.post(
            "/api/autonomy/workflows",
            json={
                "session_id": "control-test",
                "objective": "Prepara un plan local sencillo.",
                "mode": "auto",
                "project_name": "Controles",
                "start": False,
            },
        ).json()["workflow"]
        response = client.post(
            f"/api/autonomy/workflows/{paused['id']}/pause?session_id=control-test"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "paused"

        cancelled = client.post(
            "/api/autonomy/workflows",
            json={
                "session_id": "control-test",
                "objective": "Prepara otra misión local.",
                "mode": "auto",
                "project_name": "Controles",
                "start": False,
            },
        ).json()["workflow"]
        response = client.post(
            f"/api/autonomy/workflows/{cancelled['id']}/cancel?session_id=control-test"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


def test_v46_identity_register_login_and_logout():
    db_file = str(Path(tempfile.mkdtemp()) / "identity.db")
    store = IdentityStore(db_file, session_days=7)
    store.init_schema()
    user = store.register("owner@example.com", "SecurePassword123", "Owner", role="admin")
    assert user["role"] == "admin"
    session = store.login("owner@example.com", "SecurePassword123")
    assert session["token"]
    assert store.authenticate(session["token"])["email"] == "owner@example.com"
    assert store.logout(session["token"]) is True
    assert store.authenticate(session["token"]) is None


def test_v46_channel_store_is_idempotent_and_persistent():
    db_file = str(Path(tempfile.mkdtemp()) / "channels.db")
    store = ChannelStore(db_file)
    store.init_schema()
    assert store.claim_event("telegram:1", "telegram", "123") is True
    assert store.claim_event("telegram:1", "telegram", "123") is False
    first = store.session_for("telegram", "123", "Cristian")
    assert store.session_for("telegram", "123", "Cristian") == first
    store.finish_event("telegram:1", "completed", "ok")
    assert store.status()["events_24h"][0]["status"] == "completed"


def test_v46_telegram_secret_allowlist_and_parser():
    channel = TelegramChannel("token", "super-secret", "123")
    assert channel.configured is True
    assert channel.verify("super-secret") is True
    assert channel.verify("wrong") is False
    assert channel.allowed_sender("123") is True
    assert channel.allowed_sender("999") is False
    event = channel.parse({"update_id": 8, "message": {"message_id": 4, "chat": {"id": 123}, "from": {"id": 5, "first_name": "C"}, "text": "Hola"}})
    assert event["event_id"] == "telegram:8"
    assert event["text"] == "Hola"


def test_v49_telegram_parsers_accept_media_and_callbacks():
    telegram = TelegramChannel("token", "secret")
    image = telegram.parse({
        "update_id": 10,
        "message": {"message_id": 1, "chat": {"id": 7}, "photo": [{"file_id": "small", "file_size": 10}, {"file_id": "large", "file_size": 50}], "caption": "Analiza"},
    })
    voice = telegram.parse({
        "update_id": 11,
        "message": {"message_id": 2, "chat": {"id": 7}, "voice": {"file_id": "voice-1", "mime_type": "audio/ogg"}},
    })
    callback = telegram.parse({
        "update_id": 12,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 7, "first_name": "Cristian"},
            "message": {"message_id": 3, "chat": {"id": 7}},
            "data": "cmd:status",
        },
    })
    assert image["message_type"] == "image" and image["media_id"] == "large"
    assert voice["message_type"] == "audio" and voice["unsupported"] is False
    assert callback["message_type"] == "callback"
    assert callback["text"] == "cmd:status"
    assert callback["callback_query_id"] == "callback-1"


def test_v49_telegram_preferences_are_persistent():
    db_file = str(Path(tempfile.mkdtemp()) / "telegram-preferences.db")
    store = TelegramPreferenceStore(db_file)
    store.init_schema()
    assert store.get("7")["voice_reply"] is False
    assert store.set_voice("7", True)["voice_reply"] is True
    assert store.get("7")["voice_reply"] is True
    assert store.status()["voice_enabled"] == 1
    store.link_mission("workflow-1", "7")
    assert store.pending_missions()[0]["workflow_id"] == "workflow-1"
    store.mark_mission_notified("workflow-1", "completed")
    assert store.pending_missions()[0]["notified_status"] == "completed"


def test_v49_telegram_media_status_requires_private_provider_keys():
    client = TelegramMediaAI()
    assert client.status()["vision"] is False
    assert client.status()["transcription"] is False
    assert client.status()["speech"] is False


def test_v46_operations_and_channel_status_endpoints():
    with TestClient(main.app) as client:
        worker = client.get("/service-worker.js")
        assert worker.status_code == 200
        assert worker.headers["service-worker-allowed"] == "/"
        assert client.get("/index.html").status_code == 200
        assert client.get("/404.html").status_code == 200
        operations = client.get("/api/operations/overview", params={"session_id": "test-v46"})
        assert operations.status_code == 200
        assert operations.json()["version"] == "55.0.0"
        assert operations.json()["safety"]["human_approval"] is True
        channels = client.get("/api/channels/status")
        assert channels.status_code == 200
        assert set(channels.json()["channels"]) == {"telegram", "activity"}
        assert "preferences" in channels.json()
        assert "vision" in channels.json()["multimodal"]


def test_v47_frontend_is_clean_connected_and_boot_safe():
    html = Path("index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    css = Path("static/styles.css").read_text(encoding="utf-8")
    assert "¿Qué quieres resolver?" in html
    assert "Telegram Pro" in js
    assert 'data-view="channels"' in html
    assert "window.storage" not in js
    assert "headers.set('Authorization', `Bearer ${state.token}`)" in js
    assert "renderChannels" in js and "openAccount" in js
    assert "auth_required" in js
    assert "error?.status === 401" in js
    assert "jarvis-unified-intelligence-v55" in Path("service-worker.js").read_text(encoding="utf-8")
    assert "url.pathname.includes('/api/')" in Path("service-worker.js").read_text(encoding="utf-8")
    assert "overflow-x: hidden" in css


def test_v46_private_core_returns_readable_cors_401(monkeypatch):
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", ["*"])
    with TestClient(main.app) as client:
        response = client.post(
            "/api/jarvis",
            headers={"Origin": "https://owner.github.io"},
            json={"message": "2+2", "session_id": "auth-required-test"},
        )
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "*"
    assert "Inicia sesión" in response.json()["detail"]


def test_v47_auth_does_not_block_cors_preflight(monkeypatch):
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", ["*"])
    with TestClient(main.app) as client:
        response = client.options(
            "/api/jarvis",
            headers={
                "Origin": "https://owner.github.io",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_v55_planner_persists_budgeted_decision():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/intelligence/plan",
            json={
                "session_id": "v55-plan",
                "objective": "Investiga tres fuentes, compara resultados y verifica las conclusiones.",
                "mode": "research",
                "project_name": "Pruebas",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "planned"
        assert payload["plan"]["complexity"] in {"medium", "high"}
        assert payload["plan"]["budget"]["max_steps"] >= 6
        assert payload["decision"]["id"]
        listed = client.get("/api/intelligence/decisions", params={"session_id": "v55-plan"}).json()
        assert any(item["id"] == payload["decision"]["id"] for item in listed["decisions"])


def test_v55_chat_exposes_recovery_budget():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/jarvis",
            json={"message": "2+2", "session_id": "v55-chat", "request_id": "v55-chat-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["intelligence"]["decision_id"]
        assert data["intelligence"]["recovery"]


def test_v55_structured_knowledge_lifecycle():
    with TestClient(main.app) as client:
        created = client.post(
            "/api/knowledge/facts",
            json={
                "session_id": "v55-facts", "project_name": "JARVIS",
                "subject": "Interfaz", "predicate": "debe ser", "object_text": "simple y accesible",
                "confidence": 0.9, "verified": True,
            },
        )
        assert created.status_code == 200
        fact = created.json()["fact"]
        found = client.get(
            "/api/knowledge/facts", params={"session_id": "v55-facts", "query": "interfaz accesible"},
        ).json()["facts"]
        assert any(item["id"] == fact["id"] for item in found)
        deleted = client.delete(
            f"/api/knowledge/facts/{fact['id']}", params={"session_id": "v55-facts"},
        )
        assert deleted.status_code == 200


def test_v55_safe_interactive_artifacts():
    with TestClient(main.app) as client:
        created = client.post(
            "/api/artifacts",
            json={
                "session_id": "v55-artifacts", "title": "Progreso", "artifact_type": "chart",
                "spec": {"labels": ["Plan", "Ejecución"], "values": [30, 70], "unit": "%"},
            },
        )
        assert created.status_code == 200
        artifact = created.json()["artifact"]
        assert artifact["spec"]["values"] == [30.0, 70.0]
        listed = client.get("/api/artifacts", params={"session_id": "v55-artifacts"}).json()
        assert listed["artifacts"][0]["id"] == artifact["id"]


def test_v55_status_integrations_and_ui_contract():
    with TestClient(main.app) as client:
        status = client.get("/api/v55/status", params={"session_id": "v55-status"})
        assert status.status_code == 200
        assert status.json()["version"] == "55.0.0"
        integrations = client.get("/api/integrations").json()["integrations"]
        assert {"telegram", "google_calendar", "gmail", "google_drive", "github", "notion", "mcp"}.issubset(
            {item["name"] for item in integrations}
        )
        voice = client.post("/api/voice/speech", json={"text": "Hola"})
        assert voice.status_code == 503
    html = Path("index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert 'data-view="knowledge"' in html and 'data-view="nexus"' in html
    assert "renderKnowledge" in js and "renderNexus" in js and "speakMessage" in js
    assert "jarvis_v55_chats" in js
