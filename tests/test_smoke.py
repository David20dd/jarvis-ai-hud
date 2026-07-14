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


if __name__ == "__main__":
    unittest.main()
