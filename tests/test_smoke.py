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
        assert live.json()["version"] == "25.0.0"
        assert live.headers["x-jarvis-version"] == "25.0.0"
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
        assert data["version"] == "25.0.0"
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


def test_provider_gateway_endpoints_and_route_preview():
    with TestClient(main.app) as client:
        status = client.get("/api/providers")
        assert status.status_code == 200
        payload = status.json()
        assert payload["version"] == "25.0.0"
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
        assert status.json()['version'] == '25.0.0'



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
        assert payload['version'] == '25.0.0'
        assert 'anthropic' in payload['matrix']['providers']
        assert 'coding' in payload['matrix']['task_preferences']
        assert payload['quality_council']['max_providers'] >= 2

        registry = client.get('/api/tools/registry')
        assert registry.status_code == 200
        tools = registry.json()
        assert tools['version'] == '25.0.0'
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
        assert payload["version"] == "25.0.0"
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
        assert status.json()["version"] == "25.0.0"


def test_responsive_frontend_contract():
    html = Path("index.html").read_text(encoding="utf-8")
    css = Path("static/styles.css").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    manifest = json.loads(Path("static/manifest.webmanifest").read_text(encoding="utf-8"))

    assert "viewport-fit=cover" in html
    assert "?v=29" in html
    assert "jarvis-reactor-v29.svg" in html
    assert "focusModeBtn" in html
    assert "mobileDock" in html
    assert "chatFilterBar" in html
    assert "thinking-stage-rail" in html
    assert "jarvis_chat_filter_v29" in js
    assert "--app-height" in css
    assert "@media (max-width: 680px)" in css
    assert "@media (max-height: 540px)" in css
    assert "keyboard-open" in css
    assert "visualViewport" in js
    assert "updateViewportMetrics" in js
    assert manifest["display"] == "standalone"
