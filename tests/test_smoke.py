import os
import tempfile
import unittest
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / "jarvis_nexus_v6_test.db"
for suffix in ("", "-shm", "-wal"):
    candidate = Path(str(TEST_DB) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ.setdefault("JARVIS_PUBLIC_MODE", "true")
os.environ["JARVIS_DB_FILE"] = str(TEST_DB)

import main
from fastapi.testclient import TestClient


class JarvisNexusSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.init_db()
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        for suffix in ("", "-shm", "-wal"):
            candidate = Path(str(TEST_DB) + suffix)
            if candidate.exists():
                candidate.unlink()

    def test_calculator(self):
        result = main.calculator("test", "85000 * 0.12")
        self.assertEqual(result["result"], 10200)

    def test_sympy(self):
        result = main.sympy_solve("test", "x^2 - 5*x + 6 = 0", "x")
        self.assertEqual(set(result["solutions"]), {"2", "3"})

    def test_assets_exist(self):
        self.assertTrue((main.STATIC_DIR / "jarvis-reactor-v10.png").exists())
        self.assertTrue((main.STATIC_DIR / "jarvis-reactor-v10.webp").exists())
        self.assertTrue((main.STATIC_DIR / "manifest.webmanifest").exists())
        self.assertTrue((main.STATIC_DIR / "styles.css").exists())
        self.assertTrue((main.STATIC_DIR / "app.js").exists())
        self.assertTrue((main.BASE_DIR / "service-worker.js").exists())
        self.assertTrue(main.INDEX_FILE.exists())

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["status"], {"ok", "degraded"})

    def test_self_check(self):
        response = self.client.get("/api/self-check")
        self.assertEqual(response.status_code, 200)
        self.assertIn("checks", response.json())

    def test_root_serves_interface(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("J.A.R.V.I.S.", response.text)
        self.assertIn("/static/app.js", response.text)

    def test_public_direct_math_route(self):
        response = self.client.post(
            "/api/jarvis",
            json={"message": "Calcula el 12% de 85000", "session_id": "test_public", "project_name": "Economía", "mode": "math"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("reply", payload)
        self.assertEqual(payload.get("intent"), "math")
        self.assertIn("latency_ms", payload)
        self.assertEqual(payload.get("project_name"), "Economía")

    def test_capabilities_include_advanced_features(self):
        response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        features = set(response.json().get("features", []))
        self.assertIn("smart_intent_router", features)
        self.assertIn("project_workspaces", features)
        self.assertIn("offline_pwa_shell", features)

    def test_router_preview(self):
        response = self.client.get("/api/router/preview", params={"message": "Investiga noticias recientes sobre inteligencia artificial"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("intent"), "research")
        self.assertIn("recommended_mode", payload)

    def test_knowledge_search(self):
        main.memory_save("test_knowledge", "El proyecto usa una interfaz oscura", "project", 4)
        response = self.client.get("/api/knowledge/search", params={"session_id": "test_knowledge", "query": "interfaz"})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json().get("total", 0), 1)

    def test_execution_plan_and_verification(self):
        plan = main.build_execution_plan("research", "Investiga un tema")
        self.assertGreaterEqual(len(plan), 4)
        verification = main.verify_result(
            "Investiga un tema",
            "research",
            {"reply": "Fuente: https://example.com\nHallazgo verificable.", "tools": [{"name": "web_search"}]},
        )
        self.assertTrue(verification["verified"])

    def test_resilient_direct_route_has_trace(self):
        response = self.client.post(
            "/api/jarvis",
            json={"message": "Calcula el 15% de 200", "session_id": "test_resilience", "project_name": "Pruebas", "mode": "math"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("verified"))
        self.assertGreaterEqual(payload.get("resolution_attempts", 0), 1)
        self.assertTrue(payload.get("resolution_trace"))

    def test_resilience_status_endpoint(self):
        response = self.client.get("/api/resilience/status", params={"session_id": "test_resilience"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("version"), "17.0.0")
        self.assertIn("providers", payload)
        self.assertIn("limits", payload)

    def test_capabilities_include_resilience_features(self):
        response = self.client.get("/api/capabilities")
        features = set(response.json().get("features", []))
        self.assertIn("multi_provider_fallback", features)
        self.assertIn("execution_planner", features)
        self.assertIn("result_verification", features)
        self.assertIn("resilient_web_search", features)

    def test_idempotent_chat_replay(self):
        payload = {"message": "Calcula el 10% de 300", "session_id": "test_idempotency", "request_id": "req-fixed-001"}
        first = self.client.post("/api/jarvis", json=payload)
        second = self.client.post("/api/jarvis", json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json().get("reply"), second.json().get("reply"))
        self.assertTrue(second.json().get("idempotent_replay"))

    def test_direct_memory_route(self):
        saved = self.client.post("/api/jarvis", json={"message": "Recuerda que prefiero respuestas completas", "session_id": "test_memory_route"})
        recalled = self.client.post("/api/jarvis", json={"message": "¿Qué recuerdas?", "session_id": "test_memory_route"})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(recalled.status_code, 200)
        self.assertIn("respuestas completas", recalled.json().get("reply", ""))


if __name__ == "__main__":
    unittest.main()
